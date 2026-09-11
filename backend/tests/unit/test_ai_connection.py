"""The AI connection: configuration, error classification, the real-call test, status.

No network anywhere in this file. Each provider is given a scripted client in
place of the SDK's, so what is under test is *our* handling — which state a
failure maps to, what the check sends, what the status claims — not whether a
vendor is up today. The real round trip is verified by hand against a live key
(see docs/CRM_IMPLEMENTATION_PROGRESS.md, Checkpoint 1), never as a unit test.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from google.genai import errors as genai_errors
from pydantic import SecretStr
from structlog.testing import capture_logs

from app.core.config import Settings
from app.platform.ai import service as ai_service
from app.platform.ai.provider import (
    HEALTH_CHECK_MAX_TOKENS,
    HEALTH_CHECK_PROMPT,
    AiAuthenticationError,
    AiConnectionState,
    AiNotConfiguredError,
    AnthropicResearchProvider,
    ConnectionCheck,
    GeminiResearchProvider,
    ResearchResult,
    build_provider,
    classify_anthropic_error,
    classify_gemini_error,
)
from app.platform.ai.service import (
    CONNECTION_VERDICT_TTL_SECONDS,
    AiConnectionService,
    AiGatewayService,
    credential_fingerprint,
)

#: Distinctive enough that finding it anywhere it should not be is unambiguous.
ANTHROPIC_SECRET = "sk-ant-test-DO-NOT-LEAK-7f3a9c"
GEMINI_SECRET = "AIza-test-DO-NOT-LEAK-51b2e8"

ORG = uuid.UUID("00000000-0000-0000-0000-00000000a001")


def configure(settings: Settings, **update: Any) -> Settings:
    """Settings with the AI fields replaced, and both keys cleared unless given."""
    values: dict[str, Any] = {"anthropic_api_key": None, "gemini_api_key": None}
    values.update(update)
    for name in ("anthropic_api_key", "gemini_api_key"):
        if isinstance(values[name], str):
            values[name] = SecretStr(values[name])
    return settings.model_copy(update=values)


@pytest.fixture
def anthropic_settings(settings: Settings) -> Settings:
    return configure(settings, ai_provider="anthropic", anthropic_api_key=ANTHROPIC_SECRET)


@pytest.fixture
def gemini_settings(settings: Settings) -> Settings:
    return configure(settings, ai_provider="gemini", gemini_api_key=GEMINI_SECRET)


# ---------------------------------------------------------------------------
# Configuration: which provider, and why not
# ---------------------------------------------------------------------------


def test_no_key_at_all_is_a_missing_credential(settings: Settings) -> None:
    configured = configure(settings)

    assert configured.ai_configured is False
    assert configured.ai_configuration_issue == "missing_credential"


def test_a_gemini_key_under_the_default_provider_is_not_configured(settings: Settings) -> None:
    """The root cause this checkpoint fixed, pinned.

    ``AI_PROVIDER`` defaults to ``anthropic``. A deployment that sets only
    ``GEMINI_API_KEY`` therefore has no key for the provider it will call —
    and must say *that*, not merely "not configured".
    """
    configured = configure(settings, gemini_api_key=GEMINI_SECRET)

    assert configured.ai_provider == "anthropic"
    assert configured.ai_configured is False
    assert configured.ai_configuration_issue == "credential_for_other_provider"


def test_the_reverse_mismatch_is_reported_the_same_way(settings: Settings) -> None:
    configured = configure(settings, ai_provider="gemini", anthropic_api_key=ANTHROPIC_SECRET)

    assert configured.ai_configured is False
    assert configured.ai_configuration_issue == "credential_for_other_provider"


def test_selecting_gemini_with_its_key_configures_it(gemini_settings: Settings) -> None:
    assert gemini_settings.ai_configured is True
    assert gemini_settings.ai_configuration_issue is None
    assert gemini_settings.ai_active_model == gemini_settings.gemini_model


def test_a_blank_key_does_not_count(settings: Settings) -> None:
    configured = configure(settings, ai_provider="gemini", gemini_api_key="   ")

    assert configured.ai_configured is False
    assert configured.ai_configuration_issue == "missing_credential"


def test_build_provider_follows_ai_provider(
    anthropic_settings: Settings, gemini_settings: Settings
) -> None:
    assert isinstance(build_provider(anthropic_settings), AnthropicResearchProvider)
    assert isinstance(build_provider(gemini_settings), GeminiResearchProvider)


def test_build_provider_refuses_without_the_selected_key(settings: Settings) -> None:
    with pytest.raises(AiNotConfiguredError):
        build_provider(configure(settings, gemini_api_key=GEMINI_SECRET))


# ---------------------------------------------------------------------------
# Classifying provider failures
# ---------------------------------------------------------------------------

ANTHROPIC_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def anthropic_status(cls: type[anthropic.APIStatusError], code: int) -> anthropic.APIStatusError:
    return cls(
        message="refused",
        response=httpx.Response(code, request=ANTHROPIC_REQUEST),
        body=None,
    )


@pytest.mark.parametrize(
    ("error", "state", "code"),
    [
        (
            anthropic_status(anthropic.AuthenticationError, 401),
            AiConnectionState.AUTHENTICATION_ERROR,
            "credential_rejected",
        ),
        (
            anthropic_status(anthropic.PermissionDeniedError, 403),
            AiConnectionState.AUTHENTICATION_ERROR,
            "credential_rejected",
        ),
        (
            anthropic_status(anthropic.RateLimitError, 429),
            AiConnectionState.PROVIDER_ERROR,
            "rate_limited",
        ),
        (
            anthropic_status(anthropic.NotFoundError, 404),
            AiConnectionState.PROVIDER_ERROR,
            "model_not_found",
        ),
        (
            anthropic_status(anthropic.InternalServerError, 500),
            AiConnectionState.PROVIDER_ERROR,
            "provider_unavailable",
        ),
        (
            anthropic_status(anthropic.BadRequestError, 400),
            AiConnectionState.PROVIDER_ERROR,
            "http_400",
        ),
        (
            anthropic.APITimeoutError(request=ANTHROPIC_REQUEST),
            AiConnectionState.TIMEOUT,
            "timeout",
        ),
        (
            anthropic.APIConnectionError(request=ANTHROPIC_REQUEST),
            AiConnectionState.PROVIDER_ERROR,
            "connection_failed",
        ),
        (TimeoutError(), AiConnectionState.TIMEOUT, "timeout"),
        (ValueError("surprise"), AiConnectionState.UNKNOWN_ERROR, "unexpected_error"),
    ],
)
def test_anthropic_failures_map_to_a_state(
    error: BaseException, state: AiConnectionState, code: str
) -> None:
    assert classify_anthropic_error(error) == (state, code)


def gemini_client_error(code: int, reason: str | None = None) -> genai_errors.ClientError:
    payload: dict[str, Any] = {"error": {"code": code, "message": "no", "status": "X"}}
    if reason is not None:
        payload["error"]["details"] = [{"@type": "…/ErrorInfo", "reason": reason}]
    return genai_errors.ClientError(code, payload)


@pytest.mark.parametrize(
    ("error", "state", "code"),
    [
        # Google answers a bad key with 400, not 401 — the case that matters.
        (
            gemini_client_error(400, "API_KEY_INVALID"),
            AiConnectionState.AUTHENTICATION_ERROR,
            "credential_rejected",
        ),
        (gemini_client_error(403), AiConnectionState.AUTHENTICATION_ERROR, "credential_rejected"),
        (gemini_client_error(429), AiConnectionState.PROVIDER_ERROR, "rate_limited"),
        (gemini_client_error(404), AiConnectionState.PROVIDER_ERROR, "model_not_found"),
        (gemini_client_error(400, "INVALID_VALUE"), AiConnectionState.PROVIDER_ERROR, "http_400"),
        (
            genai_errors.ServerError(503, {"error": {"code": 503, "message": "busy"}}),
            AiConnectionState.PROVIDER_ERROR,
            "provider_unavailable",
        ),
        (TimeoutError(), AiConnectionState.TIMEOUT, "timeout"),
        (httpx.ReadTimeout("slow"), AiConnectionState.TIMEOUT, "timeout"),
        (httpx.ConnectError("down"), AiConnectionState.PROVIDER_ERROR, "connection_failed"),
        (RuntimeError("surprise"), AiConnectionState.UNKNOWN_ERROR, "unexpected_error"),
    ],
)
def test_gemini_failures_map_to_a_state(
    error: BaseException, state: AiConnectionState, code: str
) -> None:
    assert classify_gemini_error(error) == (state, code)


# ---------------------------------------------------------------------------
# The connection check itself, against scripted clients
# ---------------------------------------------------------------------------


class ScriptedGeminiModels:
    """Stands in for ``client.aio.models``; answers, raises or stalls."""

    def __init__(self, outcome: object, *, delay: float = 0.0) -> None:
        self.outcome = outcome
        self.delay = delay
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def gemini_with(settings: Settings, models: ScriptedGeminiModels) -> GeminiResearchProvider:
    provider = GeminiResearchProvider(settings)
    provider._client = SimpleNamespace(aio=SimpleNamespace(models=models))  # type: ignore[assignment]
    return provider


class ScriptedAnthropic:
    """Stands in for ``AsyncAnthropic``: records ``with_options`` and ``create``."""

    def __init__(self, outcome: object, *, delay: float = 0.0) -> None:
        self.outcome = outcome
        self.delay = delay
        self.options: dict[str, Any] = {}
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def with_options(self, **options: Any) -> ScriptedAnthropic:
        self.options = options
        return self

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def anthropic_with(settings: Settings, client: ScriptedAnthropic) -> AnthropicResearchProvider:
    provider = AnthropicResearchProvider(settings)
    provider._client = client  # type: ignore[assignment]
    return provider


@pytest.mark.asyncio
async def test_gemini_check_sends_one_minimal_request_and_reports_the_model(
    gemini_settings: Settings,
) -> None:
    models = ScriptedGeminiModels(
        SimpleNamespace(candidates=[SimpleNamespace()], model_version="gemini-flash-lite-001")
    )

    check = await gemini_with(gemini_settings, models).check(timeout_seconds=5)

    assert check.state is AiConnectionState.AVAILABLE
    assert check.model == "gemini-flash-lite-001"
    assert check.latency_ms is not None and check.latency_ms >= 0
    assert check.error_code is None
    [call] = models.calls
    assert call["model"] == gemini_settings.gemini_model
    assert call["contents"] == HEALTH_CHECK_PROMPT
    assert call["config"].max_output_tokens == HEALTH_CHECK_MAX_TOKENS
    # No grounding: a connection test must not spend a search, or hit the 429
    # an unbilled project returns for one.
    assert call["config"].tools is None


@pytest.mark.asyncio
async def test_a_gemini_reply_with_no_candidate_is_not_available(
    gemini_settings: Settings,
) -> None:
    models = ScriptedGeminiModels(SimpleNamespace(candidates=[]))

    check = await gemini_with(gemini_settings, models).check(timeout_seconds=5)

    assert check.state is AiConnectionState.PROVIDER_ERROR
    assert check.error_code == "empty_response"


@pytest.mark.asyncio
async def test_a_refused_gemini_key_is_an_authentication_error(
    gemini_settings: Settings,
) -> None:
    models = ScriptedGeminiModels(gemini_client_error(400, "API_KEY_INVALID"))

    check = await gemini_with(gemini_settings, models).check(timeout_seconds=5)

    assert check.state is AiConnectionState.AUTHENTICATION_ERROR
    assert check.error_code == "credential_rejected"


@pytest.mark.asyncio
async def test_a_gemini_call_that_outlives_the_timeout_is_a_timeout(
    gemini_settings: Settings,
) -> None:
    models = ScriptedGeminiModels(SimpleNamespace(candidates=[SimpleNamespace()]), delay=5)

    check = await gemini_with(gemini_settings, models).check(timeout_seconds=0.05)

    assert check.state is AiConnectionState.TIMEOUT
    assert check.error_code == "timeout"


@pytest.mark.asyncio
async def test_anthropic_check_is_one_small_unretried_call(
    anthropic_settings: Settings,
) -> None:
    client = ScriptedAnthropic(SimpleNamespace(model="claude-opus-5-20260101", content=[]))

    check = await anthropic_with(anthropic_settings, client).check(timeout_seconds=7)

    assert check.state is AiConnectionState.AVAILABLE
    assert check.model == "claude-opus-5-20260101"
    # Retries off: a retried success would hide the failure being tested for.
    assert client.options == {"timeout": 7, "max_retries": 0}
    [call] = client.calls
    assert call["model"] == anthropic_settings.ai_model
    assert call["max_tokens"] == HEALTH_CHECK_MAX_TOKENS
    assert call["messages"] == [{"role": "user", "content": HEALTH_CHECK_PROMPT}]
    assert "tools" not in call


@pytest.mark.asyncio
async def test_a_refused_anthropic_key_is_an_authentication_error(
    anthropic_settings: Settings,
) -> None:
    client = ScriptedAnthropic(anthropic_status(anthropic.AuthenticationError, 401))

    check = await anthropic_with(anthropic_settings, client).check(timeout_seconds=5)

    assert check.state is AiConnectionState.AUTHENTICATION_ERROR


@pytest.mark.asyncio
async def test_an_anthropic_call_that_outlives_the_timeout_is_a_timeout(
    anthropic_settings: Settings,
) -> None:
    client = ScriptedAnthropic(SimpleNamespace(model="m", content=[]), delay=5)

    check = await anthropic_with(anthropic_settings, client).check(timeout_seconds=0.05)

    assert check.state is AiConnectionState.TIMEOUT


# ---------------------------------------------------------------------------
# A refused key on the research path is no longer reported as "not configured"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_with_a_refused_gemini_key_raises_authentication_failed(
    gemini_settings: Settings,
) -> None:
    provider = gemini_with(gemini_settings, ScriptedGeminiModels(gemini_client_error(401)))

    with pytest.raises(AiAuthenticationError) as raised:
        await provider._send(contents=[], config=SimpleNamespace())  # type: ignore[arg-type]

    assert raised.value.code == "ai_authentication_failed"


@pytest.mark.asyncio
async def test_research_with_a_refused_anthropic_key_raises_authentication_failed(
    anthropic_settings: Settings,
) -> None:
    provider = AnthropicResearchProvider(anthropic_settings)

    def refuse(**_: Any) -> Any:
        raise anthropic_status(anthropic.AuthenticationError, 401)

    provider._client = SimpleNamespace(  # type: ignore[assignment]
        beta=SimpleNamespace(messages=SimpleNamespace(stream=refuse))
    )

    with pytest.raises(AiAuthenticationError):
        await provider._send(system="s", messages=[], tools=[])


# ---------------------------------------------------------------------------
# Status and the recorded verdict
# ---------------------------------------------------------------------------


class FakeRedis:
    """The two commands the verdict uses, in memory."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.expiry: dict[str, int | None] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        self.expiry[key] = ex


