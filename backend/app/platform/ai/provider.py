"""The model call itself: Claude with server-side web search.

This is the only module in the codebase that talks to an AI provider, and the
only one that reads the API credential.

**Why web search rather than model knowledge.** Market Insights answers
questions whose answers change — funding rounds, leadership, recent
developments. A model's training data has a cutoff, so answering from it alone
would produce confident, stale prose with no way to tell which parts had aged.
The ``web_search`` server tool runs on Anthropic's infrastructure, returns
results with real URLs, and lets the model cite them inline.

**Sources are observed, never invented.** :class:`ResearchSource` values come
from ``web_search_tool_result`` blocks the API actually returned. Nothing here
parses URLs out of prose, and nothing constructs a citation the tool did not
report — a fabricated source in a business-intelligence report is worse than
no source at all (§17). ``cited=True`` is set only where a text block carried
a ``web_search_result_location`` citation naming that URL, so the interface can
distinguish *retrieved* from *quoted*.

**Turn shape.** Server tools run a sampling loop on Anthropic's side. When it
reaches its iteration limit the response comes back with ``stop_reason ==
"pause_turn"`` and must be resumed by echoing the assistant turn back
unchanged — no synthetic "continue" message, which would corrupt the tool
state. ``max_continuations`` bounds that loop so a pathological turn cannot run
forever.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic
import structlog
from anthropic.types.beta import BetaMessage
from fastapi import status

from app.core.config import Settings
from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)

#: Tool version carrying dynamic filtering — Claude filters results in a
#: sandbox before they reach the context window. Supported on the Opus 5 /
#: Sonnet 5 generation. Declaring ``code_execution`` alongside it would create
#: a second execution environment and confuse the model, so it is not declared.
WEB_SEARCH_TOOL_TYPE = "web_search_20260209"

#: Server-side refusal fallback. A safety decline returns HTTP 200 with
#: ``stop_reason: "refusal"`` rather than an error; with this the API re-runs
#: the request on a fallback model inside the same call, routed by category, so
#: a borderline company name does not dead-end the user. A decline that
#: produced no output is not billed.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AiNotConfiguredError(AppError):
    """No AI credential is configured, so no model can be called.

    A first-class state rather than a bug: the deployment simply has no key.
    Reported as 503 so the frontend can render its "AI is not connected"
    surface instead of a generic failure.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "ai_not_configured"
    message = (
        "AI is not connected. An administrator must configure an AI provider "
        "credential before research can run."
    )


class AiProviderError(AppError):
    """The provider was reachable but the turn did not produce a result."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "ai_provider_error"
    message = "The AI provider could not complete this request. Please try again."


class AiTemporarilyUnavailableError(AppError):
    """Rate limited, overloaded or timed out — worth retrying."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "ai_temporarily_unavailable"
    message = "The AI service is busy right now. Please try again in a moment."


