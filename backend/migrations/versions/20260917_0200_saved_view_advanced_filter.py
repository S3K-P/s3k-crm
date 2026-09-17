"""Advanced (multi-condition AND/OR) filters on saved views (Checkpoint 5).

Revision ID: 20260917_0200
Revises: 20260917_0100
Create Date: 2026-09-17 02:00:00.000000

Adds one nullable JSONB column to ``crm.saved_views``. Purely additive: the
existing ``filters`` column, its validator and every view saved before this
migration are untouched — see ``views/models.py`` for why the two columns
are kept separate rather than one replacing the other.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_0200"
down_revision: str | Sequence[str] | None = "20260917_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"
TABLE = "saved_views"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("advanced_filter", postgresql.JSONB(), nullable=True),
        schema=CRM,
    )


def downgrade() -> None:
    op.drop_column(TABLE, "advanced_filter", schema=CRM)
