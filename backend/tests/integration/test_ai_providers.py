"""AI provider credentials: storage, verification, and what must never leak.

The connectivity check is the one thing stubbed — it is a live call to
Anthropic, and a test suite that needed a real API key would be a test suite
nobody could run. Everything else is real: the encryption, the database, RLS,
the permission checks and the gateway's resolution order.

Weighted deliberately towards the refusals. A suite that only proved a
credential can be saved would pass just as happily against an implementation
that returned the key in every response.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application import create_app
from app.core.config import Settings
from app.platform.ai import router as ai_router
from app.platform.ai.provider import CredentialCheck
from tests.integration.conftest import ApiSession, Tenant, scope_session_to

pytestmark = pytest.mark.integration

PROVIDER = "anthropic"
GEMINI = "gemini"
#: Long enough to pass the length guard; the value itself is never real.
FAKE_KEY = "sk-ant-api03-test-key-0123456789abcdefghij"
OTHER_KEY = "sk-ant-api03-other-key-9876543210zyxwvutsr"


class StubCheck:
    """Stands in for the live provider call, and records what it was given.

    Substituted for the registry's ``verify_credential`` rather than a vendor
    function, so it covers both providers and so adding a third does not need a
    second stub.
    """

    def __init__(self) -> None:
        self.ok = True
        self.error: str | None = None
        self.calls: list[str] = []
        #: ``(provider, model)`` per call, so a test can assert the right
        #: vendor and the right model were dispatched to.
        self.dispatched: list[tuple[str, str]] = []

    async def __call__(
        self, *, provider: str, api_key: str, model: str, **_: object
    ) -> CredentialCheck:
        self.calls.append(api_key)
        self.dispatched.append((provider, model))
        return CredentialCheck(ok=self.ok, error=self.error, model=model if self.ok else None)


@pytest.fixture
def checker() -> StubCheck:
    return StubCheck()


#: Every deployment-wide vendor key resolution consults. Cleared together, and
#: derived from one list rather than named ad hoc: a third vendor added to
#: ``_from_environment`` without being added here would silently connect every
#: "not configured" test through the fallback, and the failure would look like
#: a bug in the feature rather than a gap in the fixture. That is precisely
#: what happened when Gemini was added, so the list now lives in one place.
ENVIRONMENT_KEY_FIELDS = ("anthropic_api_key", "gemini_api_key")


@pytest.fixture
def encrypting_settings(integration_settings: Settings) -> Settings:
    """Settings with a real encryption key and **no** environment credential.

    Both halves matter. The key is what makes storage possible at all; the
    absent vendor keys are what make the fallback tests meaningful, since a
    deployment key would mask every "not configured" case — including on a
    developer machine that happens to have one exported.
    """
    return integration_settings.model_copy(
        update={
            "ai_credential_encryption_key": SecretStr(Fernet.generate_key().decode()),
            **dict.fromkeys(ENVIRONMENT_KEY_FIELDS, None),
        }
    )


@pytest.fixture
def api_app(
    encrypting_settings: Settings, checker: StubCheck, monkeypatch: pytest.MonkeyPatch
) -> FastAPI:
    """The real application with only the network call replaced."""
    monkeypatch.setattr(ai_router, "verify_credential", checker)
    return create_app(encrypting_settings)


@pytest.fixture
def client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as test_client:
        yield test_client


def _session(client: TestClient, settings: Settings, email: str, org: uuid.UUID) -> ApiSession:
    session = ApiSession(client, settings.api_prefix)
    session.login(email, organization_id=org)
    return session


# Independent sessions, for the reason ``test_market_insights`` gives: the
# conftest fixtures share one ApiSession, so a test naming two would silently
# run as whichever authenticated last.


@pytest.fixture
def alpha_admin(
    client: TestClient, encrypting_settings: Settings, alpha: Tenant
) -> ApiSession:
    return _session(client, encrypting_settings, alpha.admin.email, alpha.organization_id)


@pytest.fixture
def alpha_member(
    client: TestClient, encrypting_settings: Settings, alpha: Tenant
) -> ApiSession:
    return _session(client, encrypting_settings, alpha.member.email, alpha.organization_id)


@pytest.fixture
def beta_admin(client: TestClient, encrypting_settings: Settings, beta: Tenant) -> ApiSession:
    return _session(client, encrypting_settings, beta.admin.email, beta.organization_id)


def _save(
    session: ApiSession, key: str = FAKE_KEY, provider: str = PROVIDER
) -> Response:
    return session.request("PUT", f"/ai/providers/{provider}", json={"api_key": key})


# --- Configuring ------------------------------------------------------------


def test_a_credential_can_be_stored_and_is_verified_in_the_same_request(
    alpha_admin: ApiSession, checker: StubCheck
) -> None:
    """Saving and testing are one action, so a key is never merely 'accepted'."""
    response = _save(alpha_admin)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["provider"]["configured"] is True
    assert body["provider"]["status"] == "CONNECTED"
    # The stub received the real key — the round trip through encryption and
    # back is what this asserts, not merely that a row was written.
    assert checker.calls == [FAKE_KEY]


def test_the_providers_list_starts_unconfigured(alpha_admin: ApiSession) -> None:
    response = alpha_admin.get("/ai/providers")

    assert response.status_code == 200
    body = response.json()
    assert body["storage_available"] is True
    assert body["using_environment_fallback"] is False
    assert [row["provider"] for row in body["providers"]] == [PROVIDER, GEMINI]
    assert body["providers"][0]["configured"] is False


def test_an_unsupported_provider_is_refused(alpha_admin: ApiSession) -> None:
    """The allow-list is the catalogue; nothing else is configurable."""
    response = _save(alpha_admin, provider="mistral")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unsupported_ai_provider"


def test_each_provider_is_verified_against_its_own_model(
    alpha_admin: ApiSession, checker: StubCheck
) -> None:
    """Vendors name their own models, so dispatch must carry the right one.

    Checking a Gemini key against ``claude-opus-5`` would fail at the provider
    with a confusing "model not found" — and, worse, would mark a perfectly
    good credential INVALID.
    """
    _save(alpha_admin, provider=PROVIDER)
    _save(alpha_admin, key=OTHER_KEY, provider=GEMINI)

    dispatched = dict(checker.dispatched)
    assert dispatched[PROVIDER].startswith("claude")
    assert dispatched[GEMINI].startswith("gemini")


def test_two_providers_can_be_configured_and_one_chosen(
    alpha_admin: ApiSession,
) -> None:
    """Both may be stored; exactly one is the default the gateway calls."""
    _save(alpha_admin, provider=PROVIDER)
    _save(alpha_admin, key=OTHER_KEY, provider=GEMINI)

    body = alpha_admin.post(f"/ai/providers/{GEMINI}/default").json()

    chosen = {row["provider"]: row["is_default"] for row in body["providers"]}
    assert chosen == {PROVIDER: False, GEMINI: True}


def test_the_status_model_follows_the_chosen_provider(
    alpha_admin: ApiSession,
) -> None:
    """An organization on Gemini must not be told it is running Claude."""
    _save(alpha_admin, key=OTHER_KEY, provider=GEMINI)

    assert alpha_admin.get("/ai/status").json()["model"].startswith("gemini")


def test_an_obviously_invalid_key_is_refused_before_any_network_call(
    alpha_admin: ApiSession, checker: StubCheck
) -> None:
    response = _save(alpha_admin, key="short")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_ai_credential"
    assert checker.calls == []


def test_a_rejected_key_is_stored_as_invalid_rather_than_connected(
    alpha_admin: ApiSession, checker: StubCheck
) -> None:
    """Only a real provider acceptance may produce CONNECTED."""
    checker.ok = False
    checker.error = "The provider rejected this API key."

    response = _save(alpha_admin)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["provider"]["status"] == "INVALID"
    assert body["provider"]["last_test_error"] == "The provider rejected this API key."


def test_replacing_a_key_resets_its_verified_status(
    alpha_admin: ApiSession, checker: StubCheck
) -> None:
    """A new key invalidates what the last test proved about the old one."""
    _save(alpha_admin)
    checker.ok = False
    checker.error = "The provider rejected this API key."

    body = _save(alpha_admin, key=OTHER_KEY).json()

    assert body["provider"]["status"] == "INVALID"
    assert checker.calls[-1] == OTHER_KEY


# --- Never leaking the key --------------------------------------------------


def test_no_response_ever_contains_the_key(alpha_admin: ApiSession) -> None:
    """The property the whole feature rests on, asserted against raw text.

    Checked on the serialised body rather than a parsed field, so a key leaking
    through a field nobody thought to look at still fails this.
    """
    save = _save(alpha_admin)
    listed = alpha_admin.get("/ai/providers")
    tested = alpha_admin.post(f"/ai/providers/{PROVIDER}/test")

    for response in (save, listed, tested):
        assert FAKE_KEY not in response.text
        # Not even the distinctive tail beyond the four masked characters.
        assert "0123456789abcdefghij"[:-4] not in response.text


def test_the_masked_key_shows_only_the_last_four_characters(
    alpha_admin: ApiSession,
) -> None:
    body = _save(alpha_admin).json()

    masked = body["provider"]["masked_key"]
    assert masked.endswith(FAKE_KEY[-4:])
    assert FAKE_KEY[:-4] not in masked


async def test_the_key_is_encrypted_at_rest(
    alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The database must not contain the plaintext anywhere in the row."""
    _save(alpha_admin)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        row = (
            await session.execute(
                text(
                    "SELECT secret_ciphertext, masked_key, key_fingerprint "
                    "FROM platform.ai_provider_credentials "
                    "WHERE organization_id = :org"
                ),
                {"org": alpha.organization_id},
            )
        ).one()

    ciphertext, masked, fingerprint = row
    assert FAKE_KEY not in ciphertext
    assert FAKE_KEY not in masked
    assert FAKE_KEY not in fingerprint
    # Fernet tokens carry a recognisable version prefix; asserting it catches
    # the case where "encryption" silently degraded to storing the value.
    assert ciphertext.startswith("gAAAAA")


