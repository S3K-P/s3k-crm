"""Make the rupee the currency a new opportunity starts in.

Revision ID: 20260903_0100
Revises: 20260901_0100
Create Date: 2026-09-03 01:00:00.000000

The column has carried ``USD`` as its server default since the CRM core
migration, which was never a decision so much as the value that got typed
first. S3K sells in India, so an opportunity created without an explicit
currency should be in rupees.

**Existing rows are deliberately left alone.** ``currency`` is per row, and a
row saying ``USD`` is a record of a deal someone entered in dollars. Rewriting
the code without touching the amount would silently restate ₹ for $ — the
figure would keep its digits and change its meaning by roughly two orders of
magnitude, which is the kind of edit nobody finds until a forecast is wrong.
This migration therefore changes only what an *unspecified* currency becomes.
Anything already stored keeps the code it was entered under, and the UI already
formats each row by its own code.

A deployment that genuinely wants its history relabelled — a demonstration
database whose amounts were never dollars in the first place — can do it
deliberately and separately::

    UPDATE crm.opportunities SET currency = 'INR' WHERE currency = 'USD';
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260903_0100"
down_revision: str | None = "20260901_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"
TABLE = "opportunities"
COLUMN = "currency"


def upgrade() -> None:
    op.alter_column(TABLE, COLUMN, server_default="INR", schema=CRM)


def downgrade() -> None:
    op.alter_column(TABLE, COLUMN, server_default="USD", schema=CRM)