class BrokenRedis:
    async def get(self, key: str) -> str | None:
        raise ConnectionError("redis is down")

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        raise ConnectionError("redis is down")


class StubCheck:
    """A provider whose connection check returns a scripted verdict."""

    def __init__(self, check: ConnectionCheck) -> None:
        self.result = check
        self.calls = 0

    async def check(self, *, timeout_seconds: float) -> ConnectionCheck:
        self.calls += 1
        return self.result


def service(
    settings: Settings, redis: object | None, provider: StubCheck | None = None
) -> AiConnectionService:
    return AiConnectionService(settings=settings, redis=redis, provider=provider)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_status_without_a_key_is_not_configured_and_says_why(settings: Settings) -> None:
    status = await service(configure(settings, gemini_api_key=GEMINI_SECRET), FakeRedis()).status()

    assert status.configured is False
    assert status.state is AiConnectionState.NOT_CONFIGURED
    assert status.issue == "credential_for_other_provider"
    assert status.provider == "anthropic"


@pytest.mark.asyncio
async def test_a_key_alone_is_configured_never_available(gemini_settings: Settings) -> None:
    status = await service(gemini_settings, FakeRedis()).status()

    assert status.state is AiConnectionState.CONFIGURED
    assert status.checked_at is None


@pytest.mark.asyncio
async def test_a_successful_check_makes_the_status_available(gemini_settings: Settings) -> None:
    redis = FakeRedis()
    stub = StubCheck(
        ConnectionCheck(state=AiConnectionState.AVAILABLE, model="gemini-x", latency_ms=240)
    )
    connection = service(gemini_settings, redis, stub)

    check = await connection.check(organization_id=ORG, actor_id=None)
    status = await connection.status()

    assert check.state is AiConnectionState.AVAILABLE
    assert stub.calls == 1
    assert status.state is AiConnectionState.AVAILABLE
    assert status.check_source == "health_check"
    assert status.latency_ms == 240
    assert status.checked_at == check.checked_at
    assert list(redis.expiry.values()) == [CONNECTION_VERDICT_TTL_SECONDS]


