"""Per-stage entry requirements.

Revision ID: 20260903_0300
Revises: 20260903_0200
Create Date: 2026-09-03 03:00:00.000000

``crm.pipeline_stages.required_fields``: the fields a deal must carry before it
may enter that stage. The analysis's "Blueprint slot" (§5.6) — gate the change
*before* it happens, rather than reacting to a stage move that already put a
valueless deal in Proposal — expressed as a column rather than a workflow
engine.

**Empty for every existing and new stage.** The first implementation derived
requirements from a stage's probability, which is a defensible policy and the
wrong default: shipping it would have made the product start refusing stage
moves that organizations had been making for months. Which fields a stage gates
on belongs to whoever runs the sales process, exactly like the follow-up task
column beside it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0300"
down_revision: str | None = "20260903_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM_SCHEMA = "crm"


def upgrade() -> None:
    op.add_column(
        "pipeline_stages",
        sa.Column(
            "required_fields",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default="{}",
            comment=(
                "Fields a deal must carry to enter this stage. Empty means no "
                "gating, which is the default for every stage."
            ),
        ),
        schema=CRM_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("pipeline_stages", "required_fields", schema=CRM_SCHEMA)
