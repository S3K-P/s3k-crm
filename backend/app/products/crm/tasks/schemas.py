"""Pydantic contracts for tasks."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.products.crm.common import CrmEntityType, Priority
from app.products.crm.tasks.models import TaskStatus


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: Priority = Priority.MEDIUM
    due_date: dt.datetime | None = None
    owner_id: uuid.UUID | None = None
    assigned_to_id: uuid.UUID | None = None
    related_entity_type: CrmEntityType | None = None
    related_entity_id: uuid.UUID | None = None


class TaskCreate(TaskBase):
    """Everything needed to open a task."""


class TaskUpdate(BaseModel):
    """Partial update. Only supplied fields are written."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    due_date: dt.datetime | None = None
    owner_id: uuid.UUID | None = None
    assigned_to_id: uuid.UUID | None = None
    related_entity_type: CrmEntityType | None = None
    related_entity_id: uuid.UUID | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: Priority
    due_date: dt.datetime | None
    completed_at: dt.datetime | None
    owner_id: uuid.UUID | None
    assigned_to_id: uuid.UUID | None
    related_entity_type: CrmEntityType | None
    related_entity_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


class TaskStatusCounts(BaseModel):
    """Per-status totals, for board columns and summary chips."""

    counts: dict[str, int]


__all__ = ["TaskCreate", "TaskResponse", "TaskStatusCounts", "TaskUpdate"]
