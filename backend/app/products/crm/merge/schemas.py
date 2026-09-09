"""Request and response contracts for merging duplicates.

Small, because a merge takes almost no input: which record survives, which
records do not, and — for the fields where they disagree — which value wins.
Everything else about the operation is decided by the catalogue and the rules
in :mod:`.service`, not by the request.

``field_choices`` is deliberately a flat ``{field: source}`` map rather than
``{field: value}``. A client that could post *values* could write anything into
the survivor under the guise of a merge, bypassing every rule the record's own
PATCH endpoint enforces. Naming a source instead means the value can only ever
be one already in one of the records being merged.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from app.products.crm.common import CrmEntityType
from app.products.crm.merge.catalog import MAX_MERGE_RECORDS

#: ``"primary"`` or a duplicate's UUID, as text.
#:
#: Validated as a shape here and resolved against the actual duplicates in the
#: service — a syntactically fine id that is not in the merge is a 422 naming
#: the field, not a silently ignored choice.
FieldSource = Annotated[str, Field(min_length=1, max_length=64)]


class MergePreviewRequest(BaseModel):
    """Which records a merge screen is about to show."""

    primary_id: uuid.UUID
    duplicate_ids: Annotated[
        list[uuid.UUID], Field(min_length=1, max_length=MAX_MERGE_RECORDS - 1)
    ]

    @field_validator("duplicate_ids")
    @classmethod
    def _reject_repeats(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        # Deduplicated in the service anyway, but a repeated id in the request
        # is a client bug worth surfacing rather than absorbing: it usually
        # means a selection list double-counted, and the same list is about to
        # be posted to the merge endpoint.
        if len(set(value)) != len(value):
            raise ValueError("A duplicate is listed more than once.")
        return value


class MergeRequest(MergePreviewRequest):
    """The merge itself.

    ``field_choices`` may be omitted entirely, which means "keep the surviving
    record's values" — with the one narrow fallback the service documents:
    a field blank on the survivor is filled when exactly one duplicate has a
    value for it.
    """

    field_choices: Annotated[
        dict[str, FieldSource], Field(default_factory=dict, max_length=200)
    ]


class MergeConflict(BaseModel):
    """One field the records disagree about."""

    field: str
    #: Every record's value for this field, keyed by record id as text — the
    #: survivor included, so the screen can render one row per record without a
    #: second lookup.
    values: dict[str, Any]
    #: What the field becomes if the caller chooses nothing. Reported so the
    #: screen can show the outcome of pressing Merge without touching anything.
    default: Any


class MergePreviewResponse(BaseModel):
    """What a merge would change.

    ``related_counts`` is what turns the confirmation from a leap of faith into
    a statement: "12 activities and 3 notes will move to the surviving record".
    """

    primary_id: uuid.UUID
    duplicate_ids: list[uuid.UUID]
    conflicts: list[MergeConflict]
    related_counts: dict[str, int]


class MergeResultResponse(BaseModel):
    """The survivor, and what was retired into it.

    Returns the id rather than the whole record: the client re-reads it through
    the entity's own endpoint, which is the one place that knows how to shape
    that entity's response and applies its own permissions on the way.
    """

    id: uuid.UUID
    entity_type: CrmEntityType
    merged_ids: list[uuid.UUID]


__all__ = [
    "MergeConflict",
    "MergePreviewRequest",
    "MergePreviewResponse",
    "MergeRequest",
    "MergeResultResponse",
]
