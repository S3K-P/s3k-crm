"""Custom (ad-hoc) reports (Checkpoint 5).

Revision ID: 20260917_0100
Revises: 20260916_0200
Create Date: 2026-09-17 01:00:00.000000

Widens ``crm.saved_reports`` to hold a user-authored report definition
alongside the existing catalogue-key path: ``base_report_key`` becomes
nullable, a new nullable ``custom_definition`` JSONB column is added, and a
CHECK constraint requires exactly one of the two to be set on every row —
enforced at the database, not only by the two Pydantic validators
(``schemas.SavedReportCreate._exactly_one_definition``,
``library.SavedReportService.update_saved``) that already refuse to write a
row that violates it. No new permission module: a custom report over an
entity is gated by that entity's own module, exactly as a catalogue report
already is (``reports/policies.py``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260917_0100"
down_revision: str | Sequence[str] | None = "20260916_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"
TABLE = "saved_reports"


def upgrade() -> None:
    op.alter_column(
        TABLE,
        "base_report_key",
        existing_type=sa.String(length=64),
        nullable=True,
        schema=CRM,
    )
    op.add_column(
        TABLE,
        sa.Column("custom_definition", postgresql.JSONB(), nullable=True),
        schema=CRM,
    )
    op.create_check_constraint(
        "ck_saved_reports_exactly_one_definition",
        TABLE,
        "(base_report_key IS NOT NULL) != (custom_definition IS NOT NULL)",
        schema=CRM,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_saved_reports_exactly_one_definition",
        TABLE,
        schema=CRM,
        type_="check",
    )
    op.drop_column(TABLE, "custom_definition", schema=CRM)
    # A custom report saved under this revision has no `base_report_key` at
    # all; downgrading past this point would violate the column's restored
    # NOT NULL for exactly the rows this revision introduced. Deleting them
    # first is the honest choice — a silent NULL->'' rewrite would leave a
    # saved report pointing at a catalogue entry nobody chose.
    # `CRM`/`TABLE` are this file's own module-level constants, never request
    # input — nothing here is a SQL-injection vector despite the pattern match.
    op.execute(sa.text(f"DELETE FROM {CRM}.{TABLE} WHERE base_report_key IS NULL"))  # noqa: S608
    op.alter_column(
        TABLE,
        "base_report_key",
        existing_type=sa.String(length=64),
        nullable=False,
        schema=CRM,
    )
