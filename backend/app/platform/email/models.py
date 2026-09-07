"""The email delivery log.

One row per message the system tried to send: who it went to, what it was,
which provider took it and what that provider called it. It answers the two
questions an administrator actually has — "did they get it?" and "why did they
get two?" — without anyone reading application logs.

Under RLS, unlike the outbox beside it, and the difference is what each holds.
An outbox row is identifiers; this one is a recipient address and a subject
line, which is customer data read by administrators inside one tenant. It gets
the ordinary tenant policy.

**The body is deliberately absent.** Storing it would put a password-reset
link — a bearer credential — in a table that administrators can read, which
would make the log a privilege-escalation route: an administrator could reset
a colleague's password by reading the email rather than by using the
administrative action that is audited. The template name and its parameters
are enough to say what was sent.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import DateTime, Enum, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

PLATFORM_SCHEMA = "platform"


class EmailDeliveryStatus(enum.StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    #: Not attempted, because the address is on the suppression list. A
    #: distinct state from FAILED: nothing went wrong, we chose not to send.
    SUPPRESSED = "SUPPRESSED"


class EmailDelivery(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One attempt to deliver one message."""

    __tablename__ = "email_deliveries"
    __table_args__ = (
        Index(
            "ix_email_deliveries_organization_id_created_at",
            "organization_id",
            "created_at",
        ),
        # At most one delivery per outbox event, which is what makes a retried
        # event safe: the second attempt finds this row and does not send
        # again. Partial, because a manual resend has no event and NULLs would
        # otherwise collide.
        Index(
            "uq_email_deliveries_outbox_event_id",
            "outbox_event_id",
            unique=True,
            postgresql_where="outbox_event_id IS NOT NULL",
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    #: 320 is the maximum length of an address per RFC 3696 errata.
    to_address: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    #: Which template produced it. Names the *kind* of message without storing
    #: the message.
    template: Mapped[str] = mapped_column(String(80), nullable=False)

    status: Mapped[EmailDeliveryStatus] = mapped_column(
        Enum(
            EmailDeliveryStatus,
            name="email_delivery_status",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=EmailDeliveryStatus.PENDING,
        server_default=EmailDeliveryStatus.PENDING.value,
    )

    #: What the provider called it — the handle for asking them what happened
    #: after we handed it over.
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: The event that caused this. Not a foreign key: the outbox is pruned on
    #: its own schedule and the log outlives it, so the constraint would either
    #: block pruning or cascade the log away with it.
    outbox_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


__all__ = ["EmailDelivery", "EmailDeliveryStatus"]
