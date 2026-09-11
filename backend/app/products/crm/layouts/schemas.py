"""Request and response contracts for the record layout builder."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.products.crm.common import CrmEntityType
from app.products.crm.layouts.evaluate import OPERATORS
from app.products.crm.layouts.models import (
    MAX_CONDITIONS_PER_RULE,
    MAX_SECTION_COLUMNS,
    LayoutStatus,
    RuleLogic,
)


class LayoutFieldConditionInput(BaseModel):
    field_key: str = Field(min_length=1, max_length=80)
    operator: str

    @field_validator("operator")
    @classmethod
    def _known_operator(cls, value: str) -> str:
        if value not in OPERATORS:
            raise ValueError(f"Unknown operator. Expected one of: {', '.join(sorted(OPERATORS))}.")
        return value

    value: object = None


class LayoutFieldRuleCreate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    target_field_key: str = Field(min_length=1, max_length=80)
    logic: RuleLogic = RuleLogic.AND
    conditions: list[LayoutFieldConditionInput] = Field(
        default_factory=list, max_length=MAX_CONDITIONS_PER_RULE
    )
    effect_visible: bool = True
    effect_required: bool | None = None


class LayoutFieldRuleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    logic: RuleLogic | None = None
    conditions: list[LayoutFieldConditionInput] | None = Field(
        default=None, max_length=MAX_CONDITIONS_PER_RULE
    )
    effect_visible: bool | None = None
    effect_required: bool | None = None
    clear_effect_required: bool = False


class LayoutFieldRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    layout_id: uuid.UUID
    name: str | None
    target_field_key: str
    logic: RuleLogic
    conditions: list[dict[str, object]]
    effect_visible: bool
    effect_required: bool | None
    position: int


class LayoutFieldCreate(BaseModel):
    section_id: uuid.UUID
    field_key: str = Field(min_length=1, max_length=80)
    position: int | None = Field(default=None, ge=0)
    column_span: int = Field(default=1, ge=1, le=MAX_SECTION_COLUMNS)
    is_visible: bool = True
    is_required_override: bool | None = None
    is_read_only: bool = False
    label_override: str | None = Field(default=None, max_length=160)
    help_text_override: str | None = Field(default=None, max_length=500)
    placeholder_override: str | None = Field(default=None, max_length=160)


class LayoutFieldUpdate(BaseModel):
    section_id: uuid.UUID | None = None
    position: int | None = Field(default=None, ge=0)
    column_span: int | None = Field(default=None, ge=1, le=MAX_SECTION_COLUMNS)
    is_visible: bool | None = None
    is_required_override: bool | None = None
    clear_required_override: bool = False
    is_read_only: bool | None = None
    label_override: str | None = Field(default=None, max_length=160)
    help_text_override: str | None = Field(default=None, max_length=500)
    placeholder_override: str | None = Field(default=None, max_length=160)


class LayoutFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    layout_id: uuid.UUID
    section_id: uuid.UUID
    field_key: str
    position: int
    column_span: int
    is_visible: bool
    is_required_override: bool | None
    is_read_only: bool
    label_override: str | None
    help_text_override: str | None
    placeholder_override: str | None


class LayoutSectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    position: int | None = Field(default=None, ge=0)
    columns: int = Field(default=1, ge=1, le=MAX_SECTION_COLUMNS)


class LayoutSectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    position: int | None = Field(default=None, ge=0)
    columns: int | None = Field(default=None, ge=1, le=MAX_SECTION_COLUMNS)


class LayoutSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    layout_id: uuid.UUID
    name: str
    position: int
    columns: int
    fields: list[LayoutFieldResponse] = Field(default_factory=list)


class RecordLayoutCreate(BaseModel):
    entity_type: CrmEntityType
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)


class RecordLayoutUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)


class RecordLayoutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    entity_type: CrmEntityType
    name: str
    description: str | None
    status: LayoutStatus
    published_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime


class RecordLayoutDetailResponse(RecordLayoutResponse):
    """The layout plus everything a builder or a form renderer needs."""

    sections: list[LayoutSectionResponse] = Field(default_factory=list)
    rules: list[LayoutFieldRuleResponse] = Field(default_factory=list)


class AvailableFieldInfo(BaseModel):
    """One field a layout for this entity type could place.

    ``placed`` is relative to the layout the caller is editing, so the builder
    can show "already on this layout" without a second lookup.
    """

    field_key: str
    label: str
    is_custom: bool
    is_required_base: bool
    placed: bool


class LayoutFieldOrderEntry(BaseModel):
    field_id: uuid.UUID
    section_id: uuid.UUID
    position: int


class LayoutReorderRequest(BaseModel):
    """Move and reorder fields (and, implicitly, sections) in one round trip.

    Mirrors ``custom_fields.reorder``'s own reasoning: a drag-and-drop canvas
    produces a *complete* new arrangement in one interaction, and a per-field
    PATCH would let two rapid drags race and leave two fields claiming the
    same position. Every live field on the layout must appear exactly once.
    """

    fields: list[LayoutFieldOrderEntry] = Field(min_length=1)


class EvaluateFieldStatesRequest(BaseModel):
    """A record's current values, for the builder's live preview.

    Merges built-in and custom values under one flat mapping, keyed by
    ``field_key`` exactly as conditions are — the same shape
    ``evaluate.effective_custom_field_states`` consumes, so the preview and the
    server-side enforcement it mirrors are provably evaluating the same
    function over the same input shape.
    """

    values: dict[str, object] = Field(default_factory=dict)


class FieldStateResponse(BaseModel):
    visible: bool
    required: bool | None


class EvaluateFieldStatesResponse(BaseModel):
    states: dict[str, FieldStateResponse]


__all__ = [
    "AvailableFieldInfo",
    "EvaluateFieldStatesRequest",
    "EvaluateFieldStatesResponse",
    "FieldStateResponse",
    "LayoutFieldConditionInput",
    "LayoutFieldCreate",
    "LayoutFieldOrderEntry",
    "LayoutFieldResponse",
    "LayoutFieldRuleCreate",
    "LayoutFieldRuleResponse",
    "LayoutFieldRuleUpdate",
    "LayoutFieldUpdate",
    "LayoutReorderRequest",
    "LayoutSectionCreate",
    "LayoutSectionResponse",
    "LayoutSectionUpdate",
    "RecordLayoutCreate",
    "RecordLayoutDetailResponse",
    "RecordLayoutResponse",
    "RecordLayoutUpdate",
]
