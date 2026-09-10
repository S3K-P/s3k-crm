"""The worker end of a send: take one event, put one message on the wire.

Registered by the composition root, not here — a handler that delivers a CRM
message through the Platform's provider needs both layers, and
``app/api/router.py`` is the only module allowed to see both.

**Idempotence comes from two locks, not one, and they close different holes.**

``claim_delivery`` holds a unique index on the outbox event id. That is what
makes *one event* safe to run twice, which the dispatcher will do: delivery is
at-least-once, and a worker that dies between the relay accepting a message and
the row recording it leaves an event that looks unprocessed.

``lock_message_for_delivery`` takes ``FOR UPDATE`` on the message row. That is
what makes *one message* safe under two events, which the first lock cannot
help with: a user pressing "send" twice on a slow connection produces two
distinct events, each with its own clean claim, both pointing at the same
message. The status check after the lock is the actual guard; the lock is what
makes the check-then-act sound.

Neither is redundant, and removing either produces a customer receiving the
same email twice — the failure that is impossible to apologise for convincingly
because the evidence is in their inbox.
"""

from __future__ import annotations

import datetime as dt
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.documents.storage import ObjectStorage, StorageNotConfiguredError
from app.platform.email.provider import (
    EmailAttachment,
    EmailNotConfiguredError,
    EmailProvider,
    OutboundEmail,
)
from app.platform.email.service import (
    CRM_EMAIL_TEMPLATE,
    DeliveryClaim,
    claim_delivery,
    complete_delivery,
    delivery_is_sent,
    fail_delivery,
)
from app.platform.events.service import OutboxEvent, PermanentEventError
from app.products.crm.emails.models import EmailMessage, EmailStatus
from app.products.crm.emails.repository import EmailRepository
from app.products.crm.emails.service import load_attachments_for_send

logger = structlog.get_logger(__name__)


async def deliver_crm_email_event(
    session: AsyncSession,
    event: OutboxEvent,
    *,
    provider: EmailProvider,
    storage: ObjectStorage | None,
) -> None:
    """Send the message this event names, exactly once."""
    message = await _load_message(session, event)
    if message is None:
        return

    claim = await claim_delivery(
        session,
        event_id=event.id,
        organization_id=event.organization_id,
        # The first recipient stands for the message in the delivery log,
        # which has one address column. The rest are on the message itself —
        # duplicating a recipient list into a table administrators browse
        # would put a customer's colleagues in front of every audit reader for
        # no operational gain.
        to_address=message.to_addresses[0],
        subject=message.subject,
        template=CRM_EMAIL_TEMPLATE,
        provider_name=provider.name,
    )
    if claim is None:
        # Either the message has already gone out under this event, or another
        # worker took the claim a moment ago. Both mean "do not send here", and
        # they mean opposite things afterwards — so ask which it was rather
        # than assuming. Recording SENT on a delivery that is merely *in
        # flight* would tell the sender their message left when it may still
        # bounce, and the worker that actually holds the claim will record the
        # real outcome either way.
        if await delivery_is_sent(session, event_id=event.id):
            await _mark_sent_if_stale(session, message)
        return

    outbound = OutboundEmail(
        to_address=message.to_addresses[0],
        to_addresses=tuple(message.to_addresses[1:]),
        cc_addresses=tuple(message.cc_addresses),
        bcc_addresses=tuple(message.bcc_addresses),
        reply_to=message.reply_to,
        from_name=message.from_name,
        subject=message.subject,
        text_body=message.body_text,
        html_body=message.body_html,
        message_id=message.message_id,
        in_reply_to=message.in_reply_to,
        attachments=await _load_attachments(session, storage, message),
    )

    try:
        receipt = await provider.send(outbound)
    except (EmailNotConfiguredError, StorageNotConfiguredError) as failure:
        # Committed before raising, like the transient path below: the
        # dispatcher rolls the handler's session back, and an uncommitted
        # failure would vanish — leaving the sender with a message stuck on
        # QUEUED and nothing saying why.
        await _record_failure(session, message, claim, str(failure))
        # Permanent: retrying cannot configure a provider or a bucket, and
        # five attempts would only delay somebody noticing.
        raise PermanentEventError(str(failure)) from failure
    except Exception as failure:
        await _record_failure(
            session, message, claim, f"{type(failure).__name__}: {failure}"
        )
        # Transient as far as this module knows. The outbox decides how many
        # times to try and when to give up.
        raise

    await complete_delivery(session, claim, message_id=receipt.message_id)

    message.status = EmailStatus.SENT
    message.sent_at = dt.datetime.now(dt.UTC)
    message.provider_message_id = receipt.message_id
    message.error = None
    await session.flush()

    thread = await EmailRepository(session).get_thread(
        message.thread_id, message.organization_id
    )
    if thread is not None:
        # The conversation's "last activity" is what a list screen sorts on,
        # and until this moment it reflected when the message was composed.
        await EmailRepository(session).refresh_thread_rollup(thread)

    logger.info(
        "crm_email_delivered",
        message_id=str(message.id),
        thread_id=str(message.thread_id),
        provider=receipt.provider,
        recipients=len(outbound.envelope_recipients()),
    )


