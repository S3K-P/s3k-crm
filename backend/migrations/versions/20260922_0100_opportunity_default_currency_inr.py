"""New opportunities default to INR.

Revision ID: 20260922_0100
Revises: 20260921_0100
Create Date: 2026-09-22 01:00:00.000000

Only the column default changes, so a row inserted without a currency is
stamped ``INR`` to match the CRM's display currency. Existing rows are left
exactly as they are: no ``currency`` value is rewritten and no ``deal_value``
is converted. A metadata-only ``ALTER``; no table rewrite, no data touched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260922_0100"
down_revision: str | Sequence[str] | None = "20260921_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    op.alter_column("opportunities", "currency", server_default="INR", schema=CRM)


def downgrade() -> None:
    op.alter_column("opportunities", "currency", server_default="USD", schema=CRM)
