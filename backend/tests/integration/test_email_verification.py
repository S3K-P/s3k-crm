"""Email verification (P1-W05-BE-01), end to end.

Real outbox, dispatcher, delivery log and token table; a stub provider stands
in for Microsoft Graph at the very last step, because a test suite must never
put mail in a real inbox. The Graph transport itself is pinned by
``tests/unit/test_graph_email_service.py``.

Properties under test:

1. Signing up sends a verification link, and redeeming it verifies the address.
2. A link is single-use, expires, and only the newest one works.
3. A link issued for an address the account no longer has verifies nothing.
4. Asking for a link needs a session and can only mail the caller's own address.
5. Redeeming an invitation sent to the address verifies it, with no second link.
6. Verification mail is untenanted: it is in no organization's delivery log.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from redis import Redis as SyncRedis
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.platform.auth.models import EmailVerificationToken, User
from app.platform.auth.throttle import AUTH_BUCKET
from app.platform.email.models import EmailDelivery
from app.platform.email.provider import DeliveryReceipt, OutboundEmail
from app.platform.email.service import (
    EMAIL_REQUESTED,
    IDENTITY_EMAIL_REQUESTED,
    deliver_email_event,
)
from app.platform.email.templates import EMAIL_VERIFICATION
from app.platform.events.models import OutboxEvent
from app.platform.events.service import (
    EventDispatcher,
    clear_handlers,
    register_handler,
    registered_handlers,
)
from tests.integration.conftest import ApiSession, Tenant, scope_session_to

pytestmark = pytest.mark.integration

SIGNUP_PASSWORD = "Str0ngPassphrase!"
NEWCOMER = "newcomer@verify.example"


class StubProvider:
    """Records what it was asked to send."""

    def __init__(self) -> None:
        self.name = "stub"
        self.sent: list[OutboundEmail] = []

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        self.sent.append(message)
        return DeliveryReceipt(message_id=f"stub-{len(self.sent)}", provider=self.name)


@pytest.fixture(autouse=True)
def _isolate_handlers() -> Iterator[None]:
    existing = registered_handlers()
    clear_handlers()
    yield
    clear_handlers()
    for handler in existing.values():
        register_handler(
            handler.event_type, handler.handle, tenant_scoped=handler.tenant_scoped
        )


@pytest.fixture
def provider() -> StubProvider:
    stub = StubProvider()

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        await deliver_email_event(session, event, provider=stub)

    register_handler(IDENTITY_EMAIL_REQUESTED, handler, tenant_scoped=False)
    register_handler(EMAIL_REQUESTED, handler, tenant_scoped=True)
    return stub


@pytest_asyncio.fixture(autouse=True)
async def clean_verification_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    async def wipe() -> None:
        async with session_factory() as session:
            await session.execute(text("DELETE FROM platform.email_verification_tokens"))
            await session.execute(text("DELETE FROM platform.outbox_events"))
            await session.execute(
                text("DELETE FROM platform.email_deliveries WHERE organization_id IS NULL")
            )
            await session.commit()

    await wipe()
    yield
    await wipe()


@pytest.fixture(autouse=True)
def _clear_throttle(integration_settings: Settings) -> Iterator[None]:
    def clear() -> None:
        redis = SyncRedis.from_url(integration_settings.redis_url, decode_responses=True)
        try:
            keys = list(redis.scan_iter(f"ratelimit:{AUTH_BUCKET}:*"))
            if keys:
                redis.delete(*keys)
        finally:
            redis.close()

    clear()
    yield
    clear()


def _signup(client: TestClient, api: str, email: str = NEWCOMER) -> str:
    response = client.post(
        f"{api}/auth/signup",
        json={
            "email": email,
            "password": SIGNUP_PASSWORD,
            "first_name": "New",
            "last_name": "Comer",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _token_from(message: OutboundEmail) -> str:
    found = re.search(r"verify-email\?token=([^\s]+)", message.text_body)
    assert found is not None, f"no verification link in:\n{message.text_body}"
    return found.group(1)


async def _user(
    session_factory: async_sessionmaker[AsyncSession], email: str = NEWCOMER
) -> User:
    async with session_factory() as session:
        found = await session.execute(select(User).where(User.email == email))
        return found.scalar_one()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- 1. It works ------------------------------------------------------------


async def test_signing_up_sends_a_link_that_verifies_the_address(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    api = integration_settings.api_prefix
    access = _signup(client, api)

    assert (await _user(session_factory)).email_verified_at is None
    result = await EventDispatcher(session_factory).drain_once()
    assert result.succeeded == 1

    (message,) = provider.sent
    assert message.to_address == NEWCOMER
    assert message.subject == "Confirm your email address for S3K"
    assert message.text_body.count("verify-email?token=") == 1

    confirmed = client.post(
        f"{api}/auth/verify-email/confirm", json={"token": _token_from(message)}
    )
    assert confirmed.status_code == 204, confirmed.text
    assert (await _user(session_factory)).email_verified_at is not None

    me = client.get(f"{api}/auth/me", headers=_bearer(access))
    assert me.status_code == 200
    assert me.json()["user"]["email_verified_at"] is not None


async def test_only_a_digest_of_the_token_is_stored(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    _signup(client, integration_settings.api_prefix)
    await EventDispatcher(session_factory).drain_once()
    token = _token_from(provider.sent[0])

    async with session_factory() as session:
        rows = (await session.execute(select(EmailVerificationToken))).scalars().all()
    assert len(rows) == 1
    assert rows[0].token_hash != token
    assert token not in rows[0].token_hash
    assert rows[0].email == NEWCOMER


async def test_the_delivery_log_holds_no_link(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    _signup(client, integration_settings.api_prefix)
    await EventDispatcher(session_factory).drain_once()
    token = _token_from(provider.sent[0])

    async with session_factory() as session:
        (delivery,) = (await session.execute(select(EmailDelivery))).scalars().all()
    assert delivery.template == EMAIL_VERIFICATION
    assert delivery.organization_id is None
    assert token not in f"{delivery.subject}{delivery.error or ''}"


# --- 2. Single use, expiry, supersession ------------------------------------


async def test_a_link_can_only_be_used_once(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    api = integration_settings.api_prefix
    _signup(client, api)
    await EventDispatcher(session_factory).drain_once()
    token = _token_from(provider.sent[0])

    first = client.post(f"{api}/auth/verify-email/confirm", json={"token": token})
    second = client.post(f"{api}/auth/verify-email/confirm", json={"token": token})

    assert first.status_code == 204
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_verification_token"


async def test_an_expired_link_is_refused_and_verifies_nothing(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    api = integration_settings.api_prefix
    _signup(client, api)
    await EventDispatcher(session_factory).drain_once()

    async with session_factory() as session:
        await session.execute(
            update(EmailVerificationToken).values(
                expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
            )
        )
        await session.commit()

    refused = client.post(
        f"{api}/auth/verify-email/confirm", json={"token": _token_from(provider.sent[0])}
    )

    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "invalid_verification_token"
    assert (await _user(session_factory)).email_verified_at is None


@pytest.mark.parametrize("token", ["not-a-real-token", "x" * 512])
def test_a_fabricated_link_is_refused(
    client: TestClient, integration_settings: Settings, token: str
) -> None:
    refused = client.post(
        f"{integration_settings.api_prefix}/auth/verify-email/confirm", json={"token": token}
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "invalid_verification_token"


@pytest.mark.parametrize("payload", [{}, {"token": ""}, {"token": "x" * 513}])
def test_a_malformed_confirmation_is_a_validation_error(
    client: TestClient, integration_settings: Settings, payload: dict[str, str]
) -> None:
    refused = client.post(
        f"{integration_settings.api_prefix}/auth/verify-email/confirm", json=payload
    )
    assert refused.status_code == 422


async def test_asking_again_invalidates_the_earlier_link(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    api = integration_settings.api_prefix
    access = _signup(client, api)
    await EventDispatcher(session_factory).drain_once()
    first = _token_from(provider.sent[0])

    resent = client.post(f"{api}/auth/verify-email/request", headers=_bearer(access))
    assert resent.status_code == 202, resent.text
    assert resent.json() == {"sent": True, "email_verified": False}
    await EventDispatcher(session_factory).drain_once()
    second = _token_from(provider.sent[1])

    stale = client.post(f"{api}/auth/verify-email/confirm", json={"token": first})
    fresh = client.post(f"{api}/auth/verify-email/confirm", json={"token": second})

    assert stale.status_code == 400
    assert fresh.status_code == 204


# --- 3. A link belongs to an address, not an account -------------------------


async def test_a_link_for_a_previous_address_verifies_nothing(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    api = integration_settings.api_prefix
    _signup(client, api)
    await EventDispatcher(session_factory).drain_once()

    async with session_factory() as session:
        await session.execute(
            update(User).where(User.email == NEWCOMER).values(email="changed@verify.example")
        )
        await session.commit()

    refused = client.post(
        f"{api}/auth/verify-email/confirm", json={"token": _token_from(provider.sent[0])}
    )

    assert refused.status_code == 400
    assert (await _user(session_factory, "changed@verify.example")).email_verified_at is None


# --- 4. Requesting a link ------------------------------------------------------


def test_requesting_a_link_requires_a_session(
    client: TestClient, integration_settings: Settings
) -> None:
    refused = client.post(f"{integration_settings.api_prefix}/auth/verify-email/request")
    assert refused.status_code == 401


async def test_an_already_verified_address_is_not_mailed_again(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    api = integration_settings.api_prefix
    access = _signup(client, api)
    await EventDispatcher(session_factory).drain_once()
    client.post(f"{api}/auth/verify-email/confirm", json={"token": _token_from(provider.sent[0])})

    again = client.post(f"{api}/auth/verify-email/request", headers=_bearer(access))
    await EventDispatcher(session_factory).drain_once()

    assert again.status_code == 202
    assert again.json() == {"sent": False, "email_verified": True}
    assert len(provider.sent) == 1


async def test_the_link_only_ever_goes_to_the_callers_own_address(
    as_alpha_member: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The route takes no address at all, so it cannot be aimed at anyone else."""
    requested = as_alpha_member.post(
        "/auth/verify-email/request", json={"email": "victim@elsewhere.example"}
    )
    assert requested.status_code == 202, requested.text
    await EventDispatcher(session_factory).drain_once()

    assert [message.to_address for message in provider.sent] == [alpha.member.email]