# --- Authorization ----------------------------------------------------------


def test_an_ordinary_member_cannot_read_providers(alpha_member: ApiSession) -> None:
    response = alpha_member.get("/ai/providers")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_an_ordinary_member_cannot_store_a_credential(
    alpha_member: ApiSession, checker: StubCheck
) -> None:
    """And the refusal is effective, not merely a status code."""
    response = _save(alpha_member)

    assert response.status_code == 403
    assert checker.calls == []


def test_an_ordinary_member_cannot_delete_a_credential(
    alpha_member: ApiSession,
) -> None:
    response = alpha_member.request("DELETE", f"/ai/providers/{PROVIDER}")

    assert response.status_code == 403


def test_configuring_providers_requires_authentication(
    client: TestClient, encrypting_settings: Settings
) -> None:
    response = client.get(f"{encrypting_settings.api_prefix}/ai/providers")

    assert response.status_code == 401


def test_any_member_may_still_ask_whether_ai_is_connected(
    alpha_member: ApiSession,
) -> None:
    """Status is not admin-gated: a user needs to know why a screen is empty."""
    response = alpha_member.get("/ai/status")

    assert response.status_code == 200
    assert response.json()["configured"] is False


# --- Tenant isolation -------------------------------------------------------


def test_one_organizations_credential_is_invisible_to_another(
    alpha_admin: ApiSession, beta_admin: ApiSession
) -> None:
    _save(alpha_admin)

    body = beta_admin.get("/ai/providers").json()

    assert body["providers"][0]["configured"] is False
    assert body["providers"][0]["masked_key"] is None


