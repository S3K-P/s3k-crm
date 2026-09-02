"""Pydantic contracts for import, export and bulk operations."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.products.crm.datatransfer.models import ImportMode, ImportStatus


class FieldDescriptor(BaseModel):
    """One column a module accepts, for the mapping UI."""

    name: str
    kind: str
    required: bool
    max_length: int | None = None
    choices: list[str] = Field(default_factory=list)
    #: True when the column accepts a record's *name* as well as its id, which
    #: is what a migrated file actually contains.
    accepts_name: bool = False


class ModuleDescriptor(BaseModel):
    """What one importable/exportable module looks like to the client."""

    key: str
    fields: list[FieldDescriptor]
    match_fields: list[str]
    bulk_updatable: list[str]
    required_fields: list[str]


class ModuleCatalog(BaseModel):
    modules: list[ModuleDescriptor]


class ImportRowErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    row_number: int
    field_name: str | None
    message: str


class ImportPreviewRow(BaseModel):
    """One row as the import would treat it."""

    row_number: int
    #: ``create`` · ``update`` · ``skip``
    action: str
    values: dict[str, Any]
    matched_id: uuid.UUID | None = None


class ImportPreviewResponse(BaseModel):
    """A dry run: exactly what a real import would do, having done nothing."""

    module: str
    total_rows: int
    will_create: int
    will_update: int
    will_skip: int
    error_count: int
    headers: list[str]
    mapping: dict[str, str]
    #: Columns in the file that match no field. Reported rather than dropped
    #: quietly, because a silently ignored column is data the customer believes
    #: they imported.
    unmapped_headers: list[str]
    rows: list[ImportPreviewRow]
    errors: list[ImportRowErrorResponse]


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    module: str
    filename: str
    status: ImportStatus
    mode: ImportMode
    match_field: str | None
    skip_empty_values: bool
    total_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    finished_at: dt.datetime | None
    undo_expires_at: dt.datetime | None
    undone_at: dt.datetime | None
    created_at: dt.datetime
    created_by_id: uuid.UUID | None


class ImportResultResponse(BaseModel):
    """A completed import: the job row plus the rows that did not land."""

    job: ImportJobResponse
    errors: list[ImportRowErrorResponse]


class ImportUndoResponse(BaseModel):
    """What an undo actually reversed.

    ``updates_not_reverted`` is returned rather than left implicit: undo
    removes what the import created and leaves what it changed, and a caller
    who assumed otherwise would be wrong in a way that matters.
    """

    archived: int
    updates_not_reverted: int


class BulkSelection(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)


class BulkUpdateRequest(BulkSelection):
    """Set the same fields on many records.

    Values arrive as strings and are coerced by the same code the importer
    uses, so "2026-12-31" means the same thing in both places.
    """

    values: dict[str, str] = Field(min_length=1)


class BulkOwnerRequest(BulkSelection):
    owner_id: uuid.UUID | None = None


class BulkStageRequest(BulkSelection):
    stage_id: uuid.UUID
    loss_reason: str | None = Field(default=None, max_length=255)
    win_reason: str | None = Field(default=None, max_length=255)


class BulkResultResponse(BaseModel):
    """How many records the operation actually touched.

    ``requested`` and ``changed`` differ when the selection included records
    the caller cannot see. Those are dropped rather than refused — telling a
    caller which of their guesses were real is itself a leak — so returning
    both numbers is how the UI can say "42 of 50 updated" honestly.
    """

    requested: int
    changed: int


class BulkStageResultResponse(BulkResultResponse):
    """Stage moves report their refusals, because each one has a reason."""

    failures: list[str] = Field(default_factory=list)


__all__ = [
    "BulkOwnerRequest",
    "BulkResultResponse",
    "BulkSelection",
    "BulkStageRequest",
    "BulkStageResultResponse",
    "BulkUpdateRequest",
    "FieldDescriptor",
    "ImportJobResponse",
    "ImportPreviewResponse",
    "ImportPreviewRow",
    "ImportResultResponse",
    "ImportRowErrorResponse",
    "ImportUndoResponse",
    "ModuleCatalog",
    "ModuleDescriptor",
]
