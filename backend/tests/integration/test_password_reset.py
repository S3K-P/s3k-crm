"""Self-service password reset, end to end.

The flow did not exist before Phase C — only an administrator could reset
somebody's password — so these tests cover it from first principles rather
than pinning a change to existing behaviour.

Four properties are what actually matter, and each has its own section below:

1. It works: a link arrives, is redeemable once, and the new password signs in.
2. It says nothing: an address with an account and one without produce
   identical responses, or the endpoint becomes a user-enumeration oracle.
3. It settles the account: every existing session dies, and a brute-force
   lockout is cleared, because somebody resetting a password may be doing it
   *because* an attacker is in the account.
4. It is untenanted: a reset belongs to a global identity, so it must work for
   a user who belongs to no organization, and must not appear in any
   organization's delivery log.

The provider is a stub and nothing else is. The outbox, the dispatcher, the
delivery log, the token table and RLS are all real.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from redis import Redis as SyncRedis
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.platform.auth.models import PasswordResetToken
from app.platform.auth.models import Session as AuthSession
from app.platform.auth.throttle import AUTH_BUCKET
from app.platform.email.models import EmailDelivery, EmailDeliveryStatus
from app.platform.email.provider import DeliveryReceipt, OutboundEmail
from app.platform.email.service import (
    IDENTITY_EMAIL_REQUESTED,
    deliver_email_event,
)
from app.platform.events.models import OutboxEvent
from app.platform.events.service import (
    EventDispatcher,
    clear_handlers,
    register_handler,
    registered_handlers,
)
from tests.integration.conftest import TEST_PASSWORD, Tenant, scope_session_to

pytestmark = pytest.mark.integration

FORGOT = "/auth/forgot-password"
RESET = "/auth/reset-password"
LOGIN = "/auth/login"

#: Meets the policy: 12+ characters, mixed case, a digit.
NEW_PASSWORD = "Rec0veredPassphrase!"


class StubProvider:
    """Records what it was asked to send."""

    def __init__(self) -> None:
        self.name = "stub"
        self.sent: list[OutboundEmail] = []

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        self.sent.append(message)
        return DeliveryReceipt(message_id=f"stub-{len(self.sent)}", provider=self.name)


@pytest.fixture
def api(integration_settings: Settings) -> str:
    return integration_settings.api_prefix


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
    """A provider registered against the *untenanted* event type.

    `tenant_scoped=False` is the contract this flow depends on and is worth
    stating in the fixture: an identity email names no organization, and a
    dispatcher that demanded one would dead-letter every reset.
    """
    stub = StubProvider()

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        await deliver_email_event(session, event, provider=stub)

    register_handler(IDENTITY_EMAIL_REQUESTED, handler, tenant_scoped=False)
    return stub


@pytest_asyncio.fixture(autouse=True)
async def clean_reset_state(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Empty the outbox, the delivery log and the token table around each test.

    The delivery log is cleared with no tenant in scope *and* per tenant: the
    untenanted rows this flow writes are visible only to an unscoped session,
    which is the property under test further down and would otherwise leave
    rows behind for the next test to trip over.
    """

    async def wipe() -> None:
        async with session_factory() as session:
            await session.execute(text("DELETE FROM platform.password_reset_tokens"))
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
    """The reset routes share login's bucket, so clear it around each test."""

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


def _token_from(message: OutboundEmail) -> str:
    """Pull the reset token out of the link in the message body."""
    found = re.search(r"reset-password\?token=([^\s]+)", message.text_body)
    assert found is not None, f"no reset link in:\n{message.text_body}"
    return found.group(1)