def test_one_organizations_credential_does_not_connect_another(
    alpha_admin: ApiSession, beta_admin: ApiSession
) -> None:
    """Isolation of the *effect*, not just of the listing."""
    _save(alpha_admin)

    assert alpha_admin.get("/ai/status").json()["configured"] is True
    assert beta_admin.get("/ai/status").json()["configured"] is False


def test_one_organization_cannot_delete_anothers_credential(
    alpha_admin: ApiSession, beta_admin: ApiSession
) -> None:
    _save(alpha_admin)

    response = beta_admin.request("DELETE", f"/ai/providers/{PROVIDER}")

    assert response.status_code == 404
    # Alpha's is untouched.
    assert alpha_admin.get("/ai/providers").json()["providers"][0]["configured"] is True


# --- Status, selection and removal ------------------------------------------


def test_storing_a_credential_connects_the_organization(
    alpha_admin: ApiSession,
) -> None:
    assert alpha_admin.get("/ai/status").json()["configured"] is False

    _save(alpha_admin)

    status = alpha_admin.get("/ai/status").json()
    assert status["configured"] is True
    assert status["model"]


def test_a_rejected_credential_leaves_the_organization_disconnected(
    alpha_admin: ApiSession, checker: StubCheck
) -> None:
    """INVALID is skipped by resolution, so status stays honest."""
    checker.ok = False
    checker.error = "The provider rejected this API key."

    _save(alpha_admin)

    assert alpha_admin.get("/ai/status").json()["configured"] is False


