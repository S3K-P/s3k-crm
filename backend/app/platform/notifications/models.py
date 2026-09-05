"""SQLAlchemy models for the notifications module (Phase A; see events.py).

A ``Notification`` is one thing a single user is told about: a meeting
reminder that has come due, a task that is due or overdue, or a record newly
assigned to them. It belongs to exactly one recipient inside one organization
and is never shared — there is no "team inbox".

The link to the record a notification is about is a polymorphic
``entity_type``/``entity_id`` pair rather than a foreign key, the same shape
``platform.attachments`` already uses (see
:class:`app.platform.documents.models.Attachment`): Platform may not import
the CRM tables a real foreign key would need to reference
(ARCHITECTURE-BOUNDARIES.md rule 1). Nothing here re-validates that the pair
still resolves to a live record — a notification is a record of something that
was true when it was created, and it stays legible even if the record it
points at is later deleted, the same way an audit log entry does.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

PLATFORM_SCHEMA = "platform"


class NotificationKind(enum.StrEnum):
    """What a notification is about (writer-side vocabulary).

    Stored as plain text on the row (see :attr:`Notification.kind`), not a
    database enum — matching ``AuditAction``'s own reasoning
    (``app.platform.audit.models``): a new kind must not require an
    ``ALTER TYPE`` and a coordinated deploy. Adding one is a new member here
    plus a new call site, never a migration.
    """

    MEETING_REMINDER = "MEETING_REMINDER"
    TASK_DUE = "TASK_DUE"
    RECORD_ASSIGNED = "RECORD_ASSIGNED"


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One notification for one recipient."""

    __tablename__ = "notifications"
    __table_args__ = (
        # The list endpoint's own access pattern: "my unread items, newest
        # first" and "all of mine, newest first" are both satisfied by one
        # index with recipient leading, the way every other CRM index in this
        # codebase leads with organization_id for the same reason.
        Index(
            "ix_notifications_organization_id_recipient_user_id_created_at",
            "organization_id",
            "recipient_user_id",
            "created_at",
        ),
        # De-duplicates a reminder the scheduler has already fired: the same
        # (recipient, dedupe key) pair is refused a second row by the
        # database rather than checked-then-inserted, which is what makes
        # ``NotificationService.dispatch_due_reminders`` safe under retries
        # and overlapping ticks — see service.py. NULL is exempt from
        # uniqueness in PostgreSQL, so a direct ``notify()`` call that passes
        # no dedupe key (record-assignment notifications) is never refused by
        # this constraint.
        #
        # A unique ``Index`` rather than a ``UniqueConstraint``, matching
        # ``platform.teams``' own non-partial uniqueness declarations
        # (``uq_team_memberships_team_id_user_id``): the migration creates the
        # same shape via ``op.create_index(..., unique=True)``, and a
        # constraint here would be a mismatch autogenerate would flag against
        # it.
        Index(
            "uq_notifications_org_id_recipient_user_id_dedupe_key",
            "organization_id",
            "recipient_user_id",
            "dedupe_key",
            unique=True,
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    #: Platform user id. Not a foreign key, for the same reason
    #: ``Opportunity.owner_id`` and every other owner column in this codebase
    #: is not one: a notification must remain legible after its recipient
    #: leaves the platform, and Platform tables do not need a hard dependency
    #: on a *specific row* of the users table to record who a message was for.
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: What this notification is about, generically — see the module
    #: docstring. Both are ``None`` for a notification with no linked record.
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    #: Set only by the reminder scheduler; see the unique index above. A
    #: direct ``notify()`` call (record assignment) passes ``None`` and is
    #: never deduplicated — each assignment is its own notification.
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


__all__ = ["Notification", "NotificationKind"]
