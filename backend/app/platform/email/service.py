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
    "EMAIL_REQUESTED",
    "IDENTITY_EMAIL_REQUESTED",
    "deliver_email_event",
    "request_email",
]
