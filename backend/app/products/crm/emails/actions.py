"""The "send templated email" action for CRM workflow automation.

Workflow automation (rules that react to a record changing) is on the roadmap
but not built. What it needs from email is one well-defined action, and this
module is that action — so the automation engine, when it arrives, calls this
rather than growing a second way to put mail in front of a customer.

**It is the composer, not a side door.** The action renders a stored template
against one record and hands the result to :meth:`EmailService.create_message`
with ``send=True`` — the same method the composer's Send button reaches. So
it inherits everything that path guarantees: the message is filed on the
record's timeline, audited, enqueued on the outbox in the caller's
transaction, delivered by the worker through Microsoft Graph exactly once, and
recorded in the delivery log with its outcome.

**It runs as somebody.** An automation acts on behalf of a user — the rule's
owner — and passes that user's :class:`Principal`. The action then demands
what the composer demands of a person: ``emails.CREATE``, ``VIEW`` on the
record plus record-level visibility, and a template that principal may read.
A rule cannot send mail its owner could not have sent by hand.

**It refuses rather than guesses.** A template with placeholders the record
cannot fill is not sent (an automated "Dear {{record.first_name}}" reaches a
customer with nobody watching), and a record with no address and no explicit
recipients is an error rather than a silent no-op.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.platform.authorization.service import PermissionDeniedError
from app.products.crm.common import CrmEntityType
from app.products.crm.emails.models import EmailMessage
from app.products.crm.emails.policies import MODULE
from app.products.crm.emails.record_access import (
    assert_template_usable,
    load_readable_record,
)
from app.products.crm.emails.schemas import EmailMessageCreate
from app.products.crm.emails.service import EmailService

#: The action's identifier in a workflow definition.
SEND_TEMPLATED_EMAIL = "crm.email.send_templated"


class UnresolvedTemplateError(ValidationFailedError):
    """The template has placeholders this record cannot fill."""

    code = "email_template_unresolved"
    message = "The email template has placeholders this record cannot fill."


class NoRecipientError(ValidationFailedError):
    """Nobody to send to: no explicit recipients and no address on the record."""

    code = "email_no_recipient"
    message = "There is no recipient: the record has no email address."


class InvalidEmailActionError(ValidationFailedError):
    """The rendered message fails the same validation the composer applies."""

    code = "email_action_invalid"
    message = "The email this action would send is not valid."


@dataclass(frozen=True, slots=True)
class SendTemplatedEmailAction:
    """Send one stored template, rendered against one record.

    ``to_addresses`` empty means "the record's own email address" — the usual
    case for a lead or a contact.
    """

    template_id: uuid.UUID
    related_entity_type: CrmEntityType
    related_entity_id: uuid.UUID
    to_addresses: tuple[str, ...] = ()
    cc_addresses: tuple[str, ...] = ()
    bcc_addresses: tuple[str, ...] = ()


async def execute_send_templated_email(
    session: AsyncSession,
    *,
    settings: Settings,
    principal: Principal,
    action: SendTemplatedEmailAction,
) -> EmailMessage:
    """Render and queue ``action``'s email, as ``principal``.

    Returns the queued message; delivery happens in the worker.

    Raises:
        PermissionDeniedError: the principal lacks ``emails.CREATE``.
        UnknownRelatedEntityError: the record does not exist or is hidden.
        NotFoundError: the template does not exist or is not the principal's.
        NoRecipientError: nobody to send to.
        UnresolvedTemplateError: placeholders the record cannot fill.
        InvalidEmailActionError: recipients or content fail validation.
    """
    if not principal.has_permission(MODULE, PermissionAction.CREATE):
        raise PermissionDeniedError

    template = await assert_template_usable(
        session, principal=principal, template_id=action.template_id
    )
    if template is None:  # unreachable: template_id is required on the action
        raise NotFoundError("Template not found.")
    record = await load_readable_record(
        session,
        principal=principal,
        entity_type=action.related_entity_type,
        entity_id=action.related_entity_id,
    )

    recipients = action.to_addresses
    if not recipients:
        address = getattr(record, "email", None)
        if not isinstance(address, str) or not address.strip():
            raise NoRecipientError
        recipients = (address.strip(),)

    service = EmailService(session, settings=settings)
    sender_address, sender_name = await service.sender_identity(
        principal.organization_id, principal.user_id
    )
    rendered = await service.render_template(
        template,
        organization_id=principal.organization_id,
        entity_type=action.related_entity_type,
        entity_id=action.related_entity_id,
        sender_name=sender_name,
        sender_email=sender_address,
        organization_name=await service.organization_name(principal.organization_id),
        principal=principal,
    )
    if rendered["unresolved"]:
        raise UnresolvedTemplateError(details={"unresolved": rendered["unresolved"]})

    try:
        # The composer's own schema, so an automated message is held to exactly
        # the rules a person's is: address syntax, subject length, recipient
        # limits and no address in two recipient fields.
        compose = EmailMessageCreate(
            subject=rendered["subject"],
            body_text=rendered["body_text"],
            body_html=rendered["body_html"],
            to_addresses=list(recipients),
            cc_addresses=list(action.cc_addresses),
            bcc_addresses=list(action.bcc_addresses),
            related_entity_type=action.related_entity_type,
            related_entity_id=action.related_entity_id,
            template_id=template.id,
            send=True,
        )
    except ValidationError as failure:
        details: dict[str, Any] = {
            "errors": [
                {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
                for error in failure.errors()
            ]
        }
        raise InvalidEmailActionError(details=details) from failure

    return await service.create_message(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        sender_address=sender_address,
        sender_name=sender_name,
        values=compose.model_dump(exclude_unset=True),
        principal=principal,
    )


__all__ = [
    "SEND_TEMPLATED_EMAIL",
    "InvalidEmailActionError",
    "NoRecipientError",
    "SendTemplatedEmailAction",
    "UnresolvedTemplateError",
    "execute_send_templated_email",
]
