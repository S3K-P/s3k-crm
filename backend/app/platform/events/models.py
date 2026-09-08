"""The transactional outbox (ADR-013).

An event is written **in the same transaction as the change it describes**.
That is the entire point: if the change rolls back the event goes with it, so
the system can never send "your invitation is ready" for an invitation that
does not exist, and can never lose one that does. Publishing to Redis or
calling an email API inside the request would give neither guarantee — both
succeed independently of whether the transaction commits.

**A row here holds identifiers, never data.** ``payload`` carries the ids a
handler needs to find its record and nothing else; the handler then sets
tenant scope and re-reads it through the ordinary repository. Two things
follow. The obvious one is that a payload cannot go stale between enqueue and
delivery. The one that matters more is that this table can be read across
tenants — which a worker must do — without becoming a place customer data
accumulates outside the policies that protect it everywhere else.

That is why the table is RLS-exempt, and the exemption is narrower than it
looks. ``organization_invitations`` is exempt for the same shape of reason
(see revision ``20260831_0200``): a row read while *establishing* the context
that would protect it cannot also be protected by it. Here the worker is
outside every tenant by construction — it processes all of them — and the
protection is moved to two places instead: every enqueue records the
organization explicitly, and every handler scopes itself to that organization
before touching a record. A handler that forgot would read nothing, because
the tables it reads are still under RLS.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import DateTime, Enum, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin

#: Declared locally rather than imported from ``products.crm.common``, which
#: also defines it: ARCHITECTURE-BOUNDARIES rule 1 forbids Platform importing
#: a product, and ``app.platform.audit.models`` states it the same way.
PLATFORM_SCHEMA = "platform"


class EventStatus(enum.StrEnum):
    """Where an event is in its life."""

    #: Waiting to be claimed, or waiting out a backoff after a failed attempt.
    PENDING = "PENDING"
    #: Claimed by a worker and in flight. A row stuck here means a worker died
    #: mid-attempt; ``reclaim_stalled`` returns it to PENDING.
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    #: Out of attempts. The dead-letter queue is this status, not a second
    #: table: an operator asking "what failed and why" wants the event, its
    #: payload and its last error together, and moving the row would separate
    #: them exactly when they are needed.
    DEAD = "DEAD"


class OutboxEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One thing that happened, and needs something to happen because of it."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        # The worker's only query: the oldest claimable event. Partial, because
        # succeeded events accumulate and are never selected by it — without
        # the predicate this index would grow with the table's whole history
        # while serving reads that only ever touch its head.
        Index(
            "ix_outbox_events_claimable",
            "available_at",
            postgresql_where="status = 'PENDING'",
        ),
        # For the operator view: what is stuck, and what died.
        Index("ix_outbox_events_status_created_at", "status", "created_at"),
        Index("ix_outbox_events_organization_id", "organization_id"),
        {"schema": PLATFORM_SCHEMA},
    )

    #: Nullable, and that is not an oversight. A password-reset request is made
    #: by somebody who may belong to no organization, or to several, and before
    #: any of them has been chosen. Such an event is handled without tenant
    #: scope and may therefore only touch tables that are themselves untenanted
    #: — which the handler registry enforces by requiring an event type to
    #: declare whether it is tenant-scoped.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    #: Names a handler in the registry. A string rather than an enum so that
    #: an event enqueued by a previous release, whose handler has since been
    #: removed, dead-letters with a readable reason instead of failing to load.
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)

    #: Identifiers only. See the module docstring.
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status", schema=PLATFORM_SCHEMA, native_enum=True),
        nullable=False,
        default=EventStatus.PENDING,
        server_default=EventStatus.PENDING.value,
    )

    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )

    #: Not before this instant. Set forward on each failure to space retries
    #: out, which is what stops a provider outage becoming a tight loop against
    #: a provider that is already struggling.
    available_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    #: When the current attempt was claimed. A PROCESSING row older than the
    #: stall timeout is assumed abandoned rather than slow — see
    #: ``EventRepository.reclaim_stalled``.
    claimed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: The last failure, for the operator. Truncated on write: a driver
    #: traceback can be enormous and this column is read in a list.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


#: Longest error text stored. Enough for an exception line and a short cause;
#: the full traceback belongs in the log, which is indexed and searchable.
MAX_ERROR_LENGTH = 2000


__all__ = ["MAX_ERROR_LENGTH", "EventStatus", "OutboxEvent"]
