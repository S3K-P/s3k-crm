"""Request and response contracts for blueprints.

Thin, deliberately. Almost nothing here can be checked without the database —
whether a state exists, whether a field is real, whether a move is one the
built-in machine allows — so this layer bounds sizes and shapes and the service
does the rest. Splitting the rules across both would mean two answers to
"is this configuration valid" and one of them eventually going stale.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.products.crm.blueprints.models import (
    MAX_REQUIRED_FIELDS,
    BlueprintField,
)
from app.products.crm.common import CrmEntityType


class BlueprintCreate(BaseModel):
    """A new blueprint.

    ``is_active`` is absent: a blueprint is always created inactive, because
    activation is the moment a process starts refusing people's work and doing
    it in the same request that creates an empty one would activate a process
    describing nothing.
    """

    name: Annotated[str, Field(min_length=1, max_length=160)]
    field: BlueprintField
    description: Annotated[str | None, Field(default=None, max_length=500)] = None


class BlueprintUpdate(BaseModel):
    """A partial update.

    ``field`` is accepted and then refused by the service rather than being
    left out — omitting it means pydantic drops it silently and the response
    reports success for a change that did not happen.
    """

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=160)] = None
    description: Annotated[str | None, Field(default=None, max_length=500)] = None
    field: BlueprintField | None = None
    is_active: bool | None = None


class BlueprintTransitionCreate(BaseModel):
    """One move, and what it requires.

    ``from_state`` defaults to ``"*"`` — "from anywhere" — which is what an
    administrator means when they say a state has requirements regardless of
    where the record was.
    """

    to_state: Annotated[str, Field(min_length=1, max_length=64)]
    from_state: Annotated[str, Field(default="*", min_length=1, max_length=64)] = "*"
    name: Annotated[str | None, Field(default=None, max_length=160)] = None
    required_fields: Annotated[
        list[str], Field(default_factory=list, max_length=MAX_REQUIRED_FIELDS)
    ]
    #: A ``module.ACTION`` code, checked against the catalogue by the service.
    required_permission: Annotated[str | None, Field(default=None, max_length=80)] = None
    require_note: bool = False
    position: Annotated[int, Field(default=0, ge=0, le=10_000)] = 0


class BlueprintTransitionUpdate(BaseModel):
    to_state: Annotated[str | None, Field(default=None, min_length=1, max_length=64)] = None
    from_state: Annotated[str | None, Field(default=None, min_length=1, max_length=64)] = None
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=160)] = None
    required_fields: Annotated[
        list[str] | None, Field(default=None, max_length=MAX_REQUIRED_FIELDS)
    ] = None
    required_permission: Annotated[str | None, Field(default=None, max_length=80)] = None
    require_note: bool | None = None
    position: Annotated[int | None, Field(default=None, ge=0, le=10_000)] = None


class BlueprintTransitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    blueprint_id: uuid.UUID
    name: str
    from_state: str
    to_state: str
    required_fields: list[str]
    required_permission: str | None
    require_note: bool
    position: int


class BlueprintResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    field: BlueprintField
    entity_type: CrmEntityType
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime

    #: Populated from one grouped query, never per row.
    transition_count: int = 0
    #: Present on the detail endpoint, absent from list rows.
    transitions: list[BlueprintTransitionResponse] | None = None


class BlueprintStateOption(BaseModel):
    """A state the governed field can hold.

    Read from the source of truth per request — the enum, or the tenant's live
    pipeline stages — because a configuration screen offering a stage retired
    last week is how unsatisfiable processes get built.
    """

    value: str
    label: str


class BlueprintStatesResponse(BaseModel):
    field: BlueprintField
    states: list[BlueprintStateOption]


__all__ = [
    "BlueprintCreate",
    "BlueprintResponse",
    "BlueprintStateOption",
    "BlueprintStatesResponse",
    "BlueprintTransitionCreate",
    "BlueprintTransitionResponse",
    "BlueprintTransitionUpdate",
    "BlueprintUpdate",
]
