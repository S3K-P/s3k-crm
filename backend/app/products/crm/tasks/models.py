"""SQLAlchemy models for the tasks module (doc 05 "Task")."""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import DateTime, Enum, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, CrmEntityType, Priority


class TaskStatus(enum.StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Task(Base, CrmEntityMixin):
    """A unit of work, optionally attached to a CRM record."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index(
            "ix_tasks_organization_id_assigned_to_id_status",
            "organization_id",
            "assigned_to_id",
            "status",
        ),
        Index("ix_tasks_organization_id_due_date", "organization_id", "due_date"),
        Index(
            "ix_tasks_organization_id_related",
            "organization_id",
            "related_entity_type",
            "related_entity_id",
        ),
        Index("ix_tasks_organization_id_deleted_at", "organization_id", "deleted_at"),
        {"schema": CRM_SCHEMA},
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=TaskStatus.PENDING.value,
    )
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="crm_priority", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=Priority.MEDIUM,
        server_default=Priority.MEDIUM.value,
    )
    due_date: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    related_entity_type: Mapped[CrmEntityType | None] = mapped_column(
        Enum(CrmEntityType, name="crm_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=True,
    )
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


__all__ = ["Task", "TaskStatus"]
