"""Lead conversion: product interest + UNQUALIFIED + opportunity FK.

Revision ID: 20260818_1900
Revises: 8224845a67ac
Create Date: 2026-08-18 19:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_1900"
down_revision: str | None = "8224845a67ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Native PostgreSQL enum — ALTER TYPE ... ADD VALUE cannot run inside a
    # transaction block on some versions; Alembic's default transaction is fine
    # on PG 12+ for ADD VALUE IF NOT EXISTS.
    op.execute(
        sa.text(
            "ALTER TYPE crm.lead_status ADD VALUE IF NOT EXISTS 'UNQUALIFIED' "
            "BEFORE 'CONVERTED'"
        )
    )

    op.add_column(
        "leads",
        sa.Column("product_interest", sa.String(length=255), nullable=True),
        schema="crm",
    )

    # Conversion history already stores the opportunity id; pin it with a real FK
    # so the Lead → Deal link cannot point at a deleted row silently forever.
    op.create_foreign_key(
        op.f("fk_leads_converted_opportunity_id_opportunities"),
        "leads",
        "opportunities",
        ["converted_opportunity_id"],
        ["id"],
        source_schema="crm",
        referent_schema="crm",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_leads_converted_opportunity_id_opportunities"),
        "leads",
        schema="crm",
        type_="foreignkey",
    )
    op.drop_column("leads", "product_interest", schema="crm")
    # PostgreSQL cannot remove an enum value safely; leave UNQUALIFIED in place.
