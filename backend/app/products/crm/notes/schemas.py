"""Pydantic contracts for notes."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.products.crm.common import CrmEntityType
from app.products.crm.notes.models import NoteVisibility


class NoteCreate(BaseModel):
    """A note is always attached to something — the link is not optional."""

    content: str = Field(min_length=1)
    related_entity_type: CrmEntityType
    related_entity_id: uuid.UUID
    visibility: NoteVisibility = NoteVisibility.TEAM


class NoteUpdate(BaseModel):
    """Partial update. The link itself is immutable once written."""

    content: str | None = Field(default=None, min_length=1)
    visibility: NoteVisibility | None = None


class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    content: str
    visibility: NoteVisibility
    author_id: uuid.UUID | None
    related_entity_type: CrmEntityType
    related_entity_id: uuid.UUID
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


__all__ = ["NoteCreate", "NoteResponse", "NoteUpdate"]
