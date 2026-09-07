"""Pydantic v2 schemas for the notifications module."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    kind: str
    title: str
    body: str | None
    entity_type: str | None
    entity_id: uuid.UUID | None
    read_at: dt.datetime | None
    created_at: dt.datetime


class UnreadCountResponse(BaseModel):
    unread_count: int


__all__ = ["NotificationResponse", "UnreadCountResponse"]
