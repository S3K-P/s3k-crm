"""Sending an email, and recording that we did.

The seam a caller uses is :func:`request_email`, which enqueues an outbox
event inside the caller's transaction. Nothing sends during a request: the
invitation is created and the intent to email recorded together, and the
worker does the rest. If the invitation rolls back, so does the email.

:func:`deliver_email_event` is the other end — the handler the worker runs.
It is **idempotent by construction**, which it has to be: delivery is
at-least-once, so this function will occasionally be asked to send a message
it has already sent. The unique index on ``outbox_event_id`` is what makes
that safe, and it is a database constraint rather than a check-then-act
because two workers can reach the check at the same instant.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.email.models import EmailDelivery, EmailDeliveryStatus
from app.platform.email.provider import (
    EmailNotConfiguredError,
    EmailProvider,
    OutboundEmail,
)
from app.platform.email.templates import TEMPLATES, render
from app.platform.events.models import OutboxEvent
from app.platform.events.service import PermanentEventError, enqueue

logger = structlog.get_logger(__name__)

#: The event type for a message that belongs to an organization. A single type
#: with a template name in the payload, rather than an event type per message:
#: the handler is identical for all of them, and a registry of a dozen
#: near-identical handlers is a dozen places for one of them to be forgotten.
EMAIL_REQUESTED = "platform.email.requested"

#: The event type for a message addressed to a global identity — today, only
#: the password reset.
#:
#: A second type rather than a nullable organization on the one above, and the
#: distinction is the dispatcher's to enforce rather than this module's. A
#: handler declares whether it is tenant-scoped, and an event of a tenant-scoped
#: type that arrives with no organization is dead-lettered instead of being run
#: unscoped (``events/service.py``). Collapsing both cases into one type would
#: mean registering the handler untenanted, and *that* would turn a future bug
#: which dropped the organization from an invitation into a silent unscoped
#: send rather than a loud failure.
#:
#: Same handler, same template registry, same delivery log. Only the contract
#: with the dispatcher differs, which is exactly the thing that differs.
IDENTITY_EMAIL_REQUESTED = "platform.email.identity_requested"


def request_email(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    to_address: str,
    template: str,
    context: dict[str, Any],
) -> OutboxEvent:
    """Ask for an email to be sent when this transaction commits.

    Args:
        organization_id: the tenant the message belongs to, or ``None`` for a
            message addressed to a global identity. Only the password reset is
            untenanted today; ``models.EmailDelivery`` sets out why it has to
            be and what stops that widening. Passing ``None`` for a message
            that *does* belong to a tenant would keep it out of that tenant's
            delivery log, so it is spelled out at every call site rather than
            defaulted.

    Raises:
        KeyError: no such template. Raised here, in the caller's request,
            rather than in the worker three seconds later — a typo should
            fail the code path that contains it.
    """
    if template not in TEMPLATES:
        msg = f"Unknown email template '{template}'."
        raise KeyError(msg)

    return enqueue(
        session,
        event_type=(
            EMAIL_REQUESTED if organization_id is not None else IDENTITY_EMAIL_REQUESTED
        ),
        payload={"to_address": to_address, "template": template, "context": context},
        organization_id=organization_id,
    )


async def deliver_email_event(
    session: AsyncSession, event: OutboxEvent, *, provider: EmailProvider
) -> None:
    """Render and send one requested email, exactly once.

    The delivery row is written **before** the send and committed on its own,
    which is what makes the exactly-once claim hold: if the process dies
    between the send and the completion, the retry finds this row and stops.
    Writing it afterwards would leave that window open in the direction that
    sends twice.
    """
    payload = event.payload
    template_name = str(payload.get("template", ""))
    to_address = str(payload.get("to_address", ""))
    if not template_name or not to_address:
        raise PermanentEventError(
            "An email event needs both 'template' and 'to_address'."
        )

    existing = await session.execute(
        select(EmailDelivery).where(EmailDelivery.outbox_event_id == event.id)
    )
    already = existing.scalar_one_or_none()
    if already is not None and already.status is EmailDeliveryStatus.SENT:
        logger.info("email_already_delivered", event_id=str(event.id))
        return

    try:
        rendered = render(template_name, dict(payload.get("context", {})))
    except KeyError as failure:
        # The template was removed, or its context is missing a field. No
        # number of retries produces the missing value.
        raise PermanentEventError(str(failure)) from failure

    delivery = already or EmailDelivery(
        organization_id=event.organization_id,
        to_address=to_address,
        subject=rendered.subject,
        template=template_name,
        provider=provider.name,
        outbox_event_id=event.id,
        status=EmailDeliveryStatus.PENDING,
    )
    if already is None:
        session.add(delivery)
        try:
            await session.flush()
        except IntegrityError:
            # Another worker claimed this event's delivery between our select
            # and our insert. Theirs wins; ours would be a duplicate send.
            await session.rollback()
            logger.info("email_delivery_raced", event_id=str(event.id))
            return

    try:
        receipt = await provider.send(
            OutboundEmail(
                to_address=to_address,
                subject=rendered.subject,
                text_body=rendered.text_body,
            )
        )
    except EmailNotConfiguredError as failure:
        # Committed before raising, like the transient path below: the
        # dispatcher rolls this session back when the handler raises, and an
        # uncommitted failure row would vanish — leaving an administrator with
        # a dead-lettered event and no delivery log entry saying why.
        await _record_failure(session, delivery, str(failure))
        # Permanent: retrying cannot configure a provider, and five attempts
        # would only delay the moment somebody notices.
        raise PermanentEventError(str(failure)) from failure
    except Exception as failure:
        # An operator watching deliveries should see the attempts, not only
        # the eventual success — a provider failing four times in five looks
        # perfectly healthy if only the last one is recorded.
        await _record_failure(
            session, delivery, f"{type(failure).__name__}: {failure}"
        )
        raise

    delivery.status = EmailDeliveryStatus.SENT
    delivery.provider_message_id = receipt.message_id
    delivery.sent_at = dt.datetime.now(dt.UTC)
    delivery.error = None
    await session.flush()
    logger.info(
        "email_delivered",
        template=template_name,
        provider=receipt.provider,
        event_id=str(event.id),
    )


#: The delivery-log template name for a message a person wrote.
#:
#: The log's ``template`` column names the *kind* of message, and user-authored
#: mail is one kind: an administrator asking "is our mail going out" wants the
#: sales email in that answer, and an operator diagnosing a failing relay wants
#: every attempt in one place rather than two. What it is not is a template —
#: there is no entry for this in ``TEMPLATES``, and rendering never consults
#: one, because the body came from a person.
CRM_EMAIL_TEMPLATE = "crm_email"


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    """The right to send one message, once.

    Wraps the delivery row rather than being it. A product's send handler is
    the caller, and ARCHITECTURE-BOUNDARIES.md does not let a product import
    ``app.platform.email.models`` — so handing back an ORM row would leave the
    caller unable to name the type it was given, and able to write through it
    if it worked it out. This is an opaque handle: get one from
    :func:`claim_delivery`, hand it to :func:`complete_delivery` or
    :func:`fail_delivery`, and never open it.
    """

    row: EmailDelivery


async def claim_delivery(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    organization_id: uuid.UUID | None,
    to_address: str,
    subject: str,
    template: str,
    provider_name: str,
) -> DeliveryClaim | None:
    """Reserve the right to send one message, exactly once.

    The seam a *product* uses to send through the platform's transport while
    keeping the platform's exactly-once guarantee. It is the same claim
    :func:`deliver_email_event` makes for the system's own messages, extracted
    so that a second sender cannot get it subtly wrong — an at-least-once
    dispatcher plus a hand-rolled check-then-act is how a customer receives the
    same email four times.

    Returns:
        The delivery row to complete, or ``None`` when this event has already
        been sent and the caller must not send again.

    The row is written and flushed **before** the send, which is what makes the
    claim hold: if the process dies between handing the message to the relay
    and recording success, the retry finds this row rather than a clean slate.
    The unique index on ``outbox_event_id`` is the actual guarantee, and it is
    a database constraint rather than a check because two workers can reach the
    check in the same instant.
    """
    existing = await session.execute(
        select(EmailDelivery).where(EmailDelivery.outbox_event_id == event_id)
    )
    already = existing.scalar_one_or_none()
    if already is not None and already.status is EmailDeliveryStatus.SENT:
        logger.info("email_already_delivered", event_id=str(event_id))
        return None
    if already is not None:
        # A previous attempt that failed. Reused rather than replaced, so the
        # log keeps one row per event and its `created_at` still says when the
        # message was first attempted.
        return DeliveryClaim(already)

    delivery = EmailDelivery(
        organization_id=organization_id,
        to_address=to_address,
        subject=subject,
        template=template,
        provider=provider_name,
        outbox_event_id=event_id,
        status=EmailDeliveryStatus.PENDING,
    )
    session.add(delivery)
    try:
        await session.flush()
    except IntegrityError:
        # Another worker claimed this event between our select and our insert.
        # Theirs wins; ours would be a duplicate send.
        await session.rollback()
        logger.info("email_delivery_raced", event_id=str(event_id))
        return None
    return DeliveryClaim(delivery)


async def delivery_is_sent(session: AsyncSession, *, event_id: uuid.UUID) -> bool:
    """Whether this event's message has actually been delivered.

    The question a caller has to ask after :func:`claim_delivery` returns
    ``None``, because that answer is ambiguous on its own: it means *either*
    "already sent, do not send again" *or* "another worker took the claim a
    moment ago". Those need opposite follow-ups. The first is a completed
    delivery whose outcome a caller may safely mirror onto its own row; the
    second is a delivery still in flight, which may yet fail, and mirroring a
    success onto it would tell the sender their message went out when it may
    be about to bounce.

    Cheap: a lookup on the unique index that made the claim in the first
    place, on a path that is rare by construction.
    """
    status = await session.scalar(
        select(EmailDelivery.status).where(EmailDelivery.outbox_event_id == event_id)
    )
    return status is EmailDeliveryStatus.SENT


async def complete_delivery(
    session: AsyncSession, claim: DeliveryClaim, *, message_id: str | None
) -> None:
    """Mark a claimed delivery sent."""
    delivery = claim.row
    delivery.status = EmailDeliveryStatus.SENT
    delivery.provider_message_id = message_id
    delivery.sent_at = dt.datetime.now(dt.UTC)
    delivery.error = None
    await session.flush()


async def fail_delivery(
    session: AsyncSession, claim: DeliveryClaim, error: str
) -> None:
    """Record a failed attempt so it outlives the handler's exception.

    Public counterpart to :func:`_record_failure`, for the same reason
    :func:`claim_delivery` is public: a product-side handler needs the failure
    to survive the rollback that follows its raise, and reimplementing the
    commit is how a delivery log ends up showing only successes.
    """
    await _record_failure(session, claim.row, error)


async def _record_failure(
    session: AsyncSession, delivery: EmailDelivery, error: str
) -> None:
    """Persist a failed attempt so it outlives the handler's exception.

    Committed rather than flushed: the dispatcher rolls the handler's session
    back on any raise, and a flushed-but-uncommitted row would disappear with
    it — which is how a delivery log ends up showing only successes.
    """
    delivery.status = EmailDeliveryStatus.FAILED
    delivery.error = error
    await session.commit()


__all__ = [
    "CRM_EMAIL_TEMPLATE",
    "EMAIL_REQUESTED",
    "IDENTITY_EMAIL_REQUESTED",
    "DeliveryClaim",
    "claim_delivery",
    "complete_delivery",
    "deliver_email_event",
    "delivery_is_sent",
    "fail_delivery",
    "request_email",
]
