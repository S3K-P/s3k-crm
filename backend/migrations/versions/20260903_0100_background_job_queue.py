"""The background job queue.

Revision ID: 20260903_0100
Revises: 20260902_0300
Create Date: 2026-09-03 01:00:00.000000

One table. PostgreSQL rather than Redis because every requirement the queue has
— history, retries, idempotency, duplicate-execution protection, tenant scope —
is something the database already provides, and the history has to live in a
table either way (analysis §6.4, constraint C3).

The three indexes each do one job:

* ``ix_jobs_status_run_at`` is the claim query, partial on QUEUED so it stays
  small no matter how much completed history accumulates behind it.
* ``uq_jobs_organization_id_idempotency_key_live`` is the duplicate-execution
  guarantee. Partial on QUEUED/RUNNING, so a finished job releases its key and
  the same recurring job can be queued again next period. Without the partial
  predicate a nightly job could only ever run once.
* The organization indexes serve the admin screen.

RLS is enabled like every other tenant table: a payload can name records and an
error message can quote them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260903_0100"
down_revision: str | None = "20260902_0300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM_SCHEMA = "platform"

_STATUS_VALUES = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED")

#: Left for ``create_table`` to emit, which is the only place it is used.
JOB_STATUS = sa.Enum(*_STATUS_VALUES, name="job_status", schema=PLATFORM_SCHEMA)


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "jobs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=128), nullable=False),
        sa.Column("status", JOB_STATUS, nullable=False, server_default="QUEUED"),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_jobs_attempts_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_jobs_max_attempts_positive"),
        schema=PLATFORM_SCHEMA,
    )

    op.create_index("ix_jobs_organization_id", "jobs", ["organization_id"], schema=PLATFORM_SCHEMA)
    op.create_index(
        "ix_jobs_status_run_at",
        "jobs",
        ["status", "run_at"],
        schema=PLATFORM_SCHEMA,
        postgresql_where=sa.text("status = 'QUEUED'"),
    )
    op.create_index(
        "ix_jobs_organization_id_created_at",
        "jobs",
        ["organization_id", "created_at"],
        schema=PLATFORM_SCHEMA,
    )
    op.create_index(
        "ix_jobs_organization_id_job_type",
        "jobs",
        ["organization_id", "job_type"],
        schema=PLATFORM_SCHEMA,
    )
    op.create_index(
        "uq_jobs_organization_id_idempotency_key_live",
        "jobs",
        ["organization_id", "idempotency_key"],
        unique=True,
        schema=PLATFORM_SCHEMA,
        postgresql_where=sa.text(
            "idempotency_key IS NOT NULL AND status IN ('QUEUED', 'RUNNING')"
        ),
    )

    enable_rls(connection, "jobs", schema=PLATFORM_SCHEMA)


def downgrade() -> None:
    connection = op.get_bind()
    disable_rls(connection, "jobs", schema=PLATFORM_SCHEMA)
    op.drop_table("jobs", schema=PLATFORM_SCHEMA)
    sa.Enum(*_STATUS_VALUES, name="job_status", schema=PLATFORM_SCHEMA).drop(
        connection, checkfirst=True
    )
