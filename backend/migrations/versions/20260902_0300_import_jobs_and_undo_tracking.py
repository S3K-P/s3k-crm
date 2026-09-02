"""Import bookkeeping: jobs, the undo trail, and per-row errors.

Revision ID: 20260902_0300
Revises: 20260902_0200
Create Date: 2026-09-02 03:00:00.000000

Three tables behind CSV import (analysis §5.8 — import is "the single biggest
adoption blocker"; §6.3 sequences it accordingly).

``import_jobs`` records one row per upload: the settings it ran under and the
counts it produced. ``import_records`` lists the ids that import **created**,
which is what makes undo bounded and safe — it removes exactly those, so a
record that existed beforehand and was merely updated cannot be destroyed by an
undo. ``import_errors`` holds the rows that did not land, numbered as the
customer's spreadsheet numbers them.

All three are tenant-scoped and RLS-enabled like every other CRM table. That
matters more here than usual: an import job names a file and a row count, and
an error row can quote a value out of somebody's customer list.

``import_records`` and ``import_errors`` carry no ``deleted_at``. Both are
append-only trails written once and read once; archiving a row of an audit
trail rather than keeping it would defeat the point of having one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_rls, enable_rls

revision: str = "20260902_0300"
down_revision: str | None = "20260902_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM_SCHEMA = "crm"

#: Both types are used by ``import_jobs`` and nothing else, so ``create_table``
#: is left to emit their CREATE TYPE. Creating them here as well is what the
#: first draft did, and SQLAlchemy then issued the CREATE twice — the second
#: from inside ``create_table`` — which fails as DuplicateObject. The drop in
#: ``downgrade`` is still explicit, because dropping a table does not drop the
#: types its columns used.
_MODE_VALUES = ("ADD", "UPDATE", "BOTH")
_STATUS_VALUES = ("PREVIEW", "COMPLETED", "FAILED", "UNDONE")

IMPORT_MODE = sa.Enum(*_MODE_VALUES, name="import_mode", schema=CRM_SCHEMA)
IMPORT_STATUS = sa.Enum(*_STATUS_VALUES, name="import_status", schema=CRM_SCHEMA)


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "import_jobs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("status", IMPORT_STATUS, nullable=False, server_default="COMPLETED"),
        sa.Column("mode", IMPORT_MODE, nullable=False, server_default="ADD"),
        sa.Column("match_field", sa.String(length=64), nullable=True),
        sa.Column(
            "skip_empty_values", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undo_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "created_count >= 0 AND updated_count >= 0 "
            "AND skipped_count >= 0 AND error_count >= 0",
            name="ck_import_jobs_counts_non_negative",
        ),
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_import_jobs_organization_id", "import_jobs", ["organization_id"], schema=CRM_SCHEMA
    )
    op.create_index(
        "ix_import_jobs_deleted_at", "import_jobs", ["deleted_at"], schema=CRM_SCHEMA
    )
    op.create_index(
        "ix_import_jobs_organization_id_created_at",
        "import_jobs",
        ["organization_id", "created_at"],
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_import_jobs_organization_id_module",
        "import_jobs",
        ["organization_id", "module"],
        schema=CRM_SCHEMA,
    )

    op.create_table(
        "import_records",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("import_job_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("record_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            [f"{CRM_SCHEMA}.import_jobs.id"],
            name="fk_import_records_import_job_id_import_jobs",
            ondelete="CASCADE",
        ),
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_import_records_organization_id",
        "import_records",
        ["organization_id"],
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_import_records_import_job_id",
        "import_records",
        ["import_job_id"],
        schema=CRM_SCHEMA,
    )

    op.create_table(
        "import_errors",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("import_job_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"],
            [f"{CRM_SCHEMA}.import_jobs.id"],
            name="fk_import_errors_import_job_id_import_jobs",
            ondelete="CASCADE",
        ),
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_import_errors_organization_id",
        "import_errors",
        ["organization_id"],
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_import_errors_import_job_id_row_number",
        "import_errors",
        ["import_job_id", "row_number"],
        schema=CRM_SCHEMA,
    )

    for table in ("import_jobs", "import_records", "import_errors"):
        enable_rls(connection, table, schema=CRM_SCHEMA)


def downgrade() -> None:
    connection = op.get_bind()

    for table in ("import_errors", "import_records", "import_jobs"):
        disable_rls(connection, table, schema=CRM_SCHEMA)

    op.drop_table("import_errors", schema=CRM_SCHEMA)
    op.drop_table("import_records", schema=CRM_SCHEMA)
    op.drop_table("import_jobs", schema=CRM_SCHEMA)

    sa.Enum(*_STATUS_VALUES, name="import_status", schema=CRM_SCHEMA).drop(
        connection, checkfirst=True
    )
    sa.Enum(*_MODE_VALUES, name="import_mode", schema=CRM_SCHEMA).drop(
        connection, checkfirst=True
    )
