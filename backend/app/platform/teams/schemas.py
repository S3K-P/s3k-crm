"""Pydantic v2 schemas for the teams module."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

NAME_MAX = 160


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)


class DepartmentUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    created_at: dt.datetime
    updated_at: dt.datetime


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_MAX)
    department_id: uuid.UUID | None = None


class TeamUpdate(BaseModel):
    """Partial update. ``department_id`` is tri-state, hence the sentinel.

    ``None`` is a meaningful value here — it detaches the team from its
    department — so "omitted" and "explicitly null" cannot be the same thing.
    ``model_fields_set`` distinguishes them; see the router.
    """

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    department_id: uuid.UUID | None = None


class TeamMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    joined_at: dt.datetime


class TeamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    department_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime
    #: Populated by the service; not a lazy ORM relationship, so a list
    #: response cannot turn into one query per row.
    member_count: int = 0


class TeamMemberAdd(BaseModel):
    user_id: uuid.UUID


__all__ = [
    "DepartmentCreate",
    "DepartmentResponse",
    "DepartmentUpdate",
    "TeamCreate",
    "TeamMemberAdd",
    "TeamMemberResponse",
    "TeamResponse",
    "TeamUpdate",
]