async def _load_message(
    session: AsyncSession, event: OutboxEvent
) -> EmailMessage | None:
    """Resolve and lock the message an event names, or decide not to send.

    Returns ``None`` for every case where sending would be wrong but retrying
    would be pointless — each of which is a normal outcome rather than a
    failure, and none of which should dead-letter an event an operator then
    has to triage.
    """
    raw_id = str(event.payload.get("message_id", ""))
    if not raw_id:
        raise PermanentEventError("A CRM email event needs a 'message_id'.")
    if event.organization_id is None:
        # The dispatcher refuses a tenant-scoped event without an organization
        # before reaching a handler; this is belt and braces, and it is what
        # lets everything below treat the tenant as known.
        raise PermanentEventError("A CRM email event must carry an organization.")

    try:
        message_id = uuid.UUID(raw_id)
    except ValueError as failure:
        raise PermanentEventError(f"Malformed message_id '{raw_id}'.") from failure

    message = await EmailRepository(session).lock_message_for_delivery(
        message_id, event.organization_id
    )
    if message is None:
        # The row is gone — a hard delete, or a restore that rolled the table
        # back past it. There is nothing to send and nothing to fix.
        logger.warning("crm_email_message_missing", message_id=raw_id)
        return None
    if message.deleted_at is not None:
        # Archived between the enqueue and the drain. The user changed their
        # mind after pressing send; honouring the archive is what they meant.
        logger.info("crm_email_message_archived", message_id=raw_id)
        return None
    if message.status is EmailStatus.SENT:
        # A second event for a message the first one already sent.
        logger.info("crm_email_already_sent", message_id=raw_id)
        return None
    if not message.to_addresses:
        # The check constraint makes this unreachable from the API; it is here
        # because an empty recipient list would otherwise index-error below,
        # and a crash reads like a bug in the worker rather than bad data.
        raise PermanentEventError("A message with no recipients cannot be sent.")
    return message


async def _load_attachments(
    session: AsyncSession, storage: ObjectStorage | None, message: EmailMessage
) -> tuple[EmailAttachment, ...]:
    """The message's files, or nothing."""
    return await load_attachments_for_send(
        session,
        storage,
        organization_id=message.organization_id,
        message_id=message.id,
    )


async def _record_failure(
    session: AsyncSession,
    message: EmailMessage,
    claim: DeliveryClaim,
    error: str,
) -> None:
    """Persist a failed attempt on both rows, so it outlives the raise.

    The message is marked ``FAILED`` rather than left ``QUEUED`` even though
    the outbox may retry it. That looks wrong for a moment and is not: the
    sender's screen must show the last thing that actually happened, and
    "queued" for four minutes while backoff runs is a message they believe is
    on its way. A successful retry sets it back to ``SENT``.
    """
    message.status = EmailStatus.FAILED
    message.error = error
    await fail_delivery(session, claim, error)


async def _mark_sent_if_stale(session: AsyncSession, message: EmailMessage) -> None:
    """Reconcile a message left behind by a delivery that already succeeded.

    Reached when the claim says "already sent" but the message row does not
    say so — the window where a worker recorded the delivery and died before
    recording the message. Rare, and the alternative to fixing it here is a
    message stuck on ``QUEUED`` for ever, which is the one state a user can do
    nothing about.
    """
    if message.status is EmailStatus.SENT:
        return
    message.status = EmailStatus.SENT
    message.sent_at = message.sent_at or dt.datetime.now(dt.UTC)
    message.error = None
    await session.flush()
    logger.info("crm_email_status_reconciled", message_id=str(message.id))




__all__ = ["deliver_crm_email_event"]
