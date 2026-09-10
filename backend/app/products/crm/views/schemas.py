"""Request and response contracts for saved views.

The filter document is the interesting part. It is the list endpoints' own
query vocabulary — including Phase E's ``cf_*`` custom-field filters — kept as
free-form JSON rather than modelled as columns, so a view keeps working when a
module gains a filter and the one place that has to understand a filter stays
the endpoint that already did.

That freedom is bounded here rather than trusted. A stored document is read on
every list render and sent to every client that can see the view, so it is
capped in count, in key length and in value size, and restricted to scalars and
short lists of them. What it must *not* become is a place to stash arbitrary
nested data on the server under the guise of a saved search.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.products.crm.common import CrmEntityType
from app.products.crm.views.models import ViewVisibility

#: Ceilings on one stored filter document.
#:
#: Chosen from what a list screen can actually produce: a dozen filters is far
#: more than any of the CRM list screens offers, and a filter value is a status
#: name, a uuid or a search term. Anything beyond this is not a saved search.
MAX_FILTERS = 24
MAX_FILTER_KEY = 64
MAX_FILTER_VALUE = 500
MAX_FILTER_LIST = 50
MAX_COLUMNS = 60
MAX_COLUMN_KEY = 80

FilterDocument = Annotated[dict[str, Any], Field(max_length=MAX_FILTERS)]


def _validate_filters(value: dict[str, Any]) -> dict[str, Any]:
    """Refuse a document that is not a flat set of scalar filters.

    Nested objects are rejected outright rather than truncated: a filter the
    endpoint cannot express is one the view would silently ignore, and a view
    that quietly drops half its filters shows the wrong records under a name
    that promises the right ones.
    """
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Filter names must be non-empty strings.")
        if len(key) > MAX_FILTER_KEY:
            raise ValueError(f"Filter names may be at most {MAX_FILTER_KEY} characters.")

        entries = item if isinstance(item, list) else [item]
        if isinstance(item, list) and len(item) > MAX_FILTER_LIST:
            raise ValueError(f"A filter may hold at most {MAX_FILTER_LIST} values.")
        for entry in entries:
            if entry is None or isinstance(entry, bool | int | float):
                continue
            if isinstance(entry, str):
                if len(entry) > MAX_FILTER_VALUE:
                    raise ValueError(
                        f"A filter value may be at most {MAX_FILTER_VALUE} characters."
                    )
                continue
            raise ValueError(
                "A filter value must be text, a number, a boolean, or a list of those."
            )
    return value


def _validate_columns(value: list[str]) -> list[str]:
    """Column keys are names, not expressions.

    Not checked against the entity's real columns, deliberately: the set of
    columns a *screen* can show includes derived ones the database has no
    knowledge of (``lead_count``, ``member_count``), and a client asking for a
    column that no longer exists should get a list missing that column, not a
    422 that makes the whole view unopenable.
    """
    for key in value:
        if not key.strip():
            raise ValueError("Column names must be non-empty.")
        if len(key) > MAX_COLUMN_KEY:
            raise ValueError(f"Column names may be at most {MAX_COLUMN_KEY} characters.")
    return value


class SavedViewBase(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str | None, Field(default=None, max_length=500)] = None
    visibility: ViewVisibility = ViewVisibility.PRIVATE
    filters: FilterDocument = Field(default_factory=dict)
    columns: Annotated[list[str], Field(default_factory=list, max_length=MAX_COLUMNS)]
    sort_by: Annotated[str | None, Field(default=None, max_length=80)] = None
    sort_dir: Literal["asc", "desc"] | None = None
    is_default: bool = False

    @field_validator("filters")
    @classmethod
    def _check_filters(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_filters(value)

    @field_validator("columns")
    @classmethod
    def _check_columns(cls, value: list[str]) -> list[str]:
        return _validate_columns(value)


class SavedViewCreate(SavedViewBase):
    """A new view. ``owner_id`` is absent on purpose.

    It is taken from the authenticated principal. A client that could name
    another owner could plant a view in a colleague's list and — through
    ``is_default`` — change which one their list screen opens with.
    """

    entity_type: CrmEntityType


class SavedViewUpdate(BaseModel):
    """A partial update.

    ``entity_type`` and ``owner_id`` are absent: moving a view to another
    record type would leave its filters naming columns that entity has not got,
    and reassigning it would hand somebody a view they never made.
    """

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=120)] = None
    description: Annotated[str | None, Field(default=None, max_length=500)] = None
    visibility: ViewVisibility | None = None
    filters: FilterDocument | None = None
    columns: Annotated[list[str] | None, Field(default=None, max_length=MAX_COLUMNS)] = None
    sort_by: Annotated[str | None, Field(default=None, max_length=80)] = None
    sort_dir: Literal["asc", "desc"] | None = None
    is_default: bool | None = None

    @field_validator("filters")
    @classmethod
    def _check_filters(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else _validate_filters(value)

    @field_validator("columns")
    @classmethod
    def _check_columns(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _validate_columns(value)


class SavedViewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: CrmEntityType
    name: str
    description: str | None
    owner_id: uuid.UUID
    visibility: ViewVisibility
    filters: dict[str, Any]
    columns: list[str]
    sort_by: str | None
    sort_dir: str | None
    is_default: bool
    created_at: dt.datetime
    updated_at: dt.datetime

    #: Whether *this* caller may change it. Computed per request from the
    #: caller's identity and permissions, so the UI can hide an edit control it
    #: would otherwise offer and then fail — while the server still decides.
    can_edit: bool = False


__all__ = [
    "MAX_COLUMNS",
    "MAX_FILTERS",
    "SavedViewCreate",
    "SavedViewResponse",
    "SavedViewUpdate",
]
