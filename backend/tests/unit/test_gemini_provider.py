"""What the Gemini provider believes about a grounded response.

The same rule the Anthropic provider is held to (``test_ai_provider``): a
source exists because grounding reported it, never because a URL appeared in
the model's prose. Gemini's shape differs enough to be worth pinning
separately — sources arrive as indexed ``grounding_chunks`` and the "cited"
signal is a set of indices in ``grounding_supports``, so an off-by-one here
would silently mislabel evidence.

``harvest_gemini_response`` and ``to_gemini_contents`` are module-level
functions over duck-typed objects, so these fixtures are plain namespaces and
no client, key or network is involved. :class:`GeminiResearchProvider` itself
is exercised only through its redirect resolution, with a stubbed transport.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors as genai_errors

from app.platform.ai.provider import (
    AiTemporarilyUnavailableError,
    GeminiResearchProvider,
    ResearchSource,
    grounding_tools,
    harvest_gemini_response,
    is_credential_error,
    strip_unverified_links,
    to_gemini_contents,
)

REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123"


def chunk(uri: str, title: str | None = "publisher.example", domain: str | None = None) -> Any:
    return SimpleNamespace(web=SimpleNamespace(uri=uri, title=title, domain=domain))


def support(*indices: int) -> Any:
    return SimpleNamespace(grounding_chunk_indices=list(indices), segment=None)


def response(
    *,
    text: str = "An answer.",
    chunks: list[Any] | None = None,
    supports: list[Any] | None = None,
    queries: list[str] | None = None,
    finish_reason: Any = "STOP",
) -> Any:
    return SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(parts=[SimpleNamespace(text=text)]),
                finish_reason=finish_reason,
                grounding_metadata=SimpleNamespace(
                    grounding_chunks=chunks or [],
                    grounding_supports=supports or [],
                    web_search_queries=queries or [],
                ),
            )
        ]
    )


# ------------------------------------------------------------------
# Harvesting
# ------------------------------------------------------------------


def test_text_is_joined_from_every_part() -> None:
    reply = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[SimpleNamespace(text="First."), SimpleNamespace(text="Second.")]
                ),
                finish_reason="STOP",
                grounding_metadata=None,
            )
        ]
    )

    text, _, _, _ = harvest_gemini_response(reply)

    assert text == "First.\n\nSecond."


def test_a_source_comes_only_from_a_grounding_chunk() -> None:
    text, sources, _, _ = harvest_gemini_response(
        response(text="See https://invented.example for details.", chunks=[chunk(REDIRECT)])
    )

    assert "invented.example" in text
    assert [source.url for source in sources] == [REDIRECT]


def test_only_supported_chunks_are_marked_cited() -> None:
    _, sources, _, _ = harvest_gemini_response(
        response(
            chunks=[chunk("https://a.example"), chunk("https://b.example")],
            supports=[support(1)],
        )
    )

    assert [(source.url, source.cited) for source in sources] == [
        ("https://a.example", False),
        ("https://b.example", True),
    ]


def test_a_chunk_with_no_uri_is_dropped_rather_than_guessed() -> None:
    _, sources, _, _ = harvest_gemini_response(
        response(chunks=[chunk(uri=None), chunk("https://ok.example")])
    )

    assert [source.url for source in sources] == ["https://ok.example"]


def test_the_title_falls_back_through_domain_to_the_url() -> None:
    _, sources, _, _ = harvest_gemini_response(
        response(chunks=[chunk("https://x.example", title=None, domain=None)])
    )

    assert sources[0].title == "https://x.example"


def test_search_count_comes_from_the_queries_grounding_ran() -> None:
    _, _, searches, _ = harvest_gemini_response(
        response(queries=["welspun revenue", "welspun exports"])
    )

    assert searches == 2


def test_a_missing_candidate_is_not_a_crash() -> None:
    assert harvest_gemini_response(SimpleNamespace(candidates=[])) == ("", [], 0, None)


def test_an_enum_finish_reason_is_reported_by_name() -> None:
    _, _, _, finish = harvest_gemini_response(
        response(finish_reason=SimpleNamespace(name="MAX_TOKENS"))
    )

    assert finish == "MAX_TOKENS"


# ------------------------------------------------------------------
# Stripping links nobody fetched
# ------------------------------------------------------------------
#
# An ungrounded Gemini call still tries to comply with the brief's "hyperlink
# every claim" instruction — from training-data recall, not a retrieved page.
# The result reads exactly like a cited source and is not one. These pin that
# every link loses its href and keeps its label, which is the one property
# that actually matters for a reader.


def test_a_confident_looking_link_loses_its_href() -> None:
    text = "Revenue grew 12% [FY25 results](https://example.com/results.pdf)."

    assert strip_unverified_links(text) == "Revenue grew 12% FY25 results."


def test_several_links_in_one_report_are_all_stripped() -> None:
    text = "[A](https://a.example) and [B](https://b.example) and [C](https://c.example)"

    assert strip_unverified_links(text) == "A and B and C"


def test_a_link_with_an_empty_label_leaves_no_stray_brackets() -> None:
    assert strip_unverified_links("See [](https://example.com) for more.") == "See  for more."


def test_prose_with_no_links_is_returned_unchanged() -> None:
    text = "Ordinary prose with no markup at all."

    assert strip_unverified_links(text) == text


def test_a_non_http_scheme_is_left_alone() -> None:
    # Not a case this feature can produce, but the pattern should not widen
    # to match schemes it was never written to filter.
    text = "[local file](file:///etc/passwd)"

    assert strip_unverified_links(text) == text


# ------------------------------------------------------------------
# Whether grounding is even offered
# ------------------------------------------------------------------
#
# `enabled` gates this independently of `web_search`, because on a project
# with no billing account grounding does not degrade — it is a flat 429 on
# every call. These pin the truth table so a future "just always pass
# web_search through" refactor cannot quietly re-enable that failure mode.


def test_grounding_is_offered_only_when_both_flags_agree() -> None:
    assert grounding_tools(web_search=True, enabled=True) is not None


def test_grounding_is_withheld_when_disabled_even_if_requested() -> None:
    assert grounding_tools(web_search=True, enabled=False) is None


def test_grounding_is_withheld_when_not_requested_even_if_enabled() -> None:
    assert grounding_tools(web_search=False, enabled=True) is None


def test_the_tool_offered_is_google_search() -> None:
    tools = grounding_tools(web_search=True, enabled=True)
    assert tools is not None
    assert tools[0].google_search is not None


# ------------------------------------------------------------------
# Message conversion
# ------------------------------------------------------------------


def test_the_assistant_role_becomes_model() -> None:
    contents = to_gemini_contents(
        [{"role": "user", "content": "Research them."}, {"role": "assistant", "content": "Done."}]
    )

    assert [content.role for content in contents] == ["user", "model"]
    assert contents[0].parts[0].text == "Research them."


def test_an_unexpected_role_is_treated_as_user() -> None:
    assert to_gemini_contents([{"role": "system", "content": "x"}])[0].role == "user"


# ------------------------------------------------------------------
# Telling a bad key from a bad request
# ------------------------------------------------------------------


def client_error(code: int, reason: str | None = None) -> Any:
    """A ClientError shaped like the ones Google actually returns."""
    payload: dict[str, Any] = {"error": {"code": code, "message": "no", "status": "X"}}
    if reason is not None:
        payload["error"]["details"] = [{"@type": "…/ErrorInfo", "reason": reason}]
    return SimpleNamespace(code=code, details=payload)


def test_an_invalid_key_is_recognised_despite_arriving_as_a_400() -> None:
    # The case that matters: Google answers a bad API key with 400
    # INVALID_ARGUMENT, so status alone would call this a bad request and tell
    # the operator to "try again" forever.
    assert is_credential_error(client_error(400, "API_KEY_INVALID")) is True


def test_a_genuine_bad_request_is_not_mistaken_for_a_bad_key() -> None:
    assert is_credential_error(client_error(400, "INVALID_VALUE")) is False
    assert is_credential_error(client_error(400)) is False


@pytest.mark.parametrize("code", [401, 403])
def test_the_conventional_auth_codes_still_count(code: int) -> None:
    assert is_credential_error(client_error(code)) is True


def test_a_details_payload_of_an_unexpected_shape_is_not_a_crash() -> None:
    assert is_credential_error(SimpleNamespace(code=400, details=None)) is False
    assert is_credential_error(SimpleNamespace(code=400, details={"error": "text"})) is False


# ------------------------------------------------------------------
# Redirect resolution
# ------------------------------------------------------------------


class StubProvider(GeminiResearchProvider):
    """The redirect resolver without the constructor's client and credential."""

    def __init__(self) -> None:
        # Deliberately skips super().__init__: that asserts a credential and
        # builds a genai client, neither of which redirect resolution touches.
        pass