@pytest.mark.asyncio
async def test_a_failed_check_is_what_the_status_reports(gemini_settings: Settings) -> None:
    redis = FakeRedis()
    stub = StubCheck(
        ConnectionCheck(
            state=AiConnectionState.AUTHENTICATION_ERROR, error_code="credential_rejected"
        )
    )

    await service(gemini_settings, redis, stub).check(organization_id=ORG, actor_id=None)
    status = await service(gemini_settings, redis).status()

    assert status.state is AiConnectionState.AUTHENTICATION_ERROR
    assert status.error_code == "credential_rejected"


@pytest.mark.asyncio
async def test_replacing_the_key_discards_the_old_verdict(gemini_settings: Settings) -> None:
    """The usual fix for a refused key must not keep reporting the refusal."""
    redis = FakeRedis()
    stub = StubCheck(ConnectionCheck(state=AiConnectionState.AUTHENTICATION_ERROR))
    await service(gemini_settings, redis, stub).check(organization_id=ORG, actor_id=None)

    rotated = configure(gemini_settings, ai_provider="gemini", gemini_api_key="AIza-new-key")
    status = await service(rotated, redis).status()

    assert status.state is AiConnectionState.CONFIGURED


@pytest.mark.asyncio
async def test_changing_the_model_discards_the_old_verdict(gemini_settings: Settings) -> None:
    redis = FakeRedis()
    stub = StubCheck(ConnectionCheck(state=AiConnectionState.AVAILABLE))
    await service(gemini_settings, redis, stub).check(organization_id=ORG, actor_id=None)

    other_model = gemini_settings.model_copy(update={"gemini_model": "gemini-other"})

    assert (await service(other_model, redis).status()).state is AiConnectionState.CONFIGURED


