"""Pydantic contracts for the emails module.

Two things here are load-bearing rather than decorative.

**Recipients are ``EmailStr``, validated at the edge.** A malformed address is
rejected by the request that contains it, not discovered by the worker three
seconds later and turned into a dead-lettered event the sender never sees. The
same validation the auth module already uses for a login, applied to a list.

**``bcc_addresses`` is optional in the response**, and ``None`` there means
"you may not see this" rather than "there were none" — the two are
distinguished by ``bcc_count``, which everyone gets. A colleague reading an
account timeline can therefore tell that a message *had* blind copies, which
matters for understanding a conversation, without learning who they were. The
redaction happens in the router, against
``policies.may_see_blind_copies``; this schema is only shaped to make it
expressible.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.products.crm.common import CrmEntityType
from app.products.crm.emails.models import (
    MAX_RECIPIENTS_PER_FIELD,
    SUBJECT_LENGTH,
    EmailDirection,
    EmailStatus,
)

#: A recipient list, bounded at both ends. The ceiling matches the database
#: check constraint deliberately: the API refuses politely with a 422 and the
#: table refuses absolutely, so a path that bypassed this schema still cannot
#: turn composed mail into a bulk send.
RecipientList = Annotated[
    list[EmailStr], Field(default_factory=list, max_length=MAX_RECIPIENTS_PER_FIELD)
]

Subject = Annotated[str, Field(min_length=1, max_length=SUBJECT_LENGTH)]


class EmailMessageCreate(BaseModel):
    """Compose a message.

    ``send`` decides whether this is a draft or an outgoing message, rather
    than a separate endpoint for each: the body is identical, and two
    endpoints would be two places to keep the recipient validation and the
    thread resolution correct.
    """

    subject: Subject
    body_text: str = Field(min_length=1)
    body_html: str | None = None

    to_addresses: Annotated[
        list[EmailStr], Field(min_length=1, max_length=MAX_RECIPIENTS_PER_FIELD)
    ]
    cc_addresses: RecipientList
    bcc_addresses: RecipientList
    reply_to: EmailStr | None = None

    #: The record this is about. Both halves or neither — enforced by
    #: ``validate_related_entity`` on the way in, which also proves the target
    #: is in the caller's organization.
    related_entity_type: CrmEntityType | None = None
    related_entity_id: uuid.UUID | None = None

    #: Continue an existing conversation. When absent, the thread is resolved
    #: from the normalized subject and the record, or created.
    thread_id: uuid.UUID | None = None
    #: The message this replies to. Supplying it sets the RFC ``In-Reply-To``
    #: header, which is what makes the reply thread in the *recipient's* mail
    #: client rather than only in ours.
    in_reply_to_message_id: uuid.UUID | None = None

    #: Recorded for reporting — "which template do people actually use" — and
    #: to let a template be retired without breaking the history of what was
    #: sent with it.
    template_id: uuid.UUID | None = None

    #: ``False`` saves a draft. ``True`` enqueues it in the same transaction.
    send: bool = False

    @model_validator(mode="after")
    def _no_duplicate_recipients(self) -> Self:
        """Reject an address that appears in more than one field.

        A person on both To and BCC receives two copies, and the second one
        reveals the blind copy to nobody's benefit. Rejecting is better than
        silently de-duplicating: which field the sender meant is genuinely
        ambiguous, and guessing it wrong sends a blind copy visibly.
        """
        seen: dict[str, str] = {}
        for field in ("to_addresses", "cc_addresses", "bcc_addresses"):
            for address in getattr(self, field):
                key = str(address).casefold()
                first = seen.get(key)
                if first is not None:
                    message = (
                        f"'{address}' appears in both {first} and {field}. "
                        "An address belongs in one recipient field."
                    )
                    raise ValueError(message)
                seen[key] = field
        return self


class EmailMessageUpdate(BaseModel):
    """Edit a draft. Everything is optional; nothing here applies once sent."""

    subject: Subject | None = None
    body_text: str | None = Field(default=None, min_length=1)
    body_html: str | None = None
    to_addresses: Annotated[
        list[EmailStr] | None, Field(default=None, max_length=MAX_RECIPIENTS_PER_FIELD)
    ] = None
    cc_addresses: Annotated[
        list[EmailStr] | None, Field(default=None, max_length=MAX_RECIPIENTS_PER_FIELD)
    ] = None
    bcc_addresses: Annotated[
        list[EmailStr] | None, Field(default=None, max_length=MAX_RECIPIENTS_PER_FIELD)
    ] = None
    reply_to: EmailStr | None = None
    template_id: uuid.UUID | None = None


class EmailMessageResponse(BaseModel):
    """One message, as the reader is allowed to see it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    thread_id: uuid.UUID
    direction: EmailDirection
    status: EmailStatus

    subject: str
    body_text: str
    body_html: str | None

    from_address: str
    from_name: str | None
    reply_to: str | None
    to_addresses: list[str]
    cc_addresses: list[str]

    #: ``None`` when the reader may not see the blind copies — which is not
    #: the same as an empty list, and ``bcc_count`` below is what tells them
    #: apart.
    bcc_addresses: list[str] | None = None
    bcc_count: int = 0

    message_id: str | None
    in_reply_to: str | None
    template_id: uuid.UUID | None

    related_entity_type: CrmEntityType | None
    related_entity_id: uuid.UUID | None
    owner_id: uuid.UUID | None

    sent_at: dt.datetime | None
    error: str | None
    provider_message_id: str | None

    #: How many files are attached. The attachments themselves are read from
    #: the platform attachments API, which owns their permissions and their
    #: download URLs; duplicating them here would mean a second place that
    #: decides who may see a file.
    attachment_count: int = 0

    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


