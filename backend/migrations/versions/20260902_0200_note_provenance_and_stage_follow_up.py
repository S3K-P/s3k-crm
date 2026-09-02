"""Note provenance, and declarative follow-up tasks on pipeline stages.

Revision ID: 20260902_0200
Revises: 20260902_0100
Create Date: 2026-09-02 02:00:00.000000

**1. ``crm.notes.origin_entity_type`` / ``origin_entity_id``.**

Lead conversion carries the lead's notes onto the records it produced. Zoho
copies them to the deal, the account *and* the contact; S3K moves them instead,
because three copies of the same paragraph immediately start to drift and there
is then no answer to "which one is right".

Moving costs the one thing copying preserved: a moved note no longer shows that
it was written while the record was still a lead. These two nullable columns
record that, so provenance survives without duplicating text. NULL on every
note that has never moved, which is nearly all of them.

**2. ``crm.pipeline_stages.follow_up_task_title`` / ``follow_up_task_days``.**

"When a deal reaches Proposal, someone should chase it in three days" is
configuration a sales manager owns, not code. Two nullable columns on the stage
express it exactly, and the service creates the task on entry.

This is deliberately *not* a workflow designer (analysis §4.4, §5.6): no rule
table, no condition language, no action registry. A stage either names a
follow-up or it does not.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0200"
down_revision: str | None = "20260902_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM_SCHEMA = "crm"

#: The enum already exists (created by ``8224845a67ac``); referencing it with
#: ``create_type=False`` adds a column of that type without trying to define it
#: a second time, which would fail.
CRM_ENTITY_TYPE = sa.Enum(
    "ACCOUNT",
    "CONTACT",
    "LEAD",
    "OPPORTUNITY",
    "CAMPAIGN",
    name="crm_entity_type",
    schema=CRM_SCHEMA,
    create_type=False,
)


def upgrade() -> None:
    # --- 1. Note provenance ------------------------------------------------
    op.add_column(
        "notes",
        sa.Column(
            "origin_entity_type",
            CRM_ENTITY_TYPE,
            nullable=True,
            comment="Where the note was written, when it has since been moved.",
        ),
        schema=CRM_SCHEMA,
    )
    op.add_column(
        "notes",
        sa.Column("origin_entity_id", sa.Uuid(as_uuid=True), nullable=True),
        schema=CRM_SCHEMA,
    )
    # Finding "everything that came off this lead" is the query this exists to
    # answer, and it is the one a converted lead's detail page runs.
    op.create_index(
        "ix_notes_organization_id_origin",
        "notes",
        ["organization_id", "origin_entity_type", "origin_entity_id"],
        schema=CRM_SCHEMA,
        postgresql_where=sa.text("origin_entity_id IS NOT NULL"),
    )

    # --- 2. Declarative stage follow-up ------------------------------------
    op.add_column(
        "pipeline_stages",
        sa.Column("follow_up_task_title", sa.String(length=255), nullable=True),
        schema=CRM_SCHEMA,
    )
    op.add_column(
        "pipeline_stages",
        sa.Column("follow_up_task_days", sa.Integer(), nullable=True),
        schema=CRM_SCHEMA,
    )
    op.create_check_constraint(
        "follow_up_task_days_non_negative",
        "pipeline_stages",
        "follow_up_task_days IS NULL OR follow_up_task_days >= 0",
        schema=CRM_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_pipeline_stages_follow_up_task_days_non_negative",
        "pipeline_stages",
        schema=CRM_SCHEMA,
        type_="check",
    )
    op.drop_column("pipeline_stages", "follow_up_task_days", schema=CRM_SCHEMA)
    op.drop_column("pipeline_stages", "follow_up_task_title", schema=CRM_SCHEMA)

    op.drop_index("ix_notes_organization_id_origin", table_name="notes", schema=CRM_SCHEMA)
    op.drop_column("notes", "origin_entity_id", schema=CRM_SCHEMA)
    op.drop_column("notes", "origin_entity_type", schema=CRM_SCHEMA)
