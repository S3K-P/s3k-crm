"""Request and response contracts for custom fields and picklists.

ORM models are never returned directly; these are the wire format.

``CustomFieldValues`` at the bottom is the piece the rest of the CRM imports:
it is how the five record types that support custom fields declare the shape of
their ``custom_fields`` property without each restating the rules.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.products.crm.common import CrmEntityType
from app.products.crm.custom_fields.models import MAX_FIELDS_PER_ENTITY, CustomFieldType
from app.products.crm.shared.schemas import MAX_CUSTOM_FIELD_VALUES, CustomFieldValues

#: The most custom values one request may carry, re-exported from ``shared``.
#:
#: A request cannot legitimately set more fields than the record type has, and
#: capping it stops an unbounded object being validated key by key before the
#: "unknown field" check can reject it.
MAX_SUBMITTED_VALUES = MAX_CUSTOM_FIELD_VALUES

ApiName = Annotated[str, Field(min_length=1, max_length=64)]
Label = Annotated[str, Field(min_length=1, max_length=160)]


# ---------------------------------------------------------------------------
# Picklists
# ---------------------------------------------------------------------------


class PicklistOptionCreate(BaseModel):
    value: Annotated[str, Field(min_length=1, max_length=120)]
    #: Defaults to the value. An administrator adding "EMEA" should not have to
    #: type it twice to get a list that renders.
    label: Annotated[str | None, Field(default=None, max_length=160)] = None
    position: Annotated[int, Field(default=0, ge=0, le=10_000)] = 0
    is_active: bool = True
    is_default: bool = False


class PicklistOptionUpdate(BaseModel):
    value: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    label: Annotated[str | None, Field(default=None, min_length=1, max_length=160)] = None
    position: Annotated[int | None, Field(default=None, ge=0, le=10_000)] = None
    is_active: bool | None = None
    is_default: bool | None = None


class PicklistOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    picklist_id: uuid.UUID
    value: str
    label: str
    position: int
    is_active: bool
    is_default: bool


class PicklistCreate(BaseModel):
    name: Label
    api_name: ApiName
    description: Annotated[str | None, Field(default=None, max_length=500)] = None
    #: Options may be supplied inline. Creating a list and its options in one
    #: request is one transaction, so a half-built list cannot survive a
    #: failure partway through the administrator's intent.
    options: Annotated[list[PicklistOptionCreate], Field(max_length=200)] = []


class PicklistUpdate(BaseModel):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=160)] = None
    description: Annotated[str | None, Field(default=None, max_length=500)] = None


class PicklistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    api_name: str
    description: str | None
    #: Populated by the router from one grouped query, never per row.
    option_count: int = 0
    #: Present on the detail endpoint, absent from list rows.
    options: list[PicklistOptionResponse] | None = None


# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------


class CustomFieldBase(BaseModel):
    label: Label
    help_text: Annotated[str | None, Field(default=None, max_length=500)] = None
    is_required: bool = False
    is_active: bool = True
    position: Annotated[int, Field(default=0, ge=0, le=10_000)] = 0
    default_value: Annotated[str | None, Field(default=None, max_length=1_000)] = None
    picklist_id: uuid.UUID | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: Annotated[int | None, Field(default=None, ge=0, le=32_000)] = None
    max_length: Annotated[int | None, Field(default=None, ge=1, le=32_000)] = None
    pattern: Annotated[str | None, Field(default=None, max_length=255)] = None


class CustomFieldCreate(CustomFieldBase):
    entity_type: CrmEntityType
    api_name: ApiName
    field_type: CustomFieldType


class CustomFieldUpdate(BaseModel):
    """A partial update.

    ``api_name``, ``field_type`` and ``entity_type`` are *accepted* and then
    refused by the service, rather than being left out of this schema.
    Changing any of them would strand the values already stored, so neither
    outcome is "apply it" — but omitting them here means pydantic drops them
    silently and the response reports success for a change that did not
    happen. Accepting them buys a 422 that says why.
    """

    entity_type: CrmEntityType | None = None
    api_name: str | None = None
    field_type: CustomFieldType | None = None
    label: Annotated[str | None, Field(default=None, min_length=1, max_length=160)] = None
    help_text: Annotated[str | None, Field(default=None, max_length=500)] = None
    is_required: bool | None = None
    is_active: bool | None = None
    position: Annotated[int | None, Field(default=None, ge=0, le=10_000)] = None
    default_value: Annotated[str | None, Field(default=None, max_length=1_000)] = None
    picklist_id: uuid.UUID | None = None
    min_value: float | None = None
    max_value: float | None = None
    min_length: Annotated[int | None, Field(default=None, ge=0, le=32_000)] = None
    max_length: Annotated[int | None, Field(default=None, ge=1, le=32_000)] = None
    pattern: Annotated[str | None, Field(default=None, max_length=255)] = None


class CustomFieldReorder(BaseModel):
    """The complete display order for one record type's fields."""

    entity_type: CrmEntityType
    order: Annotated[list[uuid.UUID], Field(min_length=1, max_length=MAX_FIELDS_PER_ENTITY)]


class CustomFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: CrmEntityType
    api_name: str
    label: str
    field_type: CustomFieldType
    help_text: str | None
    is_required: bool
    is_active: bool
    position: int
    default_value: str | None
    picklist_id: uuid.UUID | None
    min_value: float | None
    max_value: float | None
    min_length: int | None
    max_length: int | None
    pattern: str | None
    #: The live options, inlined on the schema endpoint so a form can be
    #: rendered from one response instead of one request per picklist field.
    options: list[PicklistOptionResponse] | None = None


class EntitySchemaResponse(BaseModel):
    """Everything a client needs to render one record type's custom section."""

    entity_type: CrmEntityType
    fields: list[CustomFieldResponse]


# ---------------------------------------------------------------------------
# Values on a record
# ---------------------------------------------------------------------------


class CustomFieldValuePatch(BaseModel):
    """Standalone update of a record's custom values.

    Exists so a record's built-in fields and its custom ones can be saved
    independently by a UI that renders them as separate panels — without the
    custom panel having to re-send the whole record and risk clobbering an
    edit somebody else made to a built-in field in between.
    """

    custom_fields: CustomFieldValues

    @field_validator("custom_fields")
    @classmethod
    def _reject_non_string_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        # JSON object keys are strings by definition, but this schema is also
        # reached from the CSV import path, where they are whatever the header
        # row produced.
        for key in value:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Custom field names must be non-empty strings.")
        return value


__all__ = [
    "MAX_SUBMITTED_VALUES",
    "CustomFieldCreate",
    "CustomFieldReorder",
    "CustomFieldResponse",
    "CustomFieldUpdate",
    "CustomFieldValuePatch",
    "CustomFieldValues",
    "EntitySchemaResponse",
    "PicklistCreate",
    "PicklistOptionCreate",
    "PicklistOptionResponse",
    "PicklistOptionUpdate",
    "PicklistResponse",
    "PicklistUpdate",
]
