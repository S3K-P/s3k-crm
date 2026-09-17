"""A second :class:`ResearchProvider`, backed by Gemini with Search grounding.

**Why this vendor and not a cheaper one to wire up.** Market Insights is
defined as *cited* company research — ``provider.py`` states the rule it lives
by: sources are observed, never invented, because a fabricated source in a
business-intelligence report is worse than no source at all. A model without
server-side search can only answer from training data, producing confident
prose with no way to tell which parts had aged and nothing real to cite. Gemini
is the free-tier option that keeps the guarantee, because Google Search
grounding returns actual retrieved URLs.

**Sources come from grounding metadata, never from prose.**
``grounding_chunks`` are the pages the model actually retrieved;
``grounding_supports`` say which of them a sentence was grounded in. Nothing
here parses a URL out of the answer text, which is the same discipline the
Anthropic provider applies to ``web_search_tool_result`` blocks.

**Shape differences from Anthropic, handled here so nothing above notices.**
Gemini names the assistant role ``model``, carries the system prompt in the
config rather than the message list, and finishes a turn in one response
instead of pausing and resuming — so there is no continuation loop. The
:class:`~app.platform.ai.provider.ResearchProvider` Protocol is the seam that
makes those differences invisible to :class:`AiGatewayService` and to every
product feature.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import Settings
from app.platform.ai.provider import (
    AiNotConfiguredError,
    AiProviderError,
    AiRefusedError,
    AiTemporarilyUnavailableError,
    CredentialCheck,
    ResearchResult,
    ResearchSource,
)

logger = structlog.get_logger(__name__)

#: Finish reasons that mean the model declined rather than failed.
_REFUSAL_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"}

#: HTTP statuses worth retrying, as opposed to worth reporting. 429 matters
#: more here than on the Anthropic path: the free tier is rate-limited by
#: design, so "busy, try again" is an expected outcome rather than an incident.
_RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}


def _to_contents(messages: Sequence[dict[str, Any]]) -> list[types.Content]:
    """Translate Messages-API turns into Gemini ``Content`` objects.

    The gateway speaks one dialect — ``{"role": "user"|"assistant", "content":
    str}`` — and each provider translates. Gemini calls the assistant ``model``;
    anything that is not a user turn is mapped to it rather than matched
    exactly, so an unexpected role degrades to "the model said this" instead of
    raising deep inside a research run.
    """
    contents: list[types.Content] = []
    for message in messages:
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        role = "user" if message.get("role") == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    return contents


def harvest_grounding(candidate: Any) -> tuple[list[ResearchSource], set[str]]:
    """Pull retrieved pages and citations out of one candidate.

    A module-level function over duck-typed objects, so unit tests can feed it
    recorded fixtures without constructing SDK models or a client — the same
    reason ``harvest_blocks`` is shaped this way on the Anthropic side.

    Returns the pages retrieved, and the subset of their URLs that a sentence
    was actually grounded in. Everything is read defensively: grounding
    metadata is absent entirely when the model answered without searching,
    which is a normal outcome and not an error.
    """
    metadata = getattr(candidate, "grounding_metadata", None)
    if metadata is None:
        return [], set()

    sources: list[ResearchSource] = []
    for chunk in getattr(metadata, "grounding_chunks", None) or ():
        web = getattr(chunk, "web", None)
        uri = getattr(web, "uri", None)
        if not uri:
            continue
        title = getattr(web, "title", None) or getattr(web, "domain", None) or uri
        sources.append(ResearchSource(title=str(title).strip(), url=uri))

    # A support names the chunks its sentence rested on, by index. Anything
    # out of range is skipped rather than trusted — the index comes from the
    # provider, and a mismatch would otherwise raise mid-report.
    cited: set[str] = set()
    for support in getattr(metadata, "grounding_supports", None) or ():
        for index in getattr(support, "grounding_chunk_indices", None) or ():
            if isinstance(index, int) and 0 <= index < len(sources):
                cited.add(sources[index].url)

    return sources, cited


class GeminiResearchProvider:
    """A :class:`ResearchProvider` backed by the Gemini API."""

    def __init__(self, settings: Settings, api_key: str) -> None:
        """Build a provider around one credential.

        Raises:
            AiNotConfiguredError: ``api_key`` is empty.
        """
        if not api_key or not api_key.strip():
            raise AiNotConfiguredError
        self._client = genai.Client(api_key=api_key.strip())
        self._model = settings.ai_gemini_model
        self._max_tokens = settings.ai_max_output_tokens
        #: Whether this deployment's key may use Search grounding at all. False
        #: on a free-tier key, where declaring the tool returns 429 while plain
        #: generation succeeds — see ``ai_gemini_grounding`` in config.
        self._grounding_allowed = settings.ai_gemini_grounding

    async def run(
        self,
        *,
        system: str,
        messages: Sequence[dict[str, Any]],
        web_search: bool = True,
    ) -> ResearchResult:
        """Run one turn with Search grounding, and report what it retrieved.

        Raises:
            AiRefusedError: the model declined on safety grounds.
            AiTemporarilyUnavailableError: rate limited or transiently failing.
            AiProviderError: any other failure, or an answer with no text.
        """
        # Grounding needs both: the caller wanting it, and the deployment's key
        # being entitled to it. A free-tier key is not, and asking anyway fails
        # the whole turn rather than degrading — so the entitlement is checked
        # here and the answer is labelled honestly instead.
        grounded = web_search and self._grounding_allowed
        if web_search and not grounded:
            logger.info("ai_turn_ungrounded", vendor="gemini", reason="grounding_disabled")

        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=self._max_tokens,
            tools=[types.Tool(google_search=types.GoogleSearch())] if grounded else None,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=_to_contents(messages),
                config=config,
            )
        except genai_errors.ClientError as exc:
            status = getattr(exc, "code", None)
            if status in _RETRYABLE_STATUSES:
                logger.warning("ai_provider_unavailable", vendor="gemini", status=status)
                raise AiTemporarilyUnavailableError from exc
            if status in (401, 403):
                # A bad key is a deployment fault, not a user one. Reported as
                # "not configured" so the operator-facing message is accurate
                # and no credential detail reaches the client.
                logger.error("ai_provider_rejected_credential", vendor="gemini")
                raise AiNotConfiguredError from exc
            logger.warning("ai_provider_error", vendor="gemini", status=status)
            raise AiProviderError from exc
        except genai_errors.ServerError as exc:
            logger.warning("ai_provider_unavailable", vendor="gemini", status="5xx")
            raise AiTemporarilyUnavailableError from exc
        except genai_errors.APIError as exc:
            logger.warning("ai_provider_error", vendor="gemini")
            raise AiProviderError from exc

        candidates = getattr(response, "candidates", None) or ()
        if not candidates:
            logger.warning("ai_turn_produced_no_candidate", vendor="gemini")
            raise AiProviderError

        candidate = candidates[0]
        finish = str(getattr(candidate, "finish_reason", "") or "")
        if finish in _REFUSAL_REASONS:
            logger.info("ai_turn_refused", vendor="gemini", reason=finish)
            raise AiRefusedError

        answer = (getattr(response, "text", None) or "").strip()
        if not answer:
            logger.warning("ai_turn_produced_no_text", vendor="gemini", finish=finish)
            raise AiProviderError

        sources, cited = harvest_grounding(candidate)
        usage = getattr(response, "usage_metadata", None)
        metadata = getattr(candidate, "grounding_metadata", None)

        return ResearchResult(
            text=answer,
            sources=tuple(
                ResearchSource(
                    title=source.title,
                    url=source.url,
                    page_age=source.page_age,
                    cited=source.url in cited,
                )
                for source in sources
            ),
            model=self._model,
            stop_reason=finish or None,
            # Gemini reports the queries it issued rather than a call count;
            # their number is the closest honest equivalent to "searches run".
            search_count=len(getattr(metadata, "web_search_queries", None) or ()),
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            truncated=finish == "MAX_TOKENS",
            grounded=grounded,
        )


async def verify_gemini_credential(
    *, api_key: str, model: str, timeout_seconds: float = 15.0
) -> CredentialCheck:
    """Ask Google whether a key works, without spending a generation on it.

    Retrieves the configured model, which authenticates the key *and* confirms
    that model is reachable under it — the second half matters because a key
    valid for one model tier and not another would otherwise be discovered by
    the first research run.

    Never raises for an authentication failure: a rejected key is an ordinary
    answer to this question, recorded against the credential by the caller.
    """
    if not api_key or not api_key.strip():
        return CredentialCheck(ok=False, error="No API key was provided.")

    client = genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
    )
    try:
        await client.aio.models.get(model=model)
        return CredentialCheck(ok=True, model=model)
    except genai_errors.ClientError as exc:
        status = getattr(exc, "code", None)
        if status in (401, 403):
            logger.info("ai_credential_check_rejected", vendor="gemini")
            return CredentialCheck(ok=False, error="The provider rejected this API key.")
        if status == 404:
            logger.warning("ai_credential_check_model_missing", vendor="gemini", model=model)
            return CredentialCheck(
                ok=False,
                error=f"The configured model ({model}) is not available to this key.",
            )
        if status == 429:
            return CredentialCheck(
                ok=False, error="Rate limited by the provider. Try again in a moment."
            )
        logger.warning("ai_credential_check_failed", vendor="gemini", status=status)
        return CredentialCheck(ok=False, error="The provider returned an unexpected error.")
    except genai_errors.APIError:
        logger.warning("ai_credential_check_unreachable", vendor="gemini")
        return CredentialCheck(
            ok=False, error="Could not reach the provider. Try again in a moment."
        )


__all__ = [
    "GeminiResearchProvider",
    "harvest_grounding",
    "verify_gemini_credential",
]