@pytest.mark.asyncio
async def test_checking_an_unconfigured_deployment_calls_nothing(settings: Settings) -> None:
    stub = StubCheck(ConnectionCheck(state=AiConnectionState.AVAILABLE))

    check = await service(configure(settings), FakeRedis(), stub).check(
        organization_id=ORG, actor_id=None
    )

    assert check.state is AiConnectionState.NOT_CONFIGURED
    assert check.error_code == "missing_credential"
    assert stub.calls == 0


@pytest.mark.asyncio
async def test_status_fails_open_when_redis_is_down(gemini_settings: Settings) -> None:
    stub = StubCheck(ConnectionCheck(state=AiConnectionState.AVAILABLE))
    connection = service(gemini_settings, BrokenRedis(), stub)

    check = await connection.check(organization_id=ORG, actor_id=None)

    assert check.state is AiConnectionState.AVAILABLE
    assert (await connection.status()).state is AiConnectionState.CONFIGURED


@pytest.mark.asyncio
async def test_a_malformed_verdict_is_no_evidence(gemini_settings: Settings) -> None:
    redis = FakeRedis()
    await service(
        gemini_settings,
        redis,
        StubCheck(ConnectionCheck(state=AiConnectionState.AVAILABLE)),
    ).check(organization_id=ORG, actor_id=None)
    [key] = redis.store
    redis.store[key] = json.dumps({"state": "NOT_A_STATE"})

    assert (await service(gemini_settings, redis).status()).state is AiConnectionState.CONFIGURED


