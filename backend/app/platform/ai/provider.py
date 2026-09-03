"""The model call itself: a model that can search the web while it answers.

This is the only module in the codebase that talks to an AI provider, and the
only one that reads an API credential. Two vendors are implemented behind
:class:`ResearchProvider` — Claude with its ``web_search`` server tool, and
Gemini with Google Search grounding — and ``ai_provider`` picks between them.
They are not interchangeable in quality: see :class:`GeminiResearchProvider`
for what the free option gives up.

**Why web search rather than model knowledge.** Market Insights answers
questions whose answers change — funding rounds, leadership, recent
developments. A model's training data has a cutoff, so answering from it alone
would produce confident, stale prose with no way to tell which parts had aged.
The ``web_search`` server tool runs on Anthropic's infrastructure, returns
results with real URLs, and lets the model cite them inline.

**Sources are observed, never invented.** This is the rule both providers are
held to. :class:`ResearchSource` values come from what the search tool
reported — ``web_search_tool_result`` blocks on Claude, ``grounding_chunks`` on
Gemini. Nothing here parses URLs out of prose, and nothing constructs a
citation the tool did not report: a fabricated source in a business-
intelligence report is worse than no source at all (§17). ``cited=True`` marks
the narrower claim that a sentence actually rested on that page, so the
interface can distinguish *retrieved* from *quoted*.

**Turn shape differs between the two.** Claude's server tools run a sampling
loop on Anthropic's side; when it reaches its iteration limit the response
comes back with ``stop_reason == "pause_turn"`` and must be resumed by echoing
the assistant turn back unchanged — no synthetic "continue" message, which
would corrupt the tool state. ``max_continuations`` bounds that loop so a
pathological turn cannot run forever. Gemini's grounding completes inside a
single ``generate_content`` call, so it has no continuation loop at all and
``max_continuations`` does not apply to it.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic
import httpx
import structlog
from anthropic.types.beta import BetaMessage
from fastapi import status
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

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

            block_text, block_sources, block_cited, block_searches = harvest_blocks(message.content)
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


class GeminiResearchProvider:
    """A :class:`ResearchProvider` backed by Gemini, the free option.

    Flash models carry a free token allowance, so a deployment can write
    Market Insights reports without a paid account.

    **Grounding is off by default — read this before turning it on.** Google
    Search grounding needs a Google Cloud project with billing *enabled*, not
    merely a valid API key; without it, a grounded request does not degrade,
    it returns a flat 429 on every model, every time
    (ai.google.dev/gemini-api/docs/rate-limits). ``settings.
    gemini_grounding_enabled`` gates whether this provider ever asks for it,
    so a deployment without billing configured gets a Gemini that always
    answers — from its own training data — rather than one that always fails.
    :class:`ResearchResult` then carries no sources, and the existing
    "No external sources" panel already tells the reader plainly to treat the
    report as less firmly grounded; nothing here needs a second disclosure
    mechanism for the same fact.

    **What grounding gives up, once billing is enabled and it is turned on.**
    It returns sources as ``vertexaisearch.cloud.google.com`` redirect links
    rather than publisher URLs, and the ``domain`` field comes back empty
    (googleapis/python-genai#1512). A Sources panel listing a dozen identical
    Google hostnames is not evidence, so this provider resolves each redirect
    to its destination before returning it — that is what
    :meth:`_resolve_sources` is for, and it is the reason this class does
    network I/O the Anthropic one does not need.

    **One round trip, not a loop.** Grounding runs inside the single
    ``generate_content`` call, so there is no ``pause_turn`` equivalent and no
    continuation loop. ``ai_max_continuations`` does not apply here.
    """

    #: Prefix Google wraps every grounded source in. Matched rather than
    #: assumed: a chunk that is already a real URL is left alone.
    REDIRECT_HOST = "vertexaisearch.cloud.google.com"

    #: Bound on redirect resolution. These run concurrently and only to learn a
    #: URL, so a slow publisher must not extend a research turn noticeably.
    RESOLVE_TIMEOUT_SECONDS = 8.0
    RESOLVE_CONCURRENCY = 8

    #: Extra attempts on a transient capacity error, beyond the first. Google's
    #: own message calls these "usually temporary" (see `_send`), and one short
    #: retry clears most of them without the caller ever seeing a failure.
    CAPACITY_RETRIES = 2
    CAPACITY_RETRY_DELAY_SECONDS = 2.0

    def __init__(self, settings: Settings) -> None:
        if not settings.ai_configured:
            raise AiNotConfiguredError
        key = settings.gemini_api_key
        if key is None:  # pragma: no cover - narrowed by ai_configured above
            raise AiNotConfiguredError

        self._client = genai.Client(
            api_key=key.get_secret_value(),
            http_options=genai_types.HttpOptions(
                timeout=int(settings.ai_request_timeout_seconds * 1000),
            ),
        )
        self._model = settings.gemini_model
        self._max_tokens = settings.ai_max_output_tokens
        self._grounding_enabled = settings.gemini_grounding_enabled

    async def run(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        web_search: bool = True,
    ) -> ResearchResult:
        """Run one turn against Gemini and return its result.

        Args:
            system: the system prompt, already composed by the service.
            messages: conversation history in the gateway's shape.
            web_search: whether to offer Google Search grounding.

        Returns:
            The answer plus every source grounding actually retrieved.

        Raises:
            AiRefusedError: the response was blocked on safety grounds.
            AiTemporarilyUnavailableError: rate limited, overloaded, timed out.
            AiProviderError: any other provider failure, or an empty answer.
        """
        tools = grounding_tools(web_search=web_search, enabled=self._grounding_enabled)
        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=self._max_tokens,
            tools=tools,
            # Grounding runs on Google's side and calls nothing of ours, so
            # the SDK's automatic function-calling loop has no work to do here.
            # Declared off rather than left to default: with `tools` set, the
            # SDK otherwise warns and reserves the right to drive a loop this
            # provider does not want.
            automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        )

        response = await self._send(contents=to_gemini_contents(messages), config=config)
        text, sources, searches, finish_reason = harvest_gemini_response(response)

        if tools is None:
            # No search tool ran, so no URL in this text was ever fetched —
            # see `strip_unverified_links`. The configured prompt still asks
            # for inline citations regardless of grounding, and Gemini
            # complies by recalling plausible-looking ones from training data.
            text = strip_unverified_links(text)

        if not text:
            # A safety block returns 200 with no text and a finish reason
            # saying why — the same shape as Claude's ``refusal`` stop reason,
            # and it deserves the same 422 rather than a generic failure.
            if finish_reason in _BLOCKED_FINISH_REASONS:
                logger.info("ai_turn_refused", finish_reason=finish_reason)
                raise AiRefusedError
            logger.warning("ai_turn_produced_no_text", finish_reason=finish_reason)
            raise AiProviderError

        usage = getattr(response, "usage_metadata", None)

        return ResearchResult(
            text=text,
            sources=await self._resolve_sources(sources),
            model=getattr(response, "model_version", None) or self._model,
            stop_reason=finish_reason,
            search_count=searches,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            truncated=finish_reason == "MAX_TOKENS",
        )

    async def _send(
        self, *, contents: list[genai_types.Content], config: genai_types.GenerateContentConfig
    ) -> Any:
        """One ``generate_content`` call, with a short retry on capacity errors.

        A ``ServerError`` ("this model is currently experiencing high demand
        … usually temporary") cleared on a second attempt for every Flash
        model tried while building this provider, seconds later with no
        change on this end — the definition of worth one retry before telling
        the caller the service is busy. A ``ClientError`` gets none: 429 and a
        rejected credential are real states the caller needs to see, not
        transients that time fixes.
        """
        attempts = self.CAPACITY_RETRIES + 1
        for attempt in range(attempts):
            try:
                return await self._client.aio.models.generate_content(
                    model=self._model, contents=contents, config=config
                )
            except genai_errors.ClientError as exc:
                # 429 is the free tier's quota, which is "come back later", not
                # a fault. A rejected credential is a deployment fault,
                # reported as "not configured" for the same reason the
                # Anthropic path does so: that is the message whose advice
                # actually helps.
                if exc.code == 429:
                    logger.warning("ai_provider_unavailable", error="ClientError", code=exc.code)
                    raise AiTemporarilyUnavailableError from exc
                if is_credential_error(exc):
                    logger.error("ai_provider_rejected_credential", status_code=exc.code)
                    raise AiNotConfiguredError from exc
                logger.warning("ai_provider_error", status_code=exc.code)
                raise AiProviderError from exc
            except genai_errors.ServerError as exc:
                if attempt < attempts - 1:
                    logger.info("ai_provider_capacity_retry", attempt=attempt + 1, code=exc.code)
                    await asyncio.sleep(self.CAPACITY_RETRY_DELAY_SECONDS)
                    continue
                logger.warning("ai_provider_unavailable", error="ServerError", code=exc.code)
                raise AiTemporarilyUnavailableError from exc
            except (TimeoutError, httpx.TimeoutException) as exc:
                logger.warning("ai_provider_unavailable", error=type(exc).__name__)
                raise AiTemporarilyUnavailableError from exc
            except genai_errors.APIError as exc:
                logger.warning("ai_provider_error", status_code=getattr(exc, "code", None))
                raise AiProviderError from exc
        raise AssertionError("unreachable: the loop above always returns or raises")

    async def _resolve_sources(
        self, sources: Sequence[ResearchSource]
    ) -> tuple[ResearchSource, ...]:
        """Turn Google's redirect links into the publisher URLs behind them.

        Each redirect is followed once, concurrently, with a short timeout. A
        failure keeps the redirect URL: it still resolves in a browser, so a
        source the reader can open beats dropping the evidence entirely.

        Deduplication happens *after* resolution — two different redirect links
        routinely point at the same page, and the panel should list it once.
        """
        if not sources:
            return ()

        limiter = asyncio.Semaphore(self.RESOLVE_CONCURRENCY)

        async def resolve(client: httpx.AsyncClient, source: ResearchSource) -> ResearchSource:
            if self.REDIRECT_HOST not in source.url:
                return source
            async with limiter:
                try:
                    response = await client.get(source.url)
                except httpx.HTTPError as exc:
                    logger.info("ai_source_redirect_unresolved", error=type(exc).__name__)
                    return source
            final = str(response.url)
            if self.REDIRECT_HOST in final:
                return source
            # `title` holds the publisher domain for a grounded chunk, which is
            # a poor headline once the real URL is known but the only label
            # Google supplies. Kept as-is rather than invented from the page.
            return ResearchSource(
                title=source.title, url=final, page_age=source.page_age, cited=source.cited
            )

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.RESOLVE_TIMEOUT_SECONDS,
        ) as client:
            resolved = await asyncio.gather(
                *(resolve(client, source) for source in sources),
                return_exceptions=False,
            )

        unique: dict[str, ResearchSource] = {}
        for source in resolved:
            existing = unique.get(source.url)
            # A cited duplicate outranks an uncited one: the panel's "Cited"
            # badge has to survive deduplication.
            if existing is None or (source.cited and not existing.cited):
                unique[source.url] = source
        return tuple(unique.values())


#: Finish reasons that mean the model declined rather than failed.
_BLOCKED_FINISH_REASONS = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"})

#: ``reason`` values that mean the credential is the problem.
_CREDENTIAL_REASONS = frozenset(
    {"API_KEY_INVALID", "API_KEY_SERVICE_BLOCKED", "PERMISSION_DENIED", "ACCESS_TOKEN_EXPIRED"}
)


def is_credential_error(exc: genai_errors.ClientError) -> bool:
    """Whether a 4xx means "your key is wrong" rather than "your request was".

    Worth its own function because the obvious test is the wrong one: Google
    answers an invalid API key with **400 INVALID_ARGUMENT**, not 401, so the
    status code cannot separate a bad credential from a bad request. Left
    unhandled, a deployment with a mistyped key tells its operator "the AI
    provider could not complete this request. Please try again" — advice that
    will never work — instead of "AI is not connected".

    The structured ``reason`` is what gets matched. The human-readable message
    is deliberately not: it is prose, and prose gets reworded.
    """
    if exc.code in (401, 403):
        return True
    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        return False
    error = details.get("error")
    if not isinstance(error, dict):
        return False
    return any(
        isinstance(item, dict) and item.get("reason") in _CREDENTIAL_REASONS
        for item in error.get("details") or ()
    )


def grounding_tools(*, web_search: bool, enabled: bool) -> list[genai_types.Tool] | None:
    """The ``tools`` list to offer Gemini for one turn, or ``None`` for a plain call.

    ``enabled`` gates this independently of ``web_search``: a deployment
    without billing on its Google Cloud project cannot use grounding no
    matter how badly the caller wants it, and asking anyway would not
    degrade — it would turn every research turn into a guaranteed 429. A
    plain function rather than inline in :meth:`GeminiResearchProvider.run`
    so the decision is unit-testable without a client or a network call.
    """
    if not (web_search and enabled):
        return None
    return [genai_types.Tool(google_search=genai_types.GoogleSearch())]


#: `[label](url)` — and, harmlessly, the bracket/paren part of an image
#: `![alt](url)` too, which loses only its leading `!`. Reports do not embed
#: images, so that overlap costs nothing here.
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\(https?://[^)\s]+\)")


def strip_unverified_links(text: str) -> str:
    """Turn every ``[label](url)`` in ungrounded output into plain ``label``.

    An ungrounded call has no search tool behind it, so any URL the model
    writes came from its own recall rather than a page it actually fetched —
    it can be right, stale, or entirely invented, and there is no way to tell
    which from here. A confident, real-looking link nobody retrieved is worse
    than no link at all, which is exactly the standard :class:`ResearchSource`
    is already held to (see the module docstring's "sources are observed,
    never invented"); this closes the same gap for links embedded in the
    prose itself, which that standard does not otherwise reach. The label
    survives because the claim it names may well be true — only the
    unverifiable citation is removed.
    """
    return _MARKDOWN_LINK.sub(lambda match: match.group(1), text)


def to_gemini_contents(messages: Sequence[dict[str, Any]]) -> list[genai_types.Content]:
    """Convert the gateway's message list into Gemini ``Content`` values.

    The gateway speaks the Messages API shape because that is what its first
    provider used. The only differences that matter here are the name of the
    assistant role and that content arrives as plain text, so the conversion
    is this small — and doing it here keeps the shape out of the service.
    """
    contents: list[genai_types.Content] = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str):
            # Defensive: the Anthropic provider echoes block lists back into
            # its own history, and nothing should reach here having done that.
            content = str(content)
        contents.append(
            genai_types.Content(
                role="model" if message.get("role") == "assistant" else "user",
                parts=[genai_types.Part(text=content)],
            )
        )
    return contents


def harvest_gemini_response(response: Any) -> tuple[str, list[ResearchSource], int, str | None]:
    """Pull text, grounded sources, search count and finish reason from a response.

    A module-level function over duck-typed objects for the same reason
    :func:`harvest_blocks` is one: the unit tests feed it recorded shapes
    without constructing SDK models or a client.

    ``cited`` is set from ``grounding_supports``, which is the only signal
    distinguishing a chunk a sentence actually rests on from one that was
    merely retrieved. Nothing here reads URLs out of the model's prose.
    """
    candidates = getattr(response, "candidates", None) or ()
    if not candidates:
        return "", [], 0, None

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    finish = getattr(finish_reason, "name", None) or (str(finish_reason) if finish_reason else None)

    texts: list[str] = []
    for part in getattr(getattr(candidate, "content", None), "parts", None) or ():
        part_text = getattr(part, "text", None)
        if part_text:
            texts.append(part_text)

    metadata = getattr(candidate, "grounding_metadata", None)
    chunks = list(getattr(metadata, "grounding_chunks", None) or ())
    searches = len(getattr(metadata, "web_search_queries", None) or ())

    cited_indices: set[int] = set()
    for support in getattr(metadata, "grounding_supports", None) or ():
        for index in getattr(support, "grounding_chunk_indices", None) or ():
            cited_indices.add(index)

    sources: list[ResearchSource] = []
    for index, chunk in enumerate(chunks):
        web = getattr(chunk, "web", None)
        uri = getattr(web, "uri", None)
        if not uri:
            continue
        # `title` is the publisher domain; `domain` is documented but empty in
        # practice. Fall back through both to the URL rather than show "None".
        label = (getattr(web, "title", None) or getattr(web, "domain", None) or uri).strip()
        sources.append(ResearchSource(title=label, url=uri, cited=index in cited_indices))

    return "\n\n".join(texts).strip(), sources, searches, finish


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
    "GeminiResearchProvider",
    "ResearchProvider",
    "ResearchResult",
    "ResearchSource",
    "grounding_tools",
    "harvest_blocks",
    "harvest_gemini_response",
    "is_credential_error",
    "strip_unverified_links",
    "to_gemini_contents",
]