async def _request_and_deliver(
    client: TestClient,
    api: str,
    email: str,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> str:
    """Ask for a reset, run the worker, and return the token from the email."""
    asked = client.post(f"{api}{FORGOT}", json={"email": email})
    assert asked.status_code == 202, asked.text
    await EventDispatcher(session_factory).drain_once()
    assert provider.sent, "no message was delivered"
    return _token_from(provider.sent[-1])


# --- 1. It works ------------------------------------------------------------


async def test_a_reset_link_arrives_and_the_new_password_signs_in(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The whole flow, in the order a person experiences it."""
    token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )

    reset = client.post(f"{api}{RESET}", json={"token": token, "new_password": NEW_PASSWORD})
    assert reset.status_code == 204, reset.text

    # The new one works...
    signed_in = client.post(
        f"{api}{LOGIN}", json={"email": alpha.member.email, "password": NEW_PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text

    # ...and the old one does not.
    refused = client.post(
        f"{api}{LOGIN}", json={"email": alpha.member.email, "password": TEST_PASSWORD}
    )
    assert refused.status_code == 401


async def test_the_email_is_plain_text_and_carries_the_link(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """A message that does not contain a usable link is decorative.

    The token also must not appear anywhere it could be read later — the
    delivery log stores a subject and a template name, never a body.
    """
    await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )

    message = provider.sent[-1]
    assert message.to_address == alpha.member.email
    assert "/reset-password?token=" in message.text_body

    async with session_factory() as session:
        rows = await session.execute(select(EmailDelivery))
        delivery = rows.scalars().one()
        assert delivery.status is EmailDeliveryStatus.SENT
        assert delivery.template == "password_reset"
        # The columns that exist are the ones that cannot leak a credential.
        assert not hasattr(delivery, "text_body")
        assert not hasattr(delivery, "body")


async def test_a_token_can_only_be_spent_once(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The second use of a link is refused, not silently re-applied.

    A link sits in an inbox indefinitely. If it stayed live, a mailbox
    compromised months later would still be a working key to the account.
    """
    token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )

    first = client.post(f"{api}{RESET}", json={"token": token, "new_password": NEW_PASSWORD})
    assert first.status_code == 204, first.text

    second = client.post(
        f"{api}{RESET}", json={"token": token, "new_password": "An0therPassphrase!"}
    )
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_reset_token"

    # And the password is still the one the first redemption set.
    assert (
        client.post(
            f"{api}{LOGIN}", json={"email": alpha.member.email, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )


async def test_asking_again_invalidates_the_earlier_link(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """Only the newest link works.

    Somebody who asks twice because the first mail was slow must not be left
    with two working credentials in an inbox they may no longer control.
    """
    first_token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )
    second_token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )
    assert first_token != second_token

    stale = client.post(
        f"{api}{RESET}", json={"token": first_token, "new_password": NEW_PASSWORD}
    )
    assert stale.status_code == 400

    fresh = client.post(
        f"{api}{RESET}", json={"token": second_token, "new_password": NEW_PASSWORD}
    )
    assert fresh.status_code == 204, fresh.text


async def test_an_expired_link_is_refused(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """Expiry is enforced on redemption, not only advertised in the email.

    The row is aged rather than the clock moved: the expiry is a column
    comparison, so this exercises the same predicate production runs.
    """
    token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )

    async with session_factory() as session:
        await session.execute(
            update(PasswordResetToken).values(
                expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
            )
        )
        await session.commit()

    expired = client.post(
        f"{api}{RESET}", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert expired.status_code == 400
    assert expired.json()["error"]["code"] == "invalid_reset_token"


async def test_a_fabricated_token_is_refused(client: TestClient, api: str) -> None:
    """No token, no row, no hint about which of those it was."""
    refused = client.post(
        f"{api}{RESET}",
        json={"token": uuid.uuid4().hex * 2, "new_password": NEW_PASSWORD},
    )
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "invalid_reset_token"


async def test_a_weak_new_password_is_refused_and_the_link_survives(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """Policy is checked before the token is spent.

    Otherwise one mistyped password costs the person their link and a second
    trip through their inbox, for a mistake the form could have caught.
    """
    token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )

    weak = client.post(f"{api}{RESET}", json={"token": token, "new_password": "short"})
    assert weak.status_code == 422
    assert weak.json()["error"]["code"] == "weak_password"

    # The same link still works.
    retried = client.post(
        f"{api}{RESET}", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert retried.status_code == 204, retried.text


# --- 2. It says nothing -----------------------------------------------------


def test_a_known_and_an_unknown_address_are_answered_identically(
    client: TestClient, api: str, alpha: Tenant
) -> None:
    """The enumeration property, stated as a comparison.

    If these two differed in status or body, anyone with a list of addresses
    could find out which of them are registered here — which is exactly what
    the login endpoint's single error message exists to prevent, and would be
    pointless to prevent there and hand over here.
    """
    known = client.post(f"{api}{FORGOT}", json={"email": alpha.member.email})
    unknown = client.post(
        f"{api}{FORGOT}", json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com"}
    )

    assert known.status_code == unknown.status_code == 202
    assert known.content == unknown.content == b""


async def test_an_unknown_address_produces_no_mail_and_no_token(
    client: TestClient,
    api: str,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The identical answer is the *only* thing that is identical.

    202 for an unknown address must not mean a message went somewhere: an
    endpoint that emailed whatever it was given would be a free outbound-mail
    generator pointed at any address an attacker chose.
    """
    asked = client.post(
        f"{api}{FORGOT}", json={"email": f"ghost-{uuid.uuid4().hex[:8]}@example.com"}
    )
    assert asked.status_code == 202

    await EventDispatcher(session_factory).drain_once()
    assert provider.sent == []

    async with session_factory() as session:
        tokens = await session.execute(select(PasswordResetToken))
        assert tokens.scalars().all() == []


def test_the_request_endpoint_is_throttled(
    client: TestClient, api: str, integration_settings: Settings
) -> None:
    """Unauthenticated, and it sends mail — so it needs the same budget as login.

    The limit is deliberately read from settings rather than hard-coded: this
    asserts that the route is *on* the bucket, not what the bucket's size
    happens to be.
    """
    limit = integration_settings.login_rate_limit_attempts
    statuses = [
        client.post(
            f"{api}{FORGOT}", json={"email": f"probe-{index}@example.com"}
        ).status_code
        for index in range(limit + 2)
    ]

    assert statuses[0] == 202, "the first request is answered normally"
    assert 429 in statuses, "the address must eventually be refused"


# --- 3. It settles the account ---------------------------------------------


async def test_resetting_ends_every_other_session(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The point of a reset when an account is compromised.

    Somebody resetting a password may be doing it *because* an attacker holds
    a live session, so the reset has to end that session and not merely issue
    a new one beside it.

    What is asserted is the **refresh** lineage, and that is the honest test
    rather than the convenient one. The access-token cutoff
    (``dependencies.get_current_user``) compares a JWT ``iat``, which has
    one-second resolution, against ``tokens_valid_from`` truncated to the same
    resolution — so a token minted in the *same second* as the reset is not
    older than the cutoff and survives until it expires. That truncation is
    deliberate and documented where it lives; it is invisible in production,
    where a session is minutes or hours old by the time somebody resets, and
    it is unavoidable here, where the whole flow runs inside one second.

    The refresh token is what makes a session outlast an access token's
    fifteen minutes, and it is revoked immediately. That is the boundary that
    actually matters: an attacker keeps at most the remainder of one access
    token and cannot renew.
    """
    signed_in = client.post(
        f"{api}{LOGIN}", json={"email": alpha.member.email, "password": TEST_PASSWORD}
    )
    assert signed_in.status_code == 200, signed_in.text
    old_access = signed_in.json()["access_token"]
    # Captured before the reset clears it from the jar. The route accepts the
    # body form for clients that cannot use cookies, which is what lets this
    # present a credential the browser would no longer hold.
    old_refresh = client.cookies.get("s3k_refresh")
    assert old_refresh is not None, "login did not set a refresh cookie"

    assert (
        client.get(
            f"{api}/auth/me", headers={"Authorization": f"Bearer {old_access}"}
        ).status_code
        == 200
    )

    reset_token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )
    assert (
        client.post(
            f"{api}{RESET}", json={"token": reset_token, "new_password": NEW_PASSWORD}
        ).status_code
        == 204
    )

    # The lineage cannot be renewed, so the session ends with the access
    # token it is holding.
    client.cookies.clear()
    renewed = client.post(f"{api}/auth/refresh", json={"refresh_token": old_refresh})
    assert renewed.status_code == 401, "a pre-reset session could still be renewed"

    async with session_factory() as session:
        live = await session.execute(
            select(AuthSession).where(
                AuthSession.user_id == alpha.member.user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
        assert live.scalars().all() == [], "a refresh lineage was left usable"


async def test_the_revocation_cutoff_moves_forward_on_reset(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The other half of the test above, asserted where it is observable.

    An access token minted before the reset is refused once a second has
    passed, and the state that produces that is ``tokens_valid_from``. Rather
    than sleep to cross the boundary, this pins the column: it must not be
    older than the moment the reset happened. If it stopped moving, the test
    above would still pass on its refresh assertion and every access token
    ever issued would quietly stay valid.
    """
    before = dt.datetime.now(dt.UTC)

    token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )
    assert (
        client.post(
            f"{api}{RESET}", json={"token": token, "new_password": NEW_PASSWORD}
        ).status_code
        == 204
    )

    async with session_factory() as session:
        cutoff = await session.scalar(
            text(
                "SELECT tokens_valid_from FROM platform.users WHERE id = :user_id"
            ),
            {"user_id": alpha.member.user_id},
        )

    assert cutoff is not None
    assert cutoff >= before, "the revocation cutoff did not move"


async def test_resetting_clears_a_brute_force_lockout(
    client: TestClient,
    api: str,
    alpha: Tenant,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """Recovering by email proves control of the address.

    Making somebody wait out a fifteen-minute lockout *after* they have
    demonstrated that would be a delay with no safety attached to it.
    """
    for _ in range(integration_settings.login_max_failed_attempts + 1):
        client.post(
            f"{api}{LOGIN}",
            json={"email": alpha.member.email, "password": "Wr0ngPassphrase!"},
        )

    locked = client.post(
        f"{api}{LOGIN}", json={"email": alpha.member.email, "password": TEST_PASSWORD}
    )
    assert locked.status_code == 423, "the account should be locked at this point"

    token = await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )
    assert (
        client.post(
            f"{api}{RESET}", json={"token": token, "new_password": NEW_PASSWORD}
        ).status_code
        == 204
    )

    recovered = client.post(
        f"{api}{LOGIN}", json={"email": alpha.member.email, "password": NEW_PASSWORD}
    )
    assert recovered.status_code == 200, recovered.text


# --- 4. It is untenanted ----------------------------------------------------


async def test_somebody_with_no_organization_can_still_reset(
    client: TestClient,
    api: str,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The case that decided the design.

    Signup creates an identity and no organization — "a brand-new account is a
    person, not yet a tenant" — so a user with no membership is an ordinary
    state, not an edge case. If the reset had been scoped to an organization
    this person could never recover their account.
    """
    email = f"tenantless-{uuid.uuid4().hex[:8]}@example.com"
    created = client.post(
        f"{api}/auth/signup",
        json={
            "email": email,
            "password": TEST_PASSWORD,
            "first_name": "Tenant",
            "last_name": "Less",
        },
    )
    assert created.status_code == 201, created.text

    token = await _request_and_deliver(client, api, email, session_factory, provider)
    reset = client.post(
        f"{api}{RESET}", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert reset.status_code == 204, reset.text

    assert (
        client.post(f"{api}{LOGIN}", json={"email": email, "password": NEW_PASSWORD}).status_code
        == 200
    )


async def test_a_reset_is_not_in_any_organizations_delivery_log(
    client: TestClient,
    api: str,
    alpha: Tenant,
    beta: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The NULL-aware policy, exercised rather than read off the catalogue.

    A reset is between the product and the account holder. An organization's
    administrators are not a party to it, and the row that records it must be
    invisible to them — including to the organization the person belongs to,
    which is the case a plain ``organization_id = <setting>`` would get wrong
    in the *other* direction by hiding it from everyone including operators.
    """
    await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )

    for tenant in (alpha, beta):
        async with session_factory() as session:
            await scope_session_to(session, tenant.organization_id)
            rows = await session.execute(select(EmailDelivery))
            assert rows.scalars().all() == [], (
                f"an untenanted reset appeared in {tenant.slug}'s delivery log"
            )

    # It does exist — an unscoped reader sees it, which is what makes the row
    # useful to an operator and keeps the exactly-once index meaningful.
    async with session_factory() as session:
        rows = await session.execute(select(EmailDelivery))
        delivery = rows.scalars().one()
        assert delivery.organization_id is None
        assert delivery.template == "password_reset"


async def test_a_redelivered_reset_event_does_not_send_twice(
    client: TestClient,
    api: str,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """At-least-once delivery, and the index that makes it safe.

    The dispatcher can hand the same event to a handler twice — that is the
    documented contract, not a fault — and for this message twice means two
    working reset links. The unique index on ``outbox_event_id`` is the only
    thing standing between those two facts, which is why the delivery row has
    to exist even though the message belongs to no tenant.
    """
    await _request_and_deliver(
        client, api, alpha.member.email, session_factory, provider
    )
    assert len(provider.sent) == 1

    async with session_factory() as session:
        rows = await session.execute(select(OutboxEvent))
        event = rows.scalars().one()
        # Replay it exactly as a stalled-claim reclaim would.
        await deliver_email_event(session, event, provider=provider)
        await session.commit()

    assert len(provider.sent) == 1, "the retry sent a second reset link"
