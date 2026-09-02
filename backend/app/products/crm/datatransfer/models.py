"""Import bookkeeping: what ran, what it created, and what went wrong.

Three tables, each earning its place:

* ``import_jobs`` — one row per upload, with the counts and the settings it ran
  under. Without it "who put these four thousand rows here" has no answer.
* ``import_records`` — the ids this import *created*. This is what makes undo
  bounded and safe: it deletes exactly these and nothing else, so a record that
  existed beforehand and was merely updated cannot be destroyed by an undo.
* ``import_errors`` — the rows that did not land, with the reason. A summary
  that says "412 failed" and cannot say which is not an error report.

Zoho's model is the reference (analysis §3.3): every import is recorded, undo
is available for a bounded window, and after that the import auto-confirms.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin

#: How long an import stays undoable. Zoho uses thirty days and auto-confirms
#: after that; the same number for the same reason — long enough to notice a
#: bad import on the next month-end, short enough that the tracking rows do not
#: accumulate forever.
UNDO_WINDOW_DAYS = 30


class ImportMode(enum.StrEnum):
    """What to do with a row that matches an existing record.

    Mirrors Zoho's three-way choice, which is the one customers already
    understand from every other CRM they have migrated off.
    """

    #: Insert new records; skip anything that matches.
    ADD = "ADD"
    #: Update matches; skip anything that does not match.
    UPDATE = "UPDATE"
    #: Update matches, insert the rest.
    BOTH = "BOTH"


class ImportStatus(enum.StrEnum):
    PREVIEW = "PREVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNDONE = "UNDONE"


class ImportJob(Base, CrmEntityMixin):
    """One CSV upload, its settings, and what it produced."""

    __tablename__ = "import_jobs"
    __table_args__ = (
        Index("ix_import_jobs_organization_id_created_at", "organization_id", "created_at"),
        Index("ix_import_jobs_organization_id_module", "organization_id", "module"),
        CheckConstraint(
            "created_count >= 0 AND updated_count >= 0 "
            "AND skipped_count >= 0 AND error_count >= 0",
            name="counts_non_negative",
        ),
        {"schema": CRM_SCHEMA},
    )

    #: Registry key — ``leads``, ``accounts``, … Stored as text rather than an
    #: enum so adding an importable module is a registry edit, not a migration.
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ImportStatus] = mapped_column(
        Enum(ImportStatus, name="import_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ImportStatus.COMPLETED,
        server_default=ImportStatus.COMPLETED.value,
    )
    mode: Mapped[ImportMode] = mapped_column(
        Enum(ImportMode, name="import_mode", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ImportMode.ADD,
        server_default=ImportMode.ADD.value,
    )
    match_field: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Zoho's "don't update empty values for existing records" (analysis §3.3).
    #: The single checkbox that prevents the most common catastrophic import:
    #: a sparse spreadsheet blanking every populated field it does not mention.
    skip_empty_values: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default="true"
    )

    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    skipped_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: After this instant the import can no longer be undone. Stored rather than
    #: computed so shortening the window later cannot retroactively strip the
    #: undo from an import somebody is still inside the window on.
    undo_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    undone_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_undoable(self) -> bool:
        if self.status is not ImportStatus.COMPLETED or self.undone_at is not None:
            return False
        if self.undo_expires_at is None:
            return False
        return dt.datetime.now(dt.UTC) < self.undo_expires_at


class ImportRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One record an import **created**, so undo can remove exactly it.

    Updated records are deliberately absent. Reversing an update needs a
    before-image of every column, and storing one per row turns an import of
    fifty thousand rows into a hundred thousand writes. Undo therefore removes
    what the import added and leaves what it changed — which is stated on the
    endpoint, because an undo that silently did less than the user expected
    would be worse than one that does nothing.

    Append-only: written during the import, read by undo, never edited.
    """

    __tablename__ = "import_records"
    __table_args__ = (
        Index("ix_import_records_import_job_id", "import_job_id"),
        {"schema": CRM_SCHEMA},
    )

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.import_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Registry key of the table the id belongs to. Not a foreign key for the
    #: same reason the activity relation is not: one column cannot reference
    #: six tables. Undo resolves it through the registry.
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class ImportError(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """A row that did not land, and why."""

    __tablename__ = "import_errors"
    __table_args__ = (
        Index("ix_import_errors_import_job_id_row_number", "import_job_id", "row_number"),
        {"schema": CRM_SCHEMA},
    )

    import_job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.import_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: 1-based, counting the header as row 1, so it matches what the customer
    #: sees in their spreadsheet. An error report numbered from zero, or from
    #: the first data row, sends people to the wrong line.
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = [
    "UNDO_WINDOW_DAYS",
    "ImportError",
    "ImportJob",
    "ImportMode",
    "ImportRecord",
    "ImportStatus",
]
