"""Request and response contracts for workflow automation.

Thin, like ``blueprints.schemas`` for the same reason its own docstring
gives: whether a trigger's field is real, whether an action applies to this
entity type, whether an operator is one the evaluator understands — none of
that can be checked without the database and the entity's own model, so this
layer bounds sizes and shapes and ``WorkflowRuleService._validate`` does the
rest.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.products.crm.workflows.models import (
    MAX_ACTIONS,
    MAX_CONDITIONS,
    WorkflowEntityType,
    WorkflowRunStatus,
    WorkflowTriggerType,
)


class WorkflowConditionSchema(BaseModel):
    """One ``{"field_key", "operator", "value"}`` condition.

    The operator vocabulary (``equals``, ``contains``, ``greater_than``, ...)
    is the closed set ``app.products.crm.layouts.evaluate.OPERATORS`` already
    defines and is checked against there, not here — restating it as a
    ``Literal`` would be a second copy of that list to keep in step with the
    first.
    """

    field_key: Annotated[str, Field(min_length=1, max_length=160)]
    operator: Annotated[str, Field(min_length=1, max_length=32)]
    value: Any = None


class WorkflowActionSchema(BaseModel):
    """One action. ``type``-specific fields are validated by the service,
    which alone knows which ones a given ``type`` and ``entity_type`` allow —
    see ``WorkflowActionType`` in ``.models`` for what each shape needs."""

    model_config = ConfigDict(extra="allow")

    type: str


class WorkflowCreate(BaseModel):
    """A new workflow. Always created inactive — see ``WorkflowRule.is_active``."""

    name: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str | None, Field(default=None, max_length=500)] = None
    entity_type: WorkflowEntityType
    trigger_type: WorkflowTriggerType
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    condition_logic: Annotated[str, Field(default="AND", pattern="^(AND|OR)$")] = "AND"
    conditions: Annotated[
        list[WorkflowConditionSchema], Field(default_factory=list, max_length=MAX_CONDITIONS)
    ]
    actions: Annotated[
        list[WorkflowActionSchema], Field(default_factory=list, max_length=MAX_ACTIONS)
    ]
    position: Annotated[int, Field(default=0, ge=0, le=10_000)] = 0


class WorkflowUpdate(BaseModel):
    """A partial update. Every field accepted and refused-if-invalid by the
    service rather than omitted, for the reason ``BlueprintUpdate`` states:
    a silently-dropped field would report success for a change that never
    happened."""

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=160)] = None
    description: Annotated[str | None, Field(default=None, max_length=500)] = None
    entity_type: WorkflowEntityType | None = None
    trigger_type: WorkflowTriggerType | None = None
    trigger_config: dict[str, Any] | None = None
    condition_logic: Annotated[str | None, Field(default=None, pattern="^(AND|OR)$")] = None
    conditions: Annotated[
        list[WorkflowConditionSchema] | None, Field(default=None, max_length=MAX_CONDITIONS)
    ] = None
    actions: Annotated[
        list[WorkflowActionSchema] | None, Field(default=None, max_length=MAX_ACTIONS)
    ] = None
    is_active: bool | None = None
    position: Annotated[int | None, Field(default=None, ge=0, le=10_000)] = None


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    entity_type: WorkflowEntityType
    trigger_type: WorkflowTriggerType
    trigger_config: dict[str, Any]
    condition_logic: str
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    is_active: bool
    position: int
    created_at: dt.datetime
    updated_at: dt.datetime


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_rule_id: uuid.UUID
    entity_type: WorkflowEntityType
    record_id: uuid.UUID
    trigger: str
    correlation_id: uuid.UUID
    depth: int
    status: WorkflowRunStatus
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    action_results: list[dict[str, Any]]
    error: str | None
    retry_count: int
    started_at: dt.datetime
    finished_at: dt.datetime | None
    created_at: dt.datetime


__all__ = [
    "WorkflowActionSchema",
    "WorkflowConditionSchema",
    "WorkflowCreate",
    "WorkflowResponse",
    "WorkflowRunResponse",
    "WorkflowUpdate",
]