# --- 5. Invitations prove the address ------------------------------------------


async def test_redeeming_an_invitation_verifies_the_address(
    client: TestClient,
    integration_settings: Settings,
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    api = integration_settings.api_prefix
    invited = as_alpha_admin.post(
        "/organizations/current/invitations", json={"email": NEWCOMER}
    )
    assert invited.status_code == 201, invited.text

    access = _signup(client, api)
    accepted = client.post(
        f"{api}/invitations/accept",
        json={"token": invited.json()["token"]},
        headers=_bearer(access),
    )
    assert accepted.status_code == 200, accepted.text

    user = await _user(session_factory)
    assert user.email_verified_at is not None

    # The verification link that signup sent is spent along with it.
    async with session_factory() as session:
        outstanding = await session.scalar(
            text(
                "SELECT count(*) FROM platform.email_verification_tokens "
                "WHERE user_id = :user AND used_at IS NULL"
            ),
            {"user": user.id},
        )
    assert outstanding == 0

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        audit = await session.scalar(
            text(
                "SELECT count(*) FROM platform.audit_logs "
                "WHERE action = 'EMAIL_VERIFIED' AND entity_id = :user"
            ),
            {"user": user.id},
        )
    assert audit == 1


# --- 6. Untenanted -------------------------------------------------------------


async def test_verification_mail_is_in_no_organizations_delivery_log(
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    _signup(client, integration_settings.api_prefix)
    await EventDispatcher(session_factory).drain_once()
    assert provider.sent

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        visible = (await session.execute(select(EmailDelivery))).scalars().all()
    assert all(delivery.template != EMAIL_VERIFICATION for delivery in visible)