class AiRefusedError(AppError):
    """The model, and its fallback, declined to answer."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "ai_refused"
    message = "The AI declined to research this subject."


@dataclass(frozen=True, slots=True)
class ResearchSource:
    """One page the model actually retrieved while answering.

    Attributes:
        title: page title as the search tool reported it.
        url: the retrieved URL. Never reconstructed from prose.
        page_age: the tool's freshness hint, when it supplied one.
        cited: whether a sentence in the answer carried an inline citation
            naming this URL, as opposed to it merely having been read.
    """

    title: str
    url: str
    page_age: str | None = None
    cited: bool = False


@dataclass(frozen=True, slots=True)
class ResearchResult:
    """Everything one completed turn produced."""

    text: str
    sources: tuple[ResearchSource, ...] = ()
    model: str = ""
    stop_reason: str | None = None
    search_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    #: True when the answer stopped at ``max_tokens`` or ran out of
    #: continuations, so the caller can label it partial rather than final.
    truncated: bool = False
    performed_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))


class ResearchProvider(Protocol):
    """What the gateway needs from an AI provider.

    Stated as a Protocol so the service layer is testable without a network
    call, and so a second vendor could be added without touching any caller.
    """

    async def run(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        web_search: bool = True,
    ) -> ResearchResult:
        """Run one conversational turn and return its result."""
        ...


class AnthropicResearchProvider:
    """A :class:`ResearchProvider` backed by the Claude Messages API."""

    def __init__(self, settings: Settings) -> None:
        if not settings.ai_configured:
            raise AiNotConfiguredError
        key = settings.anthropic_api_key
        if key is None:  # pragma: no cover - narrowed by ai_configured above
            raise AiNotConfiguredError
        self._client = anthropic.AsyncAnthropic(
            api_key=key.get_secret_value(),
            timeout=settings.ai_request_timeout_seconds,
            # The SDK already retries 429/5xx/connection errors; two is its
            # default and enough here, because a research turn is expensive and
            # a caller-visible "try again" beats a long silent retry loop.
            max_retries=2,
        )
        self._model = settings.ai_model
        self._max_tokens = settings.ai_max_output_tokens
        self._max_uses = settings.ai_web_search_max_uses
        self.max_continuations = settings.ai_max_continuations

    async def run(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        web_search: bool = True,
    ) -> ResearchResult:
        """Run one turn, resuming across ``pause_turn`` until it completes.

        Args:
            system: the system prompt, already composed by the service.
            messages: full conversation history in Messages API shape.
            web_search: whether to offer the search tool. Follow-up questions
                about material already in the conversation still get it — the
                model decides whether reaching for it is warranted.

        Returns:
            The concatenated answer plus every source actually retrieved.

        Raises:
            AiRefusedError: the model and its fallback both declined.
            AiTemporarilyUnavailableError: rate limited, overloaded, timed out.
            AiProviderError: any other provider failure, or an empty answer.
        """
        tools: list[dict[str, Any]] = []
        if web_search:
            tools.append(
                {
                    "type": WEB_SEARCH_TOOL_TYPE,
                    "name": "web_search",
                    "max_uses": self._max_uses,
                }
            )

        turns = [dict(message) for message in messages]
        texts: list[str] = []
        sources: dict[str, ResearchSource] = {}
        cited_urls: set[str] = set()
        searches = 0
        input_tokens = 0
        output_tokens = 0
        stop_reason: str | None = None
        model_used = self._model
        truncated = False

        for attempt in range(self.max_continuations + 1):
            message = await self._send(system=system, messages=turns, tools=tools)

            model_used = message.model or model_used
            stop_reason = message.stop_reason
            input_tokens += getattr(message.usage, "input_tokens", 0) or 0
            output_tokens += getattr(message.usage, "output_tokens", 0) or 0

            if stop_reason == "refusal":
                # Reached only when the fallback chain also declined. The
                # provider's explanation is deliberately not echoed onward.
                logger.info(
                    "ai_turn_refused",
                    category=getattr(getattr(message, "stop_details", None), "category", None),
                )
                raise AiRefusedError

            block_text, block_sources, block_cited, block_searches = harvest_blocks(
                message.content
            )
            texts.extend(block_text)
            searches += block_searches
            cited_urls |= block_cited
            for source in block_sources:
                sources.setdefault(source.url, source)

            if stop_reason == "max_tokens":
                truncated = True
                break

            if stop_reason != "pause_turn":
                break

            # Resume: echo the paused assistant turn back untouched. The API
            # sees the trailing server-tool block and continues from it; adding
            # a "please continue" user message here would break that.
            turns.append({"role": "assistant", "content": message.content})
            if attempt == self.max_continuations:
                truncated = True

        answer = "\n\n".join(part for part in texts if part.strip()).strip()
        if not answer:
            logger.warning("ai_turn_produced_no_text", stop_reason=stop_reason)
            raise AiProviderError

        return ResearchResult(
            text=answer,
            sources=tuple(
                ResearchSource(
                    title=source.title,
                    url=source.url,
                    page_age=source.page_age,
                    cited=source.url in cited_urls,
                )
                for source in sources.values()
            ),
            model=model_used,
            stop_reason=stop_reason,
            search_count=searches,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            truncated=truncated,
        )

    async def _send(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> BetaMessage:
        """One request, streamed, with provider errors mapped to ``AppError``.

        Streaming is not optional at this ``max_tokens``: a non-streamed
        request that large can exceed the HTTP timeout before the model has
        finished writing. ``get_final_message`` assembles the whole message, so
        the caller still sees a plain return value.
        """
        try:
            async with self._client.beta.messages.stream(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                tools=tools or anthropic.NOT_GIVEN,  # type: ignore[arg-type]
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                return await stream.get_final_message()
        except (
            anthropic.RateLimitError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
            anthropic.APIConnectionError,
        ) as exc:
            logger.warning("ai_provider_unavailable", error=type(exc).__name__)
            raise AiTemporarilyUnavailableError from exc
        except anthropic.AuthenticationError as exc:
            # A bad key is a deployment fault, not a user one. Reported as
            # "not configured" so the operator-facing message is the accurate
            # one, and so no credential detail reaches the client.
            logger.error("ai_provider_rejected_credential")
            raise AiNotConfiguredError from exc
        except anthropic.APIStatusError as exc:
            logger.warning("ai_provider_error", status_code=exc.status_code)
            raise AiProviderError from exc


def harvest_blocks(
    blocks: Iterable[Any],
) -> tuple[list[str], list[ResearchSource], set[str], int]:
    """Pull text, sources, citations and search count out of one response.

    A module-level function over duck-typed blocks, so the unit tests can feed
    it recorded fixtures without constructing SDK models or a client.

    Two shapes matter and both are handled defensively, because a server-tool
    failure arrives as a **successful** HTTP response: on success a
    ``web_search_tool_result`` block's ``content`` is a *list* of results, and
    on failure it is a single error *object*. Indexing without checking is the
    documented way to turn a soft failure into a crash.
    """
    texts: list[str] = []
    sources: list[ResearchSource] = []
    cited: set[str] = set()
    searches = 0

    for block in blocks:
        kind = getattr(block, "type", None)

        if kind == "text":
            text_value = getattr(block, "text", "") or ""
            if text_value:
                texts.append(text_value)
            for citation in getattr(block, "citations", None) or ():
                url = getattr(citation, "url", None)
                if getattr(citation, "type", None) == "web_search_result_location" and url:
                    cited.add(url)

        elif kind == "server_tool_use":
            if getattr(block, "name", None) == "web_search":
                searches += 1

        elif kind == "web_search_tool_result":
            content = getattr(block, "content", None)
            if not isinstance(content, list):
                # An error object, e.g. ``{"error_code": "max_uses_exceeded"}``.
                # Partial results are a supported outcome (§15, "partial source
                # availability"): the turn keeps whatever it already gathered
                # rather than failing outright.
                logger.info(
                    "ai_web_search_error",
                    error_code=getattr(content, "error_code", None),
                )
                continue
            for result in content:
                url = getattr(result, "url", None)
                if not url:
                    continue
                sources.append(
                    ResearchSource(
                        title=(getattr(result, "title", None) or url).strip(),
                        url=url,
                        page_age=getattr(result, "page_age", None),
                    )
                )

    return texts, sources, cited, searches


__all__ = [
    "WEB_SEARCH_TOOL_TYPE",
    "AiNotConfiguredError",
    "AiProviderError",
    "AiRefusedError",
    "AiTemporarilyUnavailableError",
    "AnthropicResearchProvider",
    "ResearchProvider",
    "ResearchResult",
    "ResearchSource",
    "harvest_blocks",
]
