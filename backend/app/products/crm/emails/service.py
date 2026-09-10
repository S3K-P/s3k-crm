"""Composing, sending and filing user-authored mail.

The shape of a send, and why it is this shape:

1. The request validates the record link, resolves or creates the thread, and
   writes the message with ``status = QUEUED``.
2. **In the same transaction**, it enqueues one outbox event carrying the
   message's id.
3. The worker drains the event, loads the row, sends it, and writes the
   outcome back.

Step 2 is the whole design. Nothing sends during a request, so a composer that
takes eight seconds to reach a slow relay does not make the user wait eight
seconds, and — the part that actually matters — a message the transaction
later rolls back is never sent. The alternative, sending inline and writing the
row afterwards, delivers mail for records that do not exist.

The reverse failure is closed by the outbox rather than by anything here: if
the request commits and the worker then dies, the event is still there and the
next drain picks it up. "Committed but never sent" is not a state this system
can rest in.

**Retries are the outbox's, and the exactly-once guarantee is the delivery
log's.** This module does not count attempts or schedule backoff; it raises,
and ``events/service.py`` decides. What it must get right is idempotence, and
it gets that from two independent locks — ``claim_delivery``'s unique index on
the event, and a ``FOR UPDATE`` on the message row — because the first stops
one event sending twice and the second stops two events sending one message
twice.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Final

import structlog
from fastapi import status
from sqlalchemy import ColumnElement, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError, ValidationFailedError
from app.platform.audit.service import Action as AuditAction
from app.platform.documents.service import (
    attachment_count,
    attachment_total_bytes,
    load_attached_files,
)
from app.platform.documents.storage import ObjectStorage, StorageNotConfiguredError
from app.platform.email.provider import EmailAttachment
from app.products.crm.common import CrmEntityType
from app.products.crm.emails.events import CRM_EMAIL_SEND_REQUESTED
from app.products.crm.emails.models import (
    EmailDirection,
    EmailMessage,
    EmailStatus,
    EmailTemplate,
    EmailThread,
)
from app.products.crm.emails.repository import EmailRepository
from app.products.crm.emails.templating import (
    normalize_subject,
    render_placeholders,
    unresolved_placeholders,
)
from app.products.crm.emails.variables import offered_placeholders, resolve_variables
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.relations import validate_related_entity
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService

logger = structlog.get_logger(__name__)

#: Total attachment bytes one message may carry.
#:
#: Well below the 50 MB a single attachment may be, and deliberately so: that
#: ceiling is for a file stored against a record, where the only cost is
#: storage. This one is for a file pushed through a mail relay, where the cost
#: is the relay's — most reject well under 25 MB, and a message over the limit
#: is not rejected until after it has been accepted, queued and attempted.
#: Refusing at compose time tells the sender while they can still do something
#: about it.
MAX_TOTAL_ATTACHMENT_BYTES: Final = 20 * 1024 * 1024

#: The attachment ``entity_type`` an email message is addressed by.
#:
#: A bare string rather than a member of ``CrmEntityType``, on purpose. That
#: enum is the vocabulary of *polymorphic record links* — what a note or an
#: activity may be filed against — and every one of its members resolves to a
#: customer record in ``shared/relations.py``. An email message is not one of
#: those: nothing files a note against an email. Adding it there to reuse the
#: spelling would widen a validated vocabulary to include a value that must
#: never appear in it.
EMAIL_MESSAGE_ENTITY_TYPE: Final = "EMAIL_MESSAGE"


class MessageNotEditableError(AppError):
    """A sent message is history and cannot be rewritten."""

    status_code = status.HTTP_409_CONFLICT
    code = "email_not_editable"
    message = "Only a draft can be edited. This message has already been sent."


class MessageNotSendableError(AppError):
    """Sending something that is not a draft, or is already on its way."""

    status_code = status.HTTP_409_CONFLICT
    code = "email_not_sendable"
    message = "This message has already been sent or is queued for sending."


class AttachmentsTooLargeError(ValidationFailedError):
    """More attached bytes than a relay will accept."""

    code = "email_attachments_too_large"
    message = "The attachments on this message are too large to send."


class EmailService(TenantScopedService[EmailMessage]):
    """Use cases for user-authored mail."""

    entity_name = "Email"

    def __init__(self, session: AsyncSession, *, settings: Settings) -> None:
        super().__init__(TenantScopedRepository(session, EmailMessage), EmailMessage)
        self._session = session
        self._settings = settings
        self._emails = EmailRepository(session)

    # `audit_module` derives from `__tablename__`, which is `email_messages`;
    # the permission module — and therefore the name the audit trail is
    # filtered by — is `emails`. Stated rather than derived, because this is
    # the one CRM entity whose table and module names differ.
    @property
    def audit_module(self) -> str:
        return "emails"

    @property
    def audit_entity_type(self) -> str:
        return "EMAIL_MESSAGE"

    # --- Reads -------------------------------------------------------------

    @staticmethod
    def build_message_filters(
        *,
        readable: ColumnElement[bool],
        thread_id: uuid.UUID | None = None,
        related_entity_type: CrmEntityType | None = None,
        related_entity_id: uuid.UUID | None = None,
        message_status: EmailStatus | None = None,
        direction: EmailDirection | None = None,
        search: str | None = None,
    ) -> list[ColumnElement[bool]]:
        """Predicates for a message list, starting from what may be read."""
        filters: list[ColumnElement[bool]] = [readable]
        if thread_id is not None:
            filters.append(EmailMessage.thread_id == thread_id)
        if related_entity_type is not None:
            filters.append(EmailMessage.related_entity_type == related_entity_type)
        if related_entity_id is not None:
            filters.append(EmailMessage.related_entity_id == related_entity_id)
        if message_status is not None:
            filters.append(EmailMessage.status == message_status)
        if direction is not None:
            filters.append(EmailMessage.direction == direction)
        if search:
            # Subject and recipients, which is what somebody looking for "the
            # email I sent Ravi" actually remembers. Not the body: that is a
            # `Text` column with no index, and a scan over every message in the
            # organization is not a search box, it is an outage.
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    EmailMessage.subject.ilike(term),
                    # The recipient list flattened to one string and matched
                    # case-insensitively. ``ARRAY.any`` with an ILIKE operator
                    # would express "some element matches" more precisely, but
                    # it is untypeable against SQLAlchemy's stubs and this
                    # produces the same answer for the question being asked —
                    # people type part of an address, in whatever case they
                    # happen to remember it.
                    func.array_to_string(EmailMessage.to_addresses, ",").ilike(term),
                )
            )
        return filters

    async def list_messages(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[EmailMessage], int]:
        return await self._emails.list_messages(
            organization_id, params=params, filters=filters
        )

    async def get_readable_message(
        self,
        message_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        viewer_id: uuid.UUID | None,
    ) -> EmailMessage:
        """Fetch one message the viewer may read, or 404.

        Somebody else's draft produces the same 404 as a message that does not
        exist — confirming it were there would defeat the point of it being
        unsent.
        """
        message = await self.get_or_404(message_id, organization_id)
        if message.status is EmailStatus.DRAFT and message.created_by_id != viewer_id:
            raise NotFoundError(f"{self.entity_name} not found.")
        return message

    @staticmethod
    def build_thread_filters(
        *,
        related_entity_type: CrmEntityType | None = None,
        related_entity_id: uuid.UUID | None = None,
    ) -> list[ColumnElement[bool]]:
        """Predicates for a conversation list.

        No readability predicate, unlike messages: a thread carries no content
        of its own, and its ``message_count`` already excludes drafts — so a
        conversation containing only somebody's unsent draft appears as an
        empty one rather than being hidden, which is the honest answer. The
        drafts themselves are still invisible when the thread is opened.
        """
        filters: list[ColumnElement[bool]] = []
        if related_entity_type is not None:
            filters.append(EmailThread.related_entity_type == related_entity_type)
        if related_entity_id is not None:
            filters.append(EmailThread.related_entity_id == related_entity_id)
        return filters

    async def list_threads(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[EmailThread], int]:
        return await self._emails.list_threads(
            organization_id, params=params, filters=filters
        )

    async def get_thread_or_404(
        self, thread_id: uuid.UUID, organization_id: uuid.UUID
    ) -> EmailThread:
        thread = await self._emails.get_thread(thread_id, organization_id)
        if thread is None:
            raise NotFoundError("Conversation not found.")
        return thread

    async def thread_messages(
        self,
        thread_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        readable: ColumnElement[bool],
    ) -> Sequence[EmailMessage]:
        return await self._emails.thread_messages(
            thread_id, organization_id, readable=readable
        )

    # --- Composing ---------------------------------------------------------

    async def sender_identity(
        self, organization_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> tuple[str, str | None]:
        """The address and display name a message from ``actor_id`` goes out as.

        Read through the organizations service rather than from
        ``platform.users`` directly: a product may not query the identity
        tables itself (ARCHITECTURE-BOUNDARIES.md rule 2), and
        ``member_directory`` is the seam that exists for it. Doing it here
        rather than in the router also avoids the trap that catches a naive
        implementation — ``principal.user.profile`` is a lazy relationship the
        request never eager-loaded, so touching it raises ``MissingGreenlet``
        under asyncio rather than returning a name.

        Falls back to the configured system address when the actor is not a
        member, which is a state that should not arise inside an authorized
        request and must not produce a message with an empty ``From``.
        """
        from app.platform.organizations.service import organizations_for_session

        if actor_id is None:
            return self._settings.email_from_address, None

        directory = await organizations_for_session(self._session).member_directory(
            organization_id, [actor_id]
        )
        identity = directory.get(actor_id)
        if identity is None:
            return self._settings.email_from_address, None
        return identity.email, (identity.full_name or None)

    async def organization_name(self, organization_id: uuid.UUID) -> str | None:
        """The tenant's name, for ``{{organization.name}}``."""
        from app.platform.organizations.service import organizations_for_session

        organization = await organizations_for_session(
            self._session
        ).get_organization(organization_id)
        return organization.name

    async def create_message(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        sender_address: str,
        sender_name: str | None,
        values: dict[str, Any],
    ) -> EmailMessage:
        """Write a draft, or write and enqueue a message.

        The thread is resolved before the message exists, so a message is
        never briefly threadless — every read path can assume ``thread_id`` is
        set, and none of them needs a null branch.
        """
        payload = dict(values)
        send_now = bool(payload.pop("send", False))
        thread_id = payload.pop("thread_id", None)
        reply_to_message_id = payload.pop("in_reply_to_message_id", None)

        related_type = payload.get("related_entity_type")
        related_id = payload.get("related_entity_id")
        await validate_related_entity(
            self._session,
            entity_type=related_type,
            entity_id=related_id,
            organization_id=organization_id,
        )

        parent = None
        if reply_to_message_id is not None:
            parent = await self.get_readable_message(
                reply_to_message_id, organization_id, viewer_id=actor_id
            )
            # A reply belongs to its parent's conversation, whatever the client
            # said. Honouring a mismatched `thread_id` would split a
            # conversation in half at the point somebody replied.
            thread_id = parent.thread_id

        thread = await self._resolve_thread(
            organization_id=organization_id,
            actor_id=actor_id,
            thread_id=thread_id,
            subject=str(payload["subject"]),
            related_entity_type=related_type,
            related_entity_id=related_id,
        )

        payload["thread_id"] = thread.id
        payload["direction"] = EmailDirection.OUTBOUND
        payload["from_address"] = sender_address
        payload["from_name"] = sender_name
        payload["owner_id"] = actor_id
        payload["status"] = EmailStatus.QUEUED if send_now else EmailStatus.DRAFT
        payload["in_reply_to"] = parent.message_id if parent is not None else None
        # Minted here rather than by the provider, because a reply has to be
        # able to cite it and replies are composed long before the send.
        payload["message_id"] = self._mint_message_id()
        # A message inherits its conversation's record when it was not given
        # one, which is what keeps a reply on the same account timeline as the
        # message it answers.
        if related_id is None:
            payload["related_entity_type"] = thread.related_entity_type
            payload["related_entity_id"] = thread.related_entity_id

        # `create` is the inherited path: organization, authorship and the
        # audit entry all come from it, in this transaction.
        message = await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )

        if send_now:
            await self._assert_attachments_sendable(message)
            await self._enqueue_send(message)
            # The same trail entry ``send_message`` writes. Composing with
            # ``send: true`` and saving-then-sending are one act to the user
            # and must be one act in the audit log: without this, the fastest
            # path to putting mail in front of a customer — the one the
            # composer's Send button takes — would be the only one that left
            # no record of the send.
            await self._record_send(message, actor_id=actor_id)
        await self._emails.refresh_thread_rollup(thread)
        return message

    async def update_draft(
        self,
        message: EmailMessage,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> EmailMessage:
        """Edit an unsent message.

        Raises:
            MessageNotEditableError: it has already been sent or queued.
        """
        self._require_draft(message, MessageNotEditableError)
        payload = dict(values)
        # The conversation, the record and the identity of the sender are
        # fixed at composition. Moving a message between threads or records
        # after the fact rewrites history on both.
        for immutable in (
            "thread_id",
            "related_entity_type",
            "related_entity_id",
            "from_address",
            "from_name",
            "status",
            "message_id",
            "in_reply_to",
        ):
            payload.pop(immutable, None)
        return await self.update(message, actor_id=actor_id, values=payload)

    async def send_message(
        self, message: EmailMessage, *, actor_id: uuid.UUID | None
    ) -> EmailMessage:
        """Enqueue a draft for delivery.

        Raises:
            MessageNotSendableError: it is not a draft.
            AttachmentsTooLargeError: more bytes than a relay will take.
        """
        self._require_draft(message, MessageNotSendableError)
        await self._assert_attachments_sendable(message)

        message.status = EmailStatus.QUEUED
        message.error = None
        message.updated_by_id = actor_id
        await self._session.flush()
        await self._enqueue_send(message)

        thread = await self.get_thread_or_404(
            message.thread_id, message.organization_id
        )
        await self._emails.refresh_thread_rollup(thread)
        await self._record_send(message, actor_id=actor_id)
        return message

    async def _record_send(
        self, message: EmailMessage, *, actor_id: uuid.UUID | None
    ) -> None:
        """Append the trail entry for a message being put on its way.

        One method, called from both send paths, because the two are the same
        act to the user and an entry written in only one of them is worse than
        none — it makes the trail look complete while omitting whichever route
        people actually use.
        """
        await self.audit.record(
            organization_id=message.organization_id,
            action=AuditAction.UPDATED,
            module=self.audit_module,
            entity_type=self.audit_entity_type,
            entity_id=message.id,
            entity_label=message.subject,
            actor_id=actor_id,
            # Counts, not addresses: the trail says how far a message went
            # without becoming a second copy of the recipient list that every
            # audit reader can browse. The addresses are on the message itself,
            # behind this module's own visibility rules.
            details={
                "to_count": len(message.to_addresses),
                "cc_count": len(message.cc_addresses),
                "bcc_count": len(message.bcc_addresses),
                "thread_id": str(message.thread_id),
            },
        )

    async def discard_draft(
        self, message: EmailMessage, *, actor_id: uuid.UUID | None
    ) -> EmailMessage:
        """Archive a message. Drafts are the author's; sent mail is history.

        A sent message can still be archived — a record's timeline is allowed
        to be tidied — but it is a soft delete like everything else here, so
        the correspondence is recoverable and the audit entry stands.
        """
        archived = await self.soft_delete(message, actor_id=actor_id)
        thread = await self._emails.get_thread(
            message.thread_id, message.organization_id
        )
        if thread is not None:
            await self._emails.refresh_thread_rollup(thread)
        return archived

    # --- Templates ---------------------------------------------------------

    async def render_template(
        self,
        template: EmailTemplate,
        *,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType | None,
        entity_id: uuid.UUID | None,
        sender_name: str | None,
        sender_email: str | None,
        organization_name: str | None,
    ) -> dict[str, Any]:
        """Fill a template's placeholders from one record.

        The link is validated first, so a template cannot be used to probe for
        records in another tenant by rendering against a guessed id.
        """
        await validate_related_entity(
            self._session,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=organization_id,
        )
        variables = await resolve_variables(
            self._session,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            sender_name=sender_name,
            sender_email=sender_email,
            organization_name=organization_name,
        )
        subject = render_placeholders(template.subject, variables)
        body_text = render_placeholders(template.body_text, variables)
        body_html = (
            render_placeholders(template.body_html, variables)
            if template.body_html
            else None
        )
        unresolved = sorted(
            set(unresolved_placeholders(template.subject, variables))
            | set(unresolved_placeholders(template.body_text, variables))
            | set(
                unresolved_placeholders(template.body_html or "", variables)
            )
        )
        return {
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "unresolved": unresolved,
            "available": offered_placeholders(entity_type),
        }

    # --- Internals ---------------------------------------------------------

    async def _resolve_thread(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        thread_id: uuid.UUID | None,
        subject: str,
        related_entity_type: CrmEntityType | None,
        related_entity_id: uuid.UUID | None,
    ) -> EmailThread:
        """Find the conversation this message belongs to, or start one."""
        if thread_id is not None:
            return await self.get_thread_or_404(thread_id, organization_id)

        normalized = normalize_subject(subject)
        existing = await self._emails.find_thread_by_subject(
            organization_id,
            normalized_subject=normalized,
            related_entity_type=(
                related_entity_type.value if related_entity_type else None
            ),
            related_entity_id=related_entity_id,
        )
        if existing is not None:
            return existing

        thread = EmailThread(
            organization_id=organization_id,
            subject=subject,
            normalized_subject=normalized,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
            owner_id=actor_id,
            created_by_id=actor_id,
            updated_by_id=actor_id,
            message_count=0,
        )
        self._session.add(thread)
        await self._session.flush()
        return thread

    async def _enqueue_send(self, message: EmailMessage) -> None:
        """Enqueue the delivery event, in this transaction.

        Imported here rather than at module scope only to keep the import
        graph honest about direction: this is a product asking the platform's
        outbox to carry something, which is an allowed dependency, and reading
        it at the call site says so.
        """
        from app.platform.events.service import enqueue

        event = enqueue(
            self._session,
            event_type=CRM_EMAIL_SEND_REQUESTED,
            payload={"message_id": str(message.id)},
            organization_id=message.organization_id,
        )
        # Stored so the delivery log and the message can be lined up, and so a
        # second send of the same message is visible as a second event rather
        # than as a mystery.
        message.outbox_event_id = event.id
        await self._session.flush()

    async def attachment_counts(
        self, organization_id: uuid.UUID, messages: Sequence[EmailMessage]
    ) -> dict[uuid.UUID, int]:
        """How many files hang off each of ``messages``.

        One query per message, and deliberately so rather than a join: the
        attachments table belongs to the Platform, and a product reaching
        across the boundary to join it is exactly what
        ARCHITECTURE-BOUNDARIES.md forbids. A page is at most fifty rows, the
        lookup is a covered index on ``(organization_id, entity_type,
        entity_id)``, and the alternative is a second module owning half of
        this one's query.
        """
        counts: dict[uuid.UUID, int] = {}
        for message in messages:
            counts[message.id] = await attachment_count(
                self._session,
                organization_id=organization_id,
                entity_type=EMAIL_MESSAGE_ENTITY_TYPE,
                entity_id=message.id,
            )
        return counts

    async def _assert_attachments_sendable(self, message: EmailMessage) -> None:
        """Refuse a message whose attachments a relay would bounce."""
        total = await attachment_total_bytes(
            self._session,
            organization_id=message.organization_id,
            entity_type=EMAIL_MESSAGE_ENTITY_TYPE,
            entity_id=message.id,
        )
        if total > MAX_TOTAL_ATTACHMENT_BYTES:
            raise AttachmentsTooLargeError(
                details={
                    "total_bytes": total,
                    "limit_bytes": MAX_TOTAL_ATTACHMENT_BYTES,
                }
            )

    def _mint_message_id(self) -> str:
        """An RFC 5322 ``Message-ID`` for a message not yet sent."""
        return f"<{uuid.uuid4()}@{self._settings.email_message_id_domain}>"

    @staticmethod
    def _require_draft(message: EmailMessage, failure: type[AppError]) -> None:
        if message.status is not EmailStatus.DRAFT:
            raise failure


async def load_attachments_for_send(
    session: AsyncSession,
    storage: ObjectStorage | None,
    *,
    organization_id: uuid.UUID,
    message_id: uuid.UUID,
) -> tuple[EmailAttachment, ...]:
    """Read a message's attachment bytes, ready to hand to a provider.

    At module scope rather than on the service because the caller is the
    worker, which has no principal and no request. ``storage`` is passed in
    for the same reason the provider is: it is built once per process by the
    composition root, and a handler constructing its own would reparse
    settings and build a signer for every message.

    A storage read that fails raises, and the outbox retries: storage being
    briefly unavailable is exactly the transient condition the retry policy
    exists for. Sending without the file instead would deliver a message whose
    body refers to an attachment that is not there, which the recipient cannot
    tell from the sender having forgotten it.
    """
    count = await attachment_count(
        session,
        organization_id=organization_id,
        entity_type=EMAIL_MESSAGE_ENTITY_TYPE,
        entity_id=message_id,
    )
    if count == 0:
        return ()
    if storage is None:
        # Files are attached but there is nowhere to read them from. Permanent
        # rather than transient: no number of retries configures object
        # storage, and the sender should be told instead of kept waiting.
        raise StorageNotConfiguredError

    files = await load_attached_files(
        session,
        storage,
        organization_id=organization_id,
        entity_type=EMAIL_MESSAGE_ENTITY_TYPE,
        entity_id=message_id,
    )
    return tuple(
        EmailAttachment(
            filename=file.name, mime_type=file.mime_type, content=file.content
        )
        for file in files
    )




__all__ = [
    "EMAIL_MESSAGE_ENTITY_TYPE",
    "MAX_TOTAL_ATTACHMENT_BYTES",
    "AttachmentsTooLargeError",
    "EmailService",
    "MessageNotEditableError",
    "MessageNotSendableError",
    "load_attachments_for_send",
]
