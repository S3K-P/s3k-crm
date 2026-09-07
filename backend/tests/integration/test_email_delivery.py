"""Email: requested in a transaction, delivered by the worker, logged once.

The behaviour under test is the one the audit called a defect rather than a
gap: before this, ``POST /organizations/current/invitations`` created a row
and the screen implied somebody had been emailed. Nobody had. So the first
test here is that inviting somebody actually produces a message, and the rest
are the ways that could go wrong once it does.

The provider is a stub, and only the provider. Everything else — the outbox,
the dispatcher, the delivery log, RLS — is real, because those are where the
guarantees live. A stub provider is the one honest fake: there is no SMTP
server in CI and sending real mail from a test suite would be a bug.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.email.models import EmailDelivery, EmailDeliveryStatus
from app.platform.email.provider import (
    DeliveryReceipt,
    EmailNotConfiguredError,
    OutboundEmail,
)
from app.platform.email.service import (
    EMAIL_REQUESTED,
    deliver_email_event,
    request_email,
)
from app.platform.email.templates import INVITATION, render
from app.platform.events.models import EventStatus, OutboxEvent
from app.platform.events.service import (
    EventDispatcher,
    clear_handlers,
    register_handler,
    registered_handlers,
)
from tests.integration.conftest import ApiSession, Tenant, scope_session_to

pytestmark = pytest.mark.integration


class StubProvider:
    """Records what it was asked to send. Optionally fails."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.name = "stub"
        self.sent: list[OutboundEmail] = []
        self._fail_with = fail_with

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        if self._fail_with is not None:
            raise self._fail_with
        self.sent.append(message)
        return DeliveryReceipt(
            message_id=f"stub-{len(self.sent)}", provider=self.name
        )


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


