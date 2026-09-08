"""SQLAlchemy models for the emails module.

Three tables, and the reason there are three rather than one.

**A message is not a thread.** A CRM shows a customer's correspondence as a
conversation, and a conversation is a thing with its own identity: it is filed
against a record, it has a last-activity time a list screen sorts on, and it
outlives any individual message in it. Deriving all of that from the messages
on every read — grouping by subject, taking a max — is the query that gets
slow first and the one that cannot be indexed usefully.

**A template is not a message.** It is organization configuration with a
lifecycle of its own: named, edited, shared, retired. Storing "the message we
send when a deal closes" as a message with a magic status would mean every
list of real correspondence had to remember to exclude it.

**What is deliberately not here: the transport.** No provider, no retry count,
no SMTP anything. A row in ``email_messages`` records what a person wrote and
what became of it; ``platform.email_deliveries`` records what the provider was
asked to do and said. Two tables because they answer to different people — a
salesperson asks "did my email to Ravi go out", an administrator asks "is our
mail relay working" — and because the delivery log is pruned on an operational
schedule while a customer's correspondence is retained on a business one.

**Addresses are stored as arrays, not as a join table.** A recipient here is
an address, not an entity: the person a rep types into the CC box may not be a
contact, may never become one, and giving them a row would either create junk
contacts or an orphan table nobody reads. The array is the value.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, CrmEntityType

#: Ceiling on any one recipient list. Not a database constraint people will
#: hit in normal use — it is the thing that stops a composed message becoming
#: a bulk mailer. Campaign sending is a different product concern with
#: different consent obligations, and this table is not the place it arrives
#: through the back door.
MAX_RECIPIENTS_PER_FIELD = 50

#: RFC 3696 errata: the longest an address can be.
ADDRESS_LENGTH = 320

#: Long enough for a subject nobody sensible writes, short enough to index.
SUBJECT_LENGTH = 500


class EmailDirection(enum.StrEnum):
    """Which way the message travelled.

    ``INBOUND`` exists because a thread with only our side of it is not a
    conversation. Nothing in this phase receives mail — there is no IMAP poll
    and no inbound webhook — but a reply logged by hand against a thread is
    already useful, and the alternative to this column is discovering later
    that every query assumed "message" meant "one we sent".
    """

    OUTBOUND = "OUTBOUND"
    INBOUND = "INBOUND"


class EmailStatus(enum.StrEnum):
    """Where a message is in its life.

    Four states, and the absent fifth is the interesting one: there is no
    ``SENDING``. A row that said so would be a lie the moment a worker died
    mid-send, and something would then have to decide how long "sending" may
    last before it is really "failed" — a reconciliation job, a heartbeat, a
    timeout to tune. The outbox already owns that problem and solves it with
    a claim that expires. Here, ``QUEUED`` means "the outbox has it, and the
    outbox will tell us how it went", which stays true whatever happens to any
    individual worker.
    """

    #: Composed, not sent. Visible only to its author (``policies.py``).
    DRAFT = "DRAFT"
    #: Handed to the outbox. The event is enqueued in the same transaction as
    #: this status, so the two cannot disagree.
    QUEUED = "QUEUED"
    SENT = "SENT"
    #: The provider refused it, or refused it five times. ``error`` says which.
    FAILED = "FAILED"


class EmailThread(Base, CrmEntityMixin):
    """One conversation, filed against a CRM record."""

    __tablename__ = "email_threads"
    __table_args__ = (
        Index(
            "ix_email_threads_organization_id_related",
            "organization_id",
            "related_entity_type",
            "related_entity_id",
        ),
        # The list screen's only sort. Descending in the index because it is
        # descending in the query — an ascending index would still be used but
        # would read backwards, and this one is cheap to get right.
        Index(
            "ix_email_threads_organization_id_last_message_at",
            "organization_id",
            "last_message_at",
            postgresql_using="btree",
        ),
        # Thread resolution reads this on every send.
        Index(
            "ix_email_threads_organization_id_normalized_subject",
            "organization_id",
            "normalized_subject",
        ),
        {"schema": CRM_SCHEMA},
    )

    #: The subject as first written, kept verbatim for display.
    subject: Mapped[str] = mapped_column(String(SUBJECT_LENGTH), nullable=False)

    #: The subject with reply and forward prefixes stripped and case folded,
    #: which is what messages are actually grouped on. Stored rather than
    #: computed per query: a functional index over a regexp_replace chain is
    #: both slower to build and harder to keep identical to the Python that
    #: has to produce the same answer when resolving a thread.
    normalized_subject: Mapped[str] = mapped_column(
        String(SUBJECT_LENGTH), nullable=False
    )

    #: The record this conversation is about. Optional, like an activity's
    #: link: a rep emailing somebody before they are a contact should not be
    #: forced to invent a record first, and the message is still theirs and
    #: still auditable without one.
    related_entity_type: Mapped[CrmEntityType | None] = mapped_column(
        Enum(
            CrmEntityType,
            name="crm_entity_type",
            schema=CRM_SCHEMA,
            native_enum=True,
        ),
        nullable=True,
    )
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    #: Whoever started it. Not used for visibility — see the module comment in
    #: ``authorization/catalog.py`` on why emails are not owner-scoped — but it
    #: is what a "my conversations" filter reads.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    #: Rollup maintained by ``EmailRepository.refresh_thread_rollup``, counting
    #: sent messages only. NULL until the first one leaves, which is what makes
    #: "a thread containing only an abandoned draft" sort to the bottom rather
    #: than to the top on its creation time.
    last_message_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class EmailMessage(Base, CrmEntityMixin):
    """One message: what somebody wrote, to whom, and what became of it."""

    __tablename__ = "email_messages"
    __table_args__ = (
        Index(
            "ix_email_messages_organization_id_thread_id",
            "organization_id",
            "thread_id",
        ),
        Index(
            "ix_email_messages_organization_id_related",
            "organization_id",
            "related_entity_type",
            "related_entity_id",
        ),
        Index(
            "ix_email_messages_organization_id_status",
            "organization_id",
            "status",
        ),
        # The worker's lookup, and the only unique constraint that matters
        # here: at most one message per outbox event. Partial, because a draft
        # has no event and NULLs would otherwise collide.
        Index(
            "uq_email_messages_outbox_event_id",
            "outbox_event_id",
            unique=True,
            postgresql_where="outbox_event_id IS NOT NULL",
        ),
        CheckConstraint(
            "cardinality(to_addresses) > 0",
            name="to_addresses_not_empty",
        ),
        CheckConstraint(
            f"cardinality(to_addresses) <= {MAX_RECIPIENTS_PER_FIELD} "
            f"AND cardinality(cc_addresses) <= {MAX_RECIPIENTS_PER_FIELD} "
            f"AND cardinality(bcc_addresses) <= {MAX_RECIPIENTS_PER_FIELD}",
            name="recipient_lists_within_limit",
        ),
        {"schema": CRM_SCHEMA},
    )

    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.email_threads.id", ondelete="CASCADE"),
        nullable=False,
    )

    direction: Mapped[EmailDirection] = mapped_column(
        Enum(
            EmailDirection,
            name="email_direction",
            schema=CRM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=EmailDirection.OUTBOUND,
        server_default=EmailDirection.OUTBOUND.value,
    )
    status: Mapped[EmailStatus] = mapped_column(
        Enum(EmailStatus, name="email_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=EmailStatus.DRAFT,
        server_default=EmailStatus.DRAFT.value,
    )

    subject: Mapped[str] = mapped_column(String(SUBJECT_LENGTH), nullable=False)

    #: The message as it will be sent. ``Text``, and therefore summarised
    #: rather than copied into the audit trail — see ``shared/service.py``,
    #: which is what stops a customer's correspondence being duplicated into a
    #: table every audit reader can see.
    body_text: Mapped[str] = mapped_column(Text, nullable=False)

    #: Optional rich version. Both are sent as alternatives when it is set, so
    #: a client that refuses HTML still gets a readable message; ``body_text``
    #: is never optional for that reason.
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    from_address: Mapped[str] = mapped_column(String(ADDRESS_LENGTH), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: Where replies should go when that is not the From address — a shared
    #: mailbox, typically.
    reply_to: Mapped[str | None] = mapped_column(String(ADDRESS_LENGTH), nullable=True)

    to_addresses: Mapped[list[str]] = mapped_column(
        ARRAY(String(ADDRESS_LENGTH)), nullable=False
    )
    cc_addresses: Mapped[list[str]] = mapped_column(
        ARRAY(String(ADDRESS_LENGTH)),
        nullable=False,
        default=list,
        server_default="{}",
    )
    #: Blind copies. Redacted from every reader but the sender and holders of
    #: ``emails.VIEW_ALL`` (``policies.may_see_blind_copies``) — a blind copy
    #: that a colleague can read off the record timeline is not blind.
    bcc_addresses: Mapped[list[str]] = mapped_column(
        ARRAY(String(ADDRESS_LENGTH)),
        nullable=False,
        default=list,
        server_default="{}",
    )

    #: The RFC 5322 ``Message-ID`` we minted for this message, and the parent
    #: it replies to. These are what make a reply thread in the *recipient's*
    #: mail client, not only in ours — without them every message in a
    #: conversation arrives as a new one in their inbox.
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: The template it was composed from, if any. ``SET NULL`` rather than
    #: ``RESTRICT``: retiring a template must not be blocked by, or destroy,
    #: the history of messages sent with it.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.email_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    #: Denormalized from the thread. The record timeline queries messages
    #: directly — "everything that happened to this account" — and joining
    #: through threads for a column that never changes after creation is a
    #: join per timeline render for no gain.
    related_entity_type: Mapped[CrmEntityType | None] = mapped_column(
        Enum(
            CrmEntityType,
            name="crm_entity_type",
            schema=CRM_SCHEMA,
            native_enum=True,
        ),
        nullable=True,
    )
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    sent_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Why the last attempt failed, verbatim. Shown to the sender, because
    #: "failed" with no reason leaves them with nothing to do about it.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The provider's handle, copied from the delivery receipt so a rep's
    #: message can be traced into the relay's logs without an administrator
    #: having to join two tables by hand.
    provider_message_id: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    #: The outbox event that will send, or sent, this message.
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class EmailTemplate(Base, CrmEntityMixin):
    """A reusable subject and body, with ``{{placeholders}}``.

    Note the placeholder syntax, which differs from the platform's system
    templates on purpose. Those use ``str.format`` and ``{name}``; that is
    safe for three strings held in source control and unsafe here, because a
    user's body is arbitrary text. A rep pasting a JSON snippet, a code
    sample, or a price written ``{1,200}`` into a ``str.format`` template gets
    a ``KeyError`` at send time — a message that will not go out, for a reason
    the sender cannot act on. ``{{double braces}}`` are rare in prose,
    substituted by regex, and an unknown one is left alone rather than raising.
    """

    __tablename__ = "email_templates"
    __table_args__ = (
        # A deleted template's name is free again: deletion is soft here and
        # the row never leaves, so a plain unique constraint would permanently
        # burn every name anybody ever retired.
        Index(
            "uq_email_templates_organization_id_name",
            "organization_id",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    subject: Mapped[str] = mapped_column(String(SUBJECT_LENGTH), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Free-form grouping for the picker — "Outreach", "Follow-up". A string
    #: rather than an enum: it is a label the organization chooses, and every
    #: organization sells differently.
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)

    #: ``False`` keeps it to its author, the same way a private note works.
    is_shared: Mapped[bool] = mapped_column(
        # Booleans arrive from the DB as bool; the annotation is enough.
        nullable=False,
        default=True,
        server_default="true",
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


__all__ = [
    "ADDRESS_LENGTH",
    "MAX_RECIPIENTS_PER_FIELD",
    "SUBJECT_LENGTH",
    "EmailDirection",
    "EmailMessage",
    "EmailStatus",
    "EmailTemplate",
    "EmailThread",
]