class EmailThreadResponse(BaseModel):
    """A conversation, without its messages."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    subject: str
    related_entity_type: CrmEntityType | None
    related_entity_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    last_message_at: dt.datetime | None
    message_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


class EmailThreadDetailResponse(EmailThreadResponse):
    """A conversation with every message in it, oldest first."""

    messages: list[EmailMessageResponse]


# --- Templates --------------------------------------------------------------


class EmailTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    subject: Subject
    body_text: str = Field(min_length=1)
    body_html: str | None = None
    category: str | None = Field(default=None, max_length=80)
    is_shared: bool = True


class EmailTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    subject: Subject | None = None
    body_text: str | None = Field(default=None, min_length=1)
    body_html: str | None = None
    category: str | None = Field(default=None, max_length=80)
    is_shared: bool | None = None


class EmailTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    subject: str
    body_text: str
    body_html: str | None
    category: str | None
    is_shared: bool
    owner_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


class TemplateRenderRequest(BaseModel):
    """Preview a template against a record, before anything is sent."""

    related_entity_type: CrmEntityType | None = None
    related_entity_id: uuid.UUID | None = None


class TemplateRenderResponse(BaseModel):
    """The rendered message, and what could not be filled in.

    ``unresolved`` is the field that earns this endpoint: a composer that
    silently sent ``{{record.phone}}`` to a customer would be worse than no
    templates at all, so the placeholders that did not resolve are named and
    the UI warns before the send rather than after it.
    """

    subject: str
    body_text: str
    body_html: str | None
    unresolved: list[str]
    #: Every placeholder this record type can fill, for the insert-field menu.
    available: list[str]


__all__ = [
    "EmailMessageCreate",
    "EmailMessageResponse",
    "EmailMessageUpdate",
    "EmailTemplateCreate",
    "EmailTemplateResponse",
    "EmailTemplateUpdate",
    "EmailThreadDetailResponse",
    "EmailThreadResponse",
    "TemplateRenderRequest",
    "TemplateRenderResponse",
]