async def resolve_with(
    handler: object, sources: list[ResearchSource], monkeypatch: pytest.MonkeyPatch
) -> tuple[ResearchSource, ...]:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    original = httpx.AsyncClient

    def client(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return original(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return await StubProvider()._resolve_sources(sources)


def redirecting(destination: str) -> object:
    """A transport that 302s the grounding host onward, like Google's does."""

    def handler(request: httpx.Request) -> httpx.Response:
        if GeminiResearchProvider.REDIRECT_HOST in str(request.url):
            return httpx.Response(302, headers={"Location": destination})
        return httpx.Response(200, text="the article")

    return handler


@pytest.mark.asyncio
async def test_a_redirect_is_followed_to_the_publisher_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = await resolve_with(
        redirecting("https://publisher.example/story"),
        [ResearchSource(title="publisher.example", url=REDIRECT)],
        monkeypatch,
    )

    assert [source.url for source in resolved] == ["https://publisher.example/story"]


@pytest.mark.asyncio
async def test_an_unresolvable_redirect_keeps_the_link_rather_than_dropping_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("nope", request=request)

    resolved = await resolve_with(
        handler, [ResearchSource(title="publisher.example", url=REDIRECT)], monkeypatch
    )

    assert [source.url for source in resolved] == [REDIRECT]


@pytest.mark.asyncio
async def test_a_real_url_is_never_fetched(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("a non-redirect source was fetched")

    resolved = await resolve_with(
        handler, [ResearchSource(title="t", url="https://direct.example/a")], monkeypatch
    )

    assert [source.url for source in resolved] == ["https://direct.example/a"]


@pytest.mark.asyncio
async def test_two_redirects_to_one_page_collapse_and_keep_the_citation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved = await resolve_with(
        redirecting("https://publisher.example/story"),
        [
            ResearchSource(title="publisher.example", url=f"{REDIRECT}-one", cited=False),
            ResearchSource(title="publisher.example", url=f"{REDIRECT}-two", cited=True),
        ],
        monkeypatch,
    )

    assert len(resolved) == 1
    assert resolved[0].cited is True


# ------------------------------------------------------------------
# Retrying a transient capacity error
# ------------------------------------------------------------------
#
# Every Flash model tried while building this provider recovered from a
# `ServerError` ("currently experiencing high demand … usually temporary")
# on a second attempt seconds later, with nothing changed on this end — the
# definition of worth one retry. A `ClientError` (quota, a bad credential)
# gets none: those are real states, not transients.


def server_error(code: int = 503, message: str = "busy") -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"error": {"code": code, "message": message}})


class _ScriptedModels:
    """Stands in for ``client.aio.models``, replaying outcomes in order."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def generate_content(self, **_: Any) -> Any:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def sender(outcomes: list[object]) -> tuple[StubProvider, _ScriptedModels]:
    provider = StubProvider()
    provider._model = "gemini-test"
    provider.CAPACITY_RETRY_DELAY_SECONDS = 0  # instance override: keep the test fast
    models = _ScriptedModels(outcomes)
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=models))
    return provider, models


@pytest.mark.asyncio
async def test_a_capacity_error_is_retried_and_then_succeeds() -> None:
    ok = SimpleNamespace(text="the report")
    provider, models = sender([server_error(), ok])

    result = await provider._send(contents=[], config=SimpleNamespace())

    assert result is ok
    assert models.calls == 2


@pytest.mark.asyncio
async def test_capacity_errors_beyond_the_retry_budget_still_surface() -> None:
    provider, models = sender([server_error(), server_error(), server_error()])

    with pytest.raises(AiTemporarilyUnavailableError):
        await provider._send(contents=[], config=SimpleNamespace())

    # CAPACITY_RETRIES=2 -> three attempts total, then it gives up.
    assert models.calls == provider.CAPACITY_RETRIES + 1


@pytest.mark.asyncio
async def test_a_quota_error_is_not_retried() -> None:
    quota = genai_errors.ClientError(429, {"error": {"code": 429, "message": "quota"}})
    provider, models = sender([quota, SimpleNamespace()])

    with pytest.raises(AiTemporarilyUnavailableError):
        await provider._send(contents=[], config=SimpleNamespace())

    assert models.calls == 1
