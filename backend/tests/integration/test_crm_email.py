"""User-authored CRM email: composed in a request, sent by the worker, once.

Everything here is real except the provider — the outbox, the dispatcher, the
delivery log, RLS, the permission checks. A stub provider is the one honest
fake: there is no Microsoft Graph tenant in CI, and a test suite that sent real mail would
be a defect rather than a test.

The tests are grouped by the promise they hold:

* composing and sending, including the transactional guarantee;
* threading, which is what makes a conversation rather than a pile of messages;
* recipients — CC, BCC, and the rule that a blind copy stays blind;
* templates and their placeholders;
* delivery: retries, failures, and the two locks that stop a double send;
* isolation and permissions.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.platform.email.models import EmailDelivery, EmailDeliveryStatus
from app.platform.email.provider import (
    DeliveryReceipt,
    EmailNotConfiguredError,
    OutboundEmail,
)
from app.platform.email.service import CRM_EMAIL_TEMPLATE
from app.platform.events.service import (
    EventDispatcher,
    clear_handlers,
    register_handler,
    registered_handlers,
)
from app.products.crm.emails.delivery import deliver_crm_email_event
from app.products.crm.emails.events import CRM_EMAIL_SEND_REQUESTED
from app.products.crm.emails.models import EmailMessage, EmailStatus, EmailThread
from app.products.crm.emails.templating import normalize_subject
from tests.integration.conftest import ApiSession, Tenant, scope_session_to

pytestmark = pytest.mark.integration


class StubProvider:
    """Records what it was asked to send. Optionally fails."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.name = "stub"
        self.sent: list[OutboundEmail] = []
        self._fail_with = fail_with
        #: Flipped to stop failing, so a retry can be observed succeeding.
        self.heal_after: int | None = None

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        if self._fail_with is not None and (
            self.heal_after is None or len(self.sent) < self.heal_after
        ):
            raise self._fail_with
        self.sent.append(message)
        return DeliveryReceipt(message_id=f"stub-{len(self.sent)}", provider=self.name)


@pytest.fixture(autouse=True)
def _isolate_handlers() -> Iterator[None]:
    """Swap the real handler registry out and put it back.

    The registry is process-global, so a test registering a stub would
    otherwise leak into every test that ran after it.
    """
    existing = registered_handlers()
    clear_handlers()
    yield
    clear_handlers()
    for handler in existing.values():
        register_handler(
            handler.event_type, handler.handle, tenant_scoped=handler.tenant_scoped
        )


@pytest.fixture
def other_session(client: TestClient, integration_settings: Settings) -> ApiSession:
    """A second, independent signed-in client.

    The shared ``as_alpha_admin`` / ``as_alpha_member`` fixtures both return
    *the same* ``ApiSession`` instance, so asking for both in one test gives
    two names for one session and the later login silently wins. Almost every
    test here needs two genuinely different people — a sender and a colleague,
    or two tenants — so they build the second one from the same
    :class:`TestClient` instead. The client is stateless between requests;
    identity travels in the headers each session holds.
    """
    return ApiSession(client, integration_settings.api_prefix)


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
    async def handler(session: AsyncSession, event: object) -> None:
        await deliver_crm_email_event(
            session,
            event,  # type: ignore[arg-type]
            provider=provider,
            storage=None,
        )

    register_handler(CRM_EMAIL_SEND_REQUESTED, handler, tenant_scoped=True)


async def _message(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: Tenant,
    message_id: str,
) -> EmailMessage:
    async with session_factory() as session:
        await scope_session_to(session, tenant.organization_id)
        row = await session.execute(
            select(EmailMessage).where(EmailMessage.id == uuid.UUID(message_id))
        )
        return row.scalar_one()


async def _deliveries(
    session_factory: async_sessionmaker[AsyncSession], tenant: Tenant
) -> list[EmailDelivery]:
    async with session_factory() as session:
        await scope_session_to(session, tenant.organization_id)
        rows = await session.execute(select(EmailDelivery))
        return list(rows.scalars().all())