def test_removing_a_credential_disconnects_the_organization(
    alpha_admin: ApiSession,
) -> None:
    _save(alpha_admin)

    removed = alpha_admin.request("DELETE", f"/ai/providers/{PROVIDER}")

    assert removed.status_code == 200
    assert removed.json()["providers"][0]["configured"] is False
    assert alpha_admin.get("/ai/status").json()["configured"] is False


def test_removing_a_credential_that_does_not_exist_is_a_404(
    alpha_admin: ApiSession,
) -> None:
    response = alpha_admin.request("DELETE", f"/ai/providers/{PROVIDER}")

    assert response.status_code == 404


def test_a_stored_credential_can_be_retested(
    alpha_admin: ApiSession, checker: StubCheck
) -> None:
    """Re-testing decrypts and calls again, without the key being resupplied."""
    _save(alpha_admin)
    checker.calls.clear()

    response = alpha_admin.post(f"/ai/providers/{PROVIDER}/test")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    # Proof the round trip through storage works: the stub saw the original key
    # although this request carried no body at all.
    assert checker.calls == [FAKE_KEY]


def test_testing_an_unconfigured_provider_is_a_404(alpha_admin: ApiSession) -> None:
    response = alpha_admin.post(f"/ai/providers/{PROVIDER}/test")

    assert response.status_code == 404


def test_a_stored_credential_is_the_active_one(alpha_admin: ApiSession) -> None:
    _save(alpha_admin)

    body = alpha_admin.post(f"/ai/providers/{PROVIDER}/default").json()

    assert body["providers"][0]["is_default"] is True


# --- The environment fallback -----------------------------------------------


def test_the_environment_key_connects_an_organization_that_configured_nothing(
    client: TestClient, integration_settings: Settings, alpha: Tenant, checker: StubCheck
) -> None:
    """Bootstrapping still works: a deployment key needs no configuration.

    Built on its own app so the environment credential is present, which the
    other tests deliberately remove.
    """
    settings = integration_settings.model_copy(
        update={
            "ai_credential_encryption_key": SecretStr(Fernet.generate_key().decode()),
            **dict.fromkeys(ENVIRONMENT_KEY_FIELDS, None),
            "anthropic_api_key": SecretStr("sk-ant-deployment-wide-key-0123456789"),
        }
    )
    with TestClient(create_app(settings)) as env_client:
        session = _session(env_client, settings, alpha.admin.email, alpha.organization_id)

        assert session.get("/ai/status").json()["configured"] is True
        assert session.get("/ai/providers").json()["using_environment_fallback"] is True


def test_a_stored_credential_takes_precedence_over_the_environment(
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An administrator's key must win, or configuring it looks ignored."""
    checker = StubCheck()
    monkeypatch.setattr(ai_router, "verify_credential", checker)
    settings = integration_settings.model_copy(
        update={
            "ai_credential_encryption_key": SecretStr(Fernet.generate_key().decode()),
            **dict.fromkeys(ENVIRONMENT_KEY_FIELDS, None),
            "anthropic_api_key": SecretStr("sk-ant-deployment-wide-key-0123456789"),
        }
    )
    with TestClient(create_app(settings)) as env_client:
        session = _session(env_client, settings, alpha.admin.email, alpha.organization_id)
        session.request("PUT", f"/ai/providers/{PROVIDER}", json={"api_key": FAKE_KEY})

        body = session.get("/ai/providers").json()

    assert body["using_environment_fallback"] is False
    assert body["providers"][0]["configured"] is True


# --- Deployments that cannot store secrets ----------------------------------


def test_without_an_encryption_key_storage_is_refused_rather_than_faked(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """No silent per-process key: a credential saved under one would stop
    decrypting after the next restart, which is worse than refusing."""
    settings = integration_settings.model_copy(
        update={
            "ai_credential_encryption_key": None,
            **dict.fromkeys(ENVIRONMENT_KEY_FIELDS, None),
        }
    )
    with TestClient(create_app(settings)) as bare_client:
        session = _session(bare_client, settings, alpha.admin.email, alpha.organization_id)

        listed = session.get("/ai/providers")
        stored = session.request(
            "PUT", f"/ai/providers/{PROVIDER}", json={"api_key": FAKE_KEY}
        )

    assert listed.json()["storage_available"] is False
    assert stored.status_code == 503
    assert stored.json()["error"]["code"] == "secret_storage_not_configured"