@pytest_asyncio.fixture
async def clean_outbox(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    async def wipe() -> None:
        async with session_factory() as session:
            await session.execute(text("DELETE FROM platform.outbox_events"))
            await session.commit()

    await wipe()
    yield
    await wipe()


def _with_provider(provider: StubProvider) -> None:
    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        await deliver_email_event(session, event, provider=provider)

    register_handler(EMAIL_REQUESTED, handler, tenant_scoped=True)


async def _deliveries(
    session_factory: async_sessionmaker[AsyncSession], tenant: Tenant
) -> list[EmailDelivery]:
    async with session_factory() as session:
        await scope_session_to(session, tenant.organization_id)
        rows = await session.execute(select(EmailDelivery))
        return list(rows.scalars().all())


# --- The defect this phase exists to close ----------------------------------


async def test_inviting_somebody_actually_produces_an_email(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """The whole point.

    Before Phase C this route created a row and sent nothing, while the screen
    said an invitation had been sent. Now the request enqueues an event in the
    same transaction, the worker delivers it, and the message carries a link
    the recipient can actually use.
    """
    provider = StubProvider()
    _with_provider(provider)

    invited = as_alpha_admin.post(
        "/organizations/current/invitations",
        json={"email": "newcomer@example.com"},
    )
    assert invited.status_code == 201, invited.text

    result = await EventDispatcher(session_factory).drain_once()

    assert result.succeeded == 1
    assert len(provider.sent) == 1
    message = provider.sent[0]
    assert message.to_address == "newcomer@example.com"
    # The link has to contain the one-time token, or the email is decorative.
    assert invited.json()["token"] in message.text_body
    assert "/invitations/accept?token=" in message.text_body


async def test_an_invitation_rolled_back_sends_nothing(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_outbox: None
) -> None:
    """The transactional guarantee, from the email's side.

    An email requested in a transaction that never commits must not be sent —
    otherwise the system announces invitations that do not exist.
    """
    provider = StubProvider()
    _with_provider(provider)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        request_email(
            session,
            organization_id=alpha.organization_id,
            to_address="ghost@example.com",
            template=INVITATION,
            context={
                "inviter_name": "Ada",
                "organization_name": "Alpha",
                "accept_url": "https://example.com/accept?token=x",
                "expires_on": "01 January 2027",
            },
        )
        await session.rollback()

    await EventDispatcher(session_factory).drain_once()

    assert provider.sent == []


# --- Exactly once, under at-least-once delivery -----------------------------


async def test_a_retried_event_does_not_send_twice(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_outbox: None
) -> None:
    """Delivery is at-least-once; sending must not be.

    The unique index on ``outbox_event_id`` is what makes the second run a
    no-op. Simulated by handing the same event to the handler twice, which is
    exactly what a worker killed between the send and the completion produces.
    """
    provider = StubProvider()
    _with_provider(provider)
    await _request_one(session_factory, alpha)

    dispatcher = EventDispatcher(session_factory)
    await dispatcher.drain_once()

    # Put the event back as if the completion had been lost.
    async with session_factory() as session:
        event = (await session.execute(select(OutboxEvent))).scalar_one()
        event.status = EventStatus.PENDING
        await session.commit()

    await dispatcher.drain_once()

    assert len(provider.sent) == 1, "the message was sent twice"
    deliveries = await _deliveries(session_factory, alpha)
    assert len(deliveries) == 1


async def test_the_delivery_log_records_what_was_sent(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_outbox: None
) -> None:
    provider = StubProvider()
    _with_provider(provider)
    await _request_one(session_factory, alpha)

    await EventDispatcher(session_factory).drain_once()

    delivery = (await _deliveries(session_factory, alpha))[0]
    assert delivery.status is EmailDeliveryStatus.SENT
    assert delivery.to_address == "newcomer@example.com"
    assert delivery.template == INVITATION
    assert delivery.provider == "stub"
    assert delivery.provider_message_id == "stub-1"
    assert delivery.sent_at is not None


async def test_the_log_never_stores_the_message_body(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_outbox: None
) -> None:
    """A stored body would put a reset link in a table administrators read.

    That would make the delivery log a privilege-escalation route: read a
    colleague's reset link rather than use the audited administrative action.
    Pinned as a column-level fact so it cannot be added back for convenience.
    """
    columns = {column.name for column in EmailDelivery.__table__.columns}

    assert "body" not in columns
    assert "text_body" not in columns
    assert "html_body" not in columns


# --- Failure -----------------------------------------------------------------


async def test_an_unconfigured_provider_fails_loudly_and_permanently(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_outbox: None
) -> None:
    """Retrying cannot configure a provider.

    Dead-lettered on the first attempt, with the reason in the delivery log —
    so an administrator sees "email was never set up" rather than silence.
    """
    provider = StubProvider(
        fail_with=EmailNotConfiguredError("No email provider is configured.")
    )
    _with_provider(provider)
    await _request_one(session_factory, alpha)

    result = await EventDispatcher(session_factory).drain_once()

    assert result.dead == 1
    delivery = (await _deliveries(session_factory, alpha))[0]
    assert delivery.status is EmailDeliveryStatus.FAILED
    assert "No email provider is configured" in (delivery.error or "")


async def test_a_transient_provider_failure_is_retried_and_visible(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_outbox: None
) -> None:
    """The failed attempt is committed even though the event will retry.

    An operator watching deliveries should see the attempts, not only the
    eventual success — otherwise a provider that fails four times out of five
    looks perfectly healthy.
    """
    provider = StubProvider(fail_with=RuntimeError("connection reset"))
    _with_provider(provider)
    await _request_one(session_factory, alpha)

    result = await EventDispatcher(session_factory).drain_once()

    assert result.retrying == 1
    delivery = (await _deliveries(session_factory, alpha))[0]
    assert delivery.status is EmailDeliveryStatus.FAILED
    assert "connection reset" in (delivery.error or "")


async def test_a_missing_template_field_dead_letters_rather_than_sending_a_gap(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_outbox: None
) -> None:
    """"Hi , click  to continue" is worse than no email at all."""
    provider = StubProvider()
    _with_provider(provider)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        request_email(
            session,
            organization_id=alpha.organization_id,
            to_address="newcomer@example.com",
            template=INVITATION,
            context={"inviter_name": "Ada"},  # the other three are missing
        )
        await session.commit()

    result = await EventDispatcher(session_factory).drain_once()

    assert result.dead == 1
    assert provider.sent == []


def test_requesting_an_unknown_template_fails_in_the_caller() -> None:
    """A typo should fail the code path that contains it, not the worker."""
    with pytest.raises(KeyError):
        request_email(
            None,  # type: ignore[arg-type] - never reached
            organization_id=uuid.uuid4(),
            to_address="somebody@example.com",
            template="no_such_template",
            context={},
        )


# --- Templates ---------------------------------------------------------------


def test_a_template_refuses_to_render_with_a_missing_field() -> None:
    with pytest.raises(KeyError, match="missing"):
        render(INVITATION, {"inviter_name": "Ada"})


def test_rendered_messages_are_plain_text_with_a_visible_link() -> None:
    """These messages carry links people are asked to trust.

    Plain text shows the URL it is sending you to; HTML is a place to put a
    link whose visible text differs from its target.
    """
    rendered = render(
        INVITATION,
        {
            "inviter_name": "Ada Admin",
            "organization_name": "Acme",
            "accept_url": "https://app.example.com/invitations/accept?token=abc",
            "expires_on": "01 January 2027",
        },
    )

    assert "Ada Admin" in rendered.subject
    assert "Acme" in rendered.subject
    assert "https://app.example.com/invitations/accept?token=abc" in rendered.text_body
    assert "<a " not in rendered.text_body


# --- Tenant isolation --------------------------------------------------------


async def test_one_organizations_delivery_log_never_reaches_another(
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    beta: Tenant,
    clean_outbox: None,
) -> None:
    """The log holds recipient addresses, so it is under RLS."""
    provider = StubProvider()
    _with_provider(provider)
    await _request_one(session_factory, alpha)
    await EventDispatcher(session_factory).drain_once()

    assert len(await _deliveries(session_factory, alpha)) == 1
    assert await _deliveries(session_factory, beta) == []


# --- Helpers -----------------------------------------------------------------


async def _request_one(
    session_factory: async_sessionmaker[AsyncSession], tenant: Tenant
) -> None:
    async with session_factory() as session:
        await scope_session_to(session, tenant.organization_id)
        request_email(
            session,
            organization_id=tenant.organization_id,
            to_address="newcomer@example.com",
            template=INVITATION,
            context={
                "inviter_name": "Ada Admin",
                "organization_name": "Alpha",
                "accept_url": "https://example.com/invitations/accept?token=abc",
                "expires_on": "01 January 2027",
            },
        )
        await session.commit()