# ---------------------------------------------------------------------------
# Research turns record what they prove
# ---------------------------------------------------------------------------


class ScriptedResearch:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome

    async def run(self, **_: Any) -> ResearchResult:
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        assert isinstance(self.outcome, ResearchResult)
        return self.outcome


@pytest.fixture
def no_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gateway audits every turn; these tests are about the verdict, not the trail."""

    class _Recorder:
        async def record(self, **_: Any) -> None:
            return None

    monkeypatch.setattr(ai_service, "audit_for_session", lambda _session: _Recorder())


@pytest.mark.asyncio
@pytest.mark.usefixtures("no_audit")
async def test_a_completed_research_turn_proves_the_connection(gemini_settings: Settings) -> None:
    redis = FakeRedis()
    gateway = AiGatewayService(
        settings=gemini_settings,
        session=None,  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        provider=ScriptedResearch(ResearchResult(text="report", model="gemini-x")),
    )

    await gateway.run_turn(
        organization_id=ORG, actor_id=None, system="s", messages=[], feature="test"
    )
    status = await service(gemini_settings, redis).status()

    assert status.state is AiConnectionState.AVAILABLE
    assert status.check_source == "feature_call"


@pytest.mark.asyncio
async def test_a_refused_research_turn_is_recorded_and_still_raised(
    gemini_settings: Settings,
) -> None:
    redis = FakeRedis()
    gateway = AiGatewayService(
        settings=gemini_settings,
        session=None,  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        provider=ScriptedResearch(AiAuthenticationError()),
    )

    with pytest.raises(AiAuthenticationError):
        await gateway.run_turn(
            organization_id=ORG, actor_id=None, system="s", messages=[], feature="test"
        )

    status = await service(gemini_settings, redis).status()
    assert status.state is AiConnectionState.AUTHENTICATION_ERROR
    assert status.check_source == "feature_call"


# ---------------------------------------------------------------------------
# No secret anywhere
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_trace_of_the_key_in_redis_logs_or_results(gemini_settings: Settings) -> None:
    redis = FakeRedis()
    stub = StubCheck(ConnectionCheck(state=AiConnectionState.AVAILABLE, model="gemini-x"))

    with capture_logs() as logs:
        check = await service(gemini_settings, redis, stub).check(
            organization_id=ORG, actor_id=None
        )
        status = await service(gemini_settings, redis).status()

    assert any(entry["event"] == "ai_connection_checked" for entry in logs)
    haystack = " ".join([repr(check), repr(status), repr(logs), repr(redis.store)])
    assert GEMINI_SECRET not in haystack
    # The cache key carries a fingerprint, which must not be the key either.
    assert credential_fingerprint(gemini_settings) not in GEMINI_SECRET
