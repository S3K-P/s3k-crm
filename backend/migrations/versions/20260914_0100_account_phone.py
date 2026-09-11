"""Add a phone number to accounts (Checkpoint 2, Account 360).

Revision ID: 20260914_0100
Revises: 20260913_0100
Create Date: 2026-09-14 01:00:00.000000

The audit's Account 360 spec lists a company phone number alongside industry,
website and address. Contacts already have one (``crm.contacts.phone``);
accounts never got the column, so the field had nowhere to be stored short of
tenant-defined custom fields — which would misclassify a near-universal
company attribute as a per-tenant one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0100"
down_revision: str | Sequence[str] | None = "20260913_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("phone", sa.String(length=32), nullable=True),
        schema=CRM,
    )


def downgrade() -> None:
    op.drop_column("accounts", "phone", schema=CRM)
