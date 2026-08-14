"""SQLAlchemy models for the activities module (doc 05 "Activity", "Meeting")."""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
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
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, CrmEntityType


class ActivityType(enum.StrEnum):
    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    NOTE = "NOTE"
    TASK = "TASK"


class ActivityStatus(enum.StrEnum):
    PLANNED = "PLANNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class MeetingType(enum.StrEnum):
    IN_PERSON = "IN_PERSON"
    VIDEO = "VIDEO"
    PHONE = "PHONE"


class Activity(Base, CrmEntityMixin):
    """Something that happened, or is planned to happen, against a record.

    ``related_entity_type``/``related_entity_id`` form a polymorphic link. It
    is validated in the service layer — the target must exist *and* belong to
    the caller's organization — because a single column cannot carry a foreign
    key to five different tables.
    """

    __tablename__ = "activities"
    __table_args__ = (
        Index("ix_activities_organization_id_type_status", "organization_id", "type", "status"),
        Index(
            "ix_activities_organization_id_related",
            "organization_id",
            "related_entity_type",
            "related_entity_id",
        ),
        Index("ix_activities_organization_id_due_date", "organization_id", "due_date"),
        Index("ix_activities_organization_id_deleted_at", "organization_id", "deleted_at"),
        {"schema": CRM_SCHEMA},
    )

    type: Mapped[ActivityType] = mapped_column(
        Enum(ActivityType, name="activity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ActivityStatus] = mapped_column(
        Enum(ActivityStatus, name="activity_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ActivityStatus.PLANNED,
        server_default=ActivityStatus.PLANNED.value,
    )
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    related_entity_type: Mapped[CrmEntityType | None] = mapped_column(
        Enum(CrmEntityType, name="crm_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=True,
    )
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class Meeting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Scheduling detail for an activity of type ``MEETING``.

    Not tenant-scoped itself: it is a strict one-to-one extension of an
    activity row, which is already isolated. Reaching it requires reading the
    parent activity first, and that read is RLS-filtered.
    """

    __tablename__ = "meetings"
    __table_args__ = ({"schema": CRM_SCHEMA},)

    activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.activities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    meeting_type: Mapped[MeetingType] = mapped_column(
        Enum(MeetingType, name="meeting_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    start_time: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meeting_link: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    internal_participant_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )


__all__ = [
    "Activity",
    "ActivityStatus",
    "ActivityType",
    "Meeting",
    "MeetingType",
]