def _contact(api: ApiSession) -> str:
    """A contact to file mail against, and its id."""
    created = api.post(
        "/crm/contacts",
        json={
            "first_name": "Ravi",
            "last_name": "Menon",
            "email": "ravi@zephyr.example",
            "phone": "+91 80 4000 1000",
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _compose(
    api: ApiSession, **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {
        "subject": "Your Q3 proposal",
        "body_text": "Hello Ravi,\n\nAttached is the proposal.\n\n— Priya",
        "to_addresses": ["ravi@zephyr.example"],
    }
    payload.update(overrides)
    response = api.post("/crm/emails", json=payload)
    assert response.status_code == 201, response.text
    return dict(response.json())


# --- Composing and sending --------------------------------------------------


async def test_composing_and_sending_delivers_exactly_one_message(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """The whole point of the phase, end to end.

    A rep composes against a contact, the request returns immediately with the
    message ``QUEUED``, and the worker is what actually puts it on the wire.
    """
    provider = StubProvider()
    _with_provider(provider)
    contact_id = _contact(as_alpha_admin)

    created = _compose(
        as_alpha_admin,
        related_entity_type="CONTACT",
        related_entity_id=contact_id,
        send=True,
    )
    # The response does not claim it has been sent, because it has not.
    assert created["status"] == EmailStatus.QUEUED.value
    assert created["from_address"] == alpha.admin.email

    result = await EventDispatcher(session_factory).drain_once()

    assert result.succeeded == 1
    assert len(provider.sent) == 1
    outbound = provider.sent[0]
    assert outbound.to_address == "ravi@zephyr.example"
    assert "Attached is the proposal." in outbound.text_body

    stored = await _message(session_factory, alpha, str(created["id"]))
    assert stored.status is EmailStatus.SENT
    assert stored.sent_at is not None
    assert stored.provider_message_id == "stub-1"
    assert stored.error is None


async def test_a_draft_is_not_sent_until_it_is(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """Saving a draft enqueues nothing. Sending it enqueues exactly one event."""
    provider = StubProvider()
    _with_provider(provider)

    created = _compose(as_alpha_admin)
    assert created["status"] == EmailStatus.DRAFT.value

    drained = await EventDispatcher(session_factory).drain_once()
    assert drained.claimed == 0
    assert provider.sent == []

    sent = as_alpha_admin.post(f"/crm/emails/{created['id']}/send")
    assert sent.status_code == 200, sent.text
    assert sent.json()["status"] == EmailStatus.QUEUED.value

    result = await EventDispatcher(session_factory).drain_once()
    assert result.succeeded == 1
    assert len(provider.sent) == 1


async def test_a_sent_message_cannot_be_edited_or_resent(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    clean_outbox: None,
) -> None:
    """Sent mail is history.

    Editing it would make our record disagree with the copy in the
    recipient's inbox, and re-sending would put a second one there.
    """
    _with_provider(StubProvider())
    created = _compose(as_alpha_admin, send=True)
    await EventDispatcher(session_factory).drain_once()

    edited = as_alpha_admin.patch(
        f"/crm/emails/{created['id']}", json={"subject": "Rewritten"}
    )
    assert edited.status_code == 409
    assert edited.json()["error"]["code"] == "email_not_editable"

    resent = as_alpha_admin.post(f"/crm/emails/{created['id']}/send")
    assert resent.status_code == 409
    assert resent.json()["error"]["code"] == "email_not_sendable"


async def test_a_rolled_back_compose_sends_nothing(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """The transactional guarantee, from the email's side.

    A message enqueued in a transaction that never commits must not be sent.
    Written directly against the service rather than through the API because
    the thing under test is a rollback, and a request that returns 201 has
    already committed.
    """
    from app.core.config import get_settings
    from app.products.crm.emails.service import EmailService

    provider = StubProvider()
    _with_provider(provider)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        service = EmailService(session, settings=get_settings())
        await service.create_message(
            organization_id=alpha.organization_id,
            actor_id=alpha.admin.user_id,
            sender_address=alpha.admin.email,
            sender_name="Priya",
            values={
                "subject": "Never happened",
                "body_text": "This transaction is about to roll back.",
                "to_addresses": ["nobody@example.com"],
                "send": True,
            },
        )
        await session.rollback()

    result = await EventDispatcher(session_factory).drain_once()
    assert result.claimed == 0
    assert provider.sent == []


# --- Threading --------------------------------------------------------------


def test_reply_prefixes_normalize_to_one_conversation_key() -> None:
    """The grouping key ignores however many times a subject was replied to."""
    assert normalize_subject("Re: Fwd:  RE:  Quote  for  Q3") == "quote for q3"
    assert normalize_subject("Quote for Q3") == normalize_subject("RE: Quote for Q3")
    # A different subject is a different conversation, prefixes or not.
    assert normalize_subject("Re: Invoice") != normalize_subject("Re: Quote")


async def test_two_messages_with_the_same_subject_share_a_thread(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """A conversation, not two unrelated messages."""
    _with_provider(StubProvider())
    contact_id = _contact(as_alpha_admin)

    first = _compose(
        as_alpha_admin,
        related_entity_type="CONTACT",
        related_entity_id=contact_id,
        send=True,
    )
    second = _compose(
        as_alpha_admin,
        subject="Re: Your Q3 proposal",
        related_entity_type="CONTACT",
        related_entity_id=contact_id,
        send=True,
    )
    assert second["thread_id"] == first["thread_id"]

    await EventDispatcher(session_factory).drain_once()

    thread = as_alpha_admin.get(f"/crm/emails/threads/{first['thread_id']}")
    assert thread.status_code == 200, thread.text
    body = thread.json()
    assert len(body["messages"]) == 2
    # Oldest first: a conversation reads forwards.
    assert body["messages"][0]["id"] == first["id"]
    assert body["message_count"] == 2


async def test_the_same_subject_to_two_records_stays_two_conversations(
    as_alpha_admin: ApiSession, clean_outbox: None
) -> None:
    """The failure this guards is a CRM classic.

    "Following up" sent to two customers must not become one thread — that is
    how one account's mail appears on another account's timeline.
    """
    _with_provider(StubProvider())
    first_contact = _contact(as_alpha_admin)
    second = as_alpha_admin.post(
        "/crm/contacts",
        json={"first_name": "Anita", "last_name": "Rao", "email": "anita@nova.example"},
    )
    assert second.status_code == 201, second.text
    second_contact = str(second.json()["id"])

    one = _compose(
        as_alpha_admin,
        subject="Following up",
        related_entity_type="CONTACT",
        related_entity_id=first_contact,
    )
    two = _compose(
        as_alpha_admin,
        subject="Following up",
        related_entity_type="CONTACT",
        related_entity_id=second_contact,
        to_addresses=["anita@nova.example"],
    )
    assert one["thread_id"] != two["thread_id"]


async def test_a_reply_cites_its_parent_so_it_threads_in_the_inbox(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """``In-Reply-To`` is what makes a reply thread in the recipient's client.

    Without it every message in a conversation arrives as a new one, which is
    the difference between a CRM that emails and one people will use.
    """
    provider = StubProvider()
    _with_provider(provider)

    first = _compose(as_alpha_admin, send=True)
    await EventDispatcher(session_factory).drain_once()

    reply = _compose(
        as_alpha_admin,
        subject="Re: Your Q3 proposal",
        in_reply_to_message_id=first["id"],
        send=True,
    )
    await EventDispatcher(session_factory).drain_once()

    assert reply["thread_id"] == first["thread_id"]
    assert reply["in_reply_to"] == first["message_id"]
    assert provider.sent[-1].in_reply_to == first["message_id"]


# --- Recipients -------------------------------------------------------------


async def test_cc_is_delivered_and_named_bcc_is_delivered_and_hidden(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    clean_outbox: None,
) -> None:
    """The rule BCC exists for.

    Every copied address must actually receive the message — so all of them
    are in the envelope — while only CC may be named in a header.
    """
    provider = StubProvider()
    _with_provider(provider)

    _compose(
        as_alpha_admin,
        cc_addresses=["manager@zephyr.example"],
        bcc_addresses=["legal@ourcompany.example"],
        send=True,
    )
    await EventDispatcher(session_factory).drain_once()

    outbound = provider.sent[0]
    assert outbound.cc_addresses == ("manager@zephyr.example",)
    assert outbound.bcc_addresses == ("legal@ourcompany.example",)
    # All three receive it.
    assert set(outbound.envelope_recipients()) == {
        "ravi@zephyr.example",
        "manager@zephyr.example",
        "legal@ourcompany.example",
    }


async def test_the_sender_sees_their_blind_copies_and_a_colleague_does_not(
    as_alpha_admin: ApiSession,
    other_session: ApiSession,
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """A blind copy a colleague can read off the timeline is not blind.

    The count is still shown, deliberately: knowing that somebody was copied
    is part of reading a conversation, and it reveals nobody.
    """
    _with_provider(StubProvider())
    created = _compose(
        as_alpha_admin, bcc_addresses=["legal@ourcompany.example"], send=True
    )

    own = as_alpha_admin.get(f"/crm/emails/{created['id']}")
    assert own.status_code == 200
    assert own.json()["bcc_addresses"] == ["legal@ourcompany.example"]
    assert own.json()["bcc_count"] == 1

    # The User role: no VIEW_ALL, so the addresses are withheld and only the
    # count survives.
    other_session.login(alpha.member.email, organization_id=alpha.organization_id)
    colleague = other_session.get(f"/crm/emails/{created['id']}")
    assert colleague.status_code == 200, colleague.text
    assert colleague.json()["bcc_addresses"] is None
    assert colleague.json()["bcc_count"] == 1


async def test_a_malformed_address_is_refused_by_the_request(
    as_alpha_admin: ApiSession, clean_outbox: None
) -> None:
    """Rejected where the sender can still fix it, not by the worker later."""
    response = as_alpha_admin.post(
        "/crm/emails",
        json={
            "subject": "Broken",
            "body_text": "…",
            "to_addresses": ["not-an-address"],
        },
    )
    assert response.status_code == 422


async def test_an_address_may_not_appear_in_two_recipient_fields(
    as_alpha_admin: ApiSession, clean_outbox: None
) -> None:
    """Otherwise the second copy quietly reveals the blind one."""
    response = as_alpha_admin.post(
        "/crm/emails",
        json={
            "subject": "Twice",
            "body_text": "…",
            "to_addresses": ["ravi@zephyr.example"],
            "bcc_addresses": ["RAVI@zephyr.example"],
        },
    )
    assert response.status_code == 422


async def test_a_message_needs_at_least_one_recipient(
    as_alpha_admin: ApiSession, clean_outbox: None
) -> None:
    response = as_alpha_admin.post(
        "/crm/emails",
        json={"subject": "Nobody", "body_text": "…", "to_addresses": []},
    )
    assert response.status_code == 422


# --- Templates --------------------------------------------------------------


async def test_a_template_renders_against_a_record_and_names_what_it_could_not(
    as_alpha_admin: ApiSession, clean_outbox: None
) -> None:
    """The composer must be able to warn before a placeholder reaches a customer."""
    contact_id = _contact(as_alpha_admin)
    template = as_alpha_admin.post(
        "/crm/email-templates",
        json={
            "name": "Proposal follow-up",
            "subject": "{{record.first_name}}, about your proposal",
            "body_text": (
                "Hello {{record.full_name}},\n\n"
                "I am at {{record.department}}.\n\n"
                "— {{sender.name}}"
            ),
        },
    )
    assert template.status_code == 201, template.text

    rendered = as_alpha_admin.post(
        f"/crm/email-templates/{template.json()['id']}/render",
        json={"related_entity_type": "CONTACT", "related_entity_id": contact_id},
    )
    assert rendered.status_code == 200, rendered.text
    body = rendered.json()
    assert body["subject"] == "Ravi, about your proposal"
    assert "Hello Ravi Menon," in body["body_text"]
    # The contact has no department, so the placeholder stays visible rather
    # than rendering "I am at ." into a customer's inbox.
    assert "{{record.department}}" in body["body_text"]
    assert body["unresolved"] == ["record.department"]
    assert "record.email" in body["available"]


async def test_braces_in_a_user_body_do_not_break_a_send(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    clean_outbox: None,
) -> None:
    """The reason placeholders are ``{{double}}``.

    A rep pasting JSON or a price range into a body must not produce a message
    that cannot be sent, which is what ``str.format`` would give them.
    """
    provider = StubProvider()
    _with_provider(provider)
    _compose(
        as_alpha_admin,
        body_text='Pricing is {1,200} per seat, config {"tier": "pro"}.',
        send=True,
    )
    result = await EventDispatcher(session_factory).drain_once()

    assert result.succeeded == 1
    assert '{"tier": "pro"}' in provider.sent[0].text_body


async def test_a_private_template_is_invisible_to_a_colleague(
    as_alpha_admin: ApiSession,
    other_session: ApiSession,
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """404, not 403: confirming it exists would defeat the point."""
    private = as_alpha_admin.post(
        "/crm/email-templates",
        json={
            "name": "My rough draft",
            "subject": "Draft",
            "body_text": "Working on it.",
            "is_shared": False,
        },
    )
    assert private.status_code == 201, private.text

    other_session.login(alpha.member.email, organization_id=alpha.organization_id)
    fetched = other_session.get(f"/crm/email-templates/{private.json()['id']}")
    assert fetched.status_code == 404

    listed = other_session.get("/crm/email-templates")
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()["data"]] == []


async def test_a_template_name_is_unique_while_it_lives(
    as_alpha_admin: ApiSession, clean_outbox: None
) -> None:
    """And free again once retired — deletion here is soft."""
    payload = {"name": "Outreach", "subject": "Hello", "body_text": "Hello there."}
    first = as_alpha_admin.post("/crm/email-templates", json=payload)
    assert first.status_code == 201, first.text

    clash = as_alpha_admin.post("/crm/email-templates", json=payload)
    assert clash.status_code == 422
    assert clash.json()["error"]["code"] == "email_template_name_taken"

    archived = as_alpha_admin.delete(f"/crm/email-templates/{first.json()['id']}")
    assert archived.status_code == 204

    reused = as_alpha_admin.post("/crm/email-templates", json=payload)
    assert reused.status_code == 201, reused.text


# --- Delivery ---------------------------------------------------------------


async def test_one_message_is_sent_once_even_when_the_event_runs_twice(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """At-least-once delivery must not become at-least-once *sending*.

    The dispatcher will re-run an event whose worker died after the relay
    accepted the message. The delivery claim is what stops the second run
    putting a second copy in the customer's inbox.
    """
    provider = StubProvider()
    _with_provider(provider)
    created = _compose(as_alpha_admin, send=True)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        event_row = await session.execute(
            text(
                "SELECT id FROM platform.outbox_events "
                "WHERE event_type = :type ORDER BY created_at DESC LIMIT 1"
            ),
            {"type": CRM_EMAIL_SEND_REQUESTED},
        )
        event_id = event_row.scalar_one()

    await EventDispatcher(session_factory).drain_once()
    assert len(provider.sent) == 1

    # Put the event back on the queue exactly as a stalled claim would.
    #
    # Backdated rather than set to ``now()`` for the reason spelled out in
    # ``test_a_retry_after_a_transient_failure...``: the dispatcher's due-check
    # compares against a Python clock, so writing the PostgreSQL one here would
    # race the two against each other.
    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        requeued = await session.execute(
            text(
                "UPDATE platform.outbox_events "
                "SET status = 'PENDING', attempts = 0, claimed_at = NULL, "
                "    available_at = now() - interval '1 hour' "
                "WHERE id = :id"
            ),
            {"id": event_id},
        )
        assert requeued.rowcount == 1
        await session.commit()

    await EventDispatcher(session_factory).drain_once()

    assert len(provider.sent) == 1, "the message was sent twice"
    stored = await _message(session_factory, alpha, str(created["id"]))
    assert stored.status is EmailStatus.SENT


async def test_a_failed_send_is_recorded_on_the_message_and_in_the_log(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """"Failed" with no reason leaves the sender nothing to act on."""
    provider = StubProvider(fail_with=RuntimeError("relay refused"))
    _with_provider(provider)
    created = _compose(as_alpha_admin, send=True)

    result = await EventDispatcher(session_factory).drain_once()
    assert result.retrying == 1

    stored = await _message(session_factory, alpha, str(created["id"]))
    assert stored.status is EmailStatus.FAILED
    assert "relay refused" in (stored.error or "")

    deliveries = await _deliveries(session_factory, alpha)
    assert len(deliveries) == 1
    assert deliveries[0].status is EmailDeliveryStatus.FAILED
    assert deliveries[0].template == CRM_EMAIL_TEMPLATE


async def test_a_retry_after_a_transient_failure_sends_and_clears_the_error(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """A message must not stay FAILED once a later attempt succeeded."""
    provider = StubProvider(fail_with=RuntimeError("relay hiccup"))
    _with_provider(provider)
    created = _compose(as_alpha_admin, send=True)

    await EventDispatcher(session_factory).drain_once()
    stored = await _message(session_factory, alpha, str(created["id"]))
    assert stored.status is EmailStatus.FAILED

    # The relay recovers, and the backoff window is brought forward so the
    # retry is due rather than a few seconds away.
    #
    # **Backdated, not set to ``now()``, and that is load-bearing.** The
    # dispatcher claims with ``available_at <= now`` where ``now`` is a
    # *Python* timestamp (``EventRepository.claim``), while ``now()`` here is
    # the *PostgreSQL* transaction clock. Writing one and comparing against the
    # other makes this test a race between two clocks: whenever Postgres is
    # even a millisecond ahead of the test process, the event is not yet due,
    # nothing is claimed, and the failure reads as "the retry did not happen".
    # An hour in the past is unambiguously due under either clock.
    provider.heal_after = 0
    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        updated = await session.execute(
            text(
                "UPDATE platform.outbox_events "
                "SET available_at = now() - interval '1 hour' "
                "WHERE payload->>'message_id' = :message_id"
            ),
            {"message_id": str(created["id"])},
        )
        # Scoped to this message's event, and asserted: a WHERE that matched
        # nothing would otherwise leave the event un-due and fail below saying
        # the retry never ran, which is the wrong thing to go looking at.
        assert updated.rowcount == 1
        await session.commit()

    result = await EventDispatcher(session_factory).drain_once()
    assert result.succeeded == 1

    stored = await _message(session_factory, alpha, str(created["id"]))
    assert stored.status is EmailStatus.SENT
    assert stored.error is None


async def test_an_unconfigured_provider_fails_permanently_rather_than_retrying(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """No number of retries configures a relay.

    Five attempts would only delay the moment somebody notices email was never
    set up.
    """
    _with_provider(StubProvider(fail_with=EmailNotConfiguredError("Missing: MICROSOFT_TENANT_ID")))
    created = _compose(as_alpha_admin, send=True)

    result = await EventDispatcher(session_factory).drain_once()
    assert result.dead == 1

    stored = await _message(session_factory, alpha, str(created["id"]))
    assert stored.status is EmailStatus.FAILED
    assert "MICROSOFT_TENANT_ID" in (stored.error or "")


async def test_archiving_a_queued_message_stops_it_being_sent(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    clean_outbox: None,
) -> None:
    """Changing your mind after pressing send should mean something."""
    provider = StubProvider()
    _with_provider(provider)
    created = _compose(as_alpha_admin, send=True)

    archived = as_alpha_admin.delete(f"/crm/emails/{created['id']}")
    assert archived.status_code == 204

    result = await EventDispatcher(session_factory).drain_once()

    assert provider.sent == []
    # A clean skip, not a dead letter an operator has to triage.
    assert result.succeeded == 1


# --- Isolation and permissions ----------------------------------------------


async def test_another_tenants_message_is_not_found(
    as_alpha_admin: ApiSession,
    other_session: ApiSession,
    beta: Tenant,
    clean_outbox: None,
) -> None:
    """A guessed identifier from another organization looks like a typo."""
    _with_provider(StubProvider())
    created = _compose(as_alpha_admin)

    other_session.login(beta.admin.email, organization_id=beta.organization_id)
    fetched = other_session.get(f"/crm/emails/{created['id']}")
    assert fetched.status_code == 404


async def test_a_thread_cannot_be_filed_against_another_tenants_record(
    as_alpha_admin: ApiSession,
    other_session: ApiSession,
    beta: Tenant,
    clean_outbox: None,
) -> None:
    """The link is validated, so mail cannot be used to probe for records."""
    other_session.login(beta.admin.email, organization_id=beta.organization_id)
    foreign_contact = _contact(other_session)

    response = as_alpha_admin.post(
        "/crm/emails",
        json={
            "subject": "Wrong tenant",
            "body_text": "…",
            "to_addresses": ["ravi@zephyr.example"],
            "related_entity_type": "CONTACT",
            "related_entity_id": foreign_contact,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_related_entity"


async def test_a_colleagues_draft_is_invisible(
    as_alpha_admin: ApiSession,
    other_session: ApiSession,
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """An unsent message is work in progress, not the record's history."""
    _with_provider(StubProvider())
    draft = _compose(as_alpha_admin)

    other_session.login(alpha.member.email, organization_id=alpha.organization_id)
    fetched = other_session.get(f"/crm/emails/{draft['id']}")
    assert fetched.status_code == 404

    listed = other_session.get("/crm/emails")
    assert listed.status_code == 200
    assert listed.json()["pagination"]["total"] == 0


async def test_a_sent_message_is_visible_to_the_whole_organization(
    as_alpha_admin: ApiSession,
    other_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    clean_outbox: None,
) -> None:
    """The reason emails are not owner-scoped.

    A colleague must see the account's correspondence, or they re-introduce
    themselves to a customer somebody else emailed last week.
    """
    _with_provider(StubProvider())
    contact_id = _contact(as_alpha_admin)
    _compose(
        as_alpha_admin,
        related_entity_type="CONTACT",
        related_entity_id=contact_id,
        send=True,
    )
    await EventDispatcher(session_factory).drain_once()

    other_session.login(alpha.member.email, organization_id=alpha.organization_id)
    timeline = other_session.get(
        f"/crm/emails?related_entity_type=CONTACT&related_entity_id={contact_id}"
    )
    assert timeline.status_code == 200, timeline.text
    assert timeline.json()["pagination"]["total"] == 1


async def test_the_record_timeline_is_scoped_to_its_record(
    as_alpha_admin: ApiSession, clean_outbox: None
) -> None:
    """Mail about one customer must not appear on another's timeline."""
    _with_provider(StubProvider())
    contact_id = _contact(as_alpha_admin)
    _compose(
        as_alpha_admin,
        related_entity_type="CONTACT",
        related_entity_id=contact_id,
    )
    _compose(as_alpha_admin, subject="Unfiled note to somebody else")

    filtered = as_alpha_admin.get(
        f"/crm/emails?related_entity_type=CONTACT&related_entity_id={contact_id}"
    )
    assert filtered.status_code == 200
    assert filtered.json()["pagination"]["total"] == 1


async def test_sending_is_audited_without_copying_the_recipients(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """The trail says how far a message went, not who it went to.

    Duplicating a recipient list into a table every audit reader can browse
    would widen who sees a customer's colleagues for no operational gain.
    """
    _with_provider(StubProvider())
    _compose(as_alpha_admin, bcc_addresses=["legal@ourcompany.example"], send=True)

    entries = as_alpha_admin.get("/audit-logs?module=emails")
    assert entries.status_code == 200, entries.text
    items = entries.json()["data"]
    assert items, "sending an email recorded nothing"

    details = [item["details"] for item in items if item["details"]]
    sent_entry = next(
        (detail for detail in details if "bcc_count" in detail), None
    )
    assert sent_entry is not None
    assert sent_entry["bcc_count"] == 1
    assert "legal@ourcompany.example" not in str(details)


async def test_a_thread_lists_against_its_record(
    as_alpha_admin: ApiSession, clean_outbox: None
) -> None:
    """The conversation list a record's Emails tab reads."""
    _with_provider(StubProvider())
    contact_id = _contact(as_alpha_admin)
    _compose(
        as_alpha_admin,
        related_entity_type="CONTACT",
        related_entity_id=contact_id,
    )

    threads = as_alpha_admin.get(
        f"/crm/emails/threads?related_entity_type=CONTACT&related_entity_id={contact_id}"
    )
    assert threads.status_code == 200, threads.text
    assert threads.json()["pagination"]["total"] == 1
    assert threads.json()["data"][0]["subject"] == "Your Q3 proposal"


async def test_rls_keeps_a_message_inside_its_tenant(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    beta: Tenant,
    clean_outbox: None,
) -> None:
    """Belt and braces beneath the application's own filter."""
    _with_provider(StubProvider())
    _compose(as_alpha_admin)

    async with session_factory() as session:
        await scope_session_to(session, beta.organization_id)
        rows = await session.execute(select(EmailMessage))
        assert list(rows.scalars().all()) == []

        threads = await session.execute(select(EmailThread))
        assert list(threads.scalars().all()) == []
