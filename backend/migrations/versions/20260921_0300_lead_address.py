"""Leads: structured address fields (Zoho field/layout parity).

Revision ID: 20260921_0300
Revises: 20260921_0200
Create Date: 2026-09-21 03:00:00.000000

Accounts and contacts already carry a structured address (migration
`20260807...` — see `app/products/crm/accounts/models.py` and
`contacts/models.py`); leads never did. The Zoho Leads reference screenshot
this checkpoint works from has an "Address Information" section, and there
was nowhere on a lead to place it. Same five nullable columns, same names, so
a layout section called "Address Information" places the same field keys on
every one of the three entities that have one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0300"
down_revision: str | Sequence[str] | None = "20260921_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    op.add_column(
        "leads", sa.Column("address_line1", sa.String(length=255), nullable=True), schema=CRM
    )
    op.add_column("leads", sa.Column("city", sa.String(length=120), nullable=True), schema=CRM)
    op.add_column("leads", sa.Column("state", sa.String(length=120), nullable=True), schema=CRM)
    op.add_column(
        "leads", sa.Column("postal_code", sa.String(length=32), nullable=True), schema=CRM
    )
    op.add_column("leads", sa.Column("country", sa.String(length=120), nullable=True), schema=CRM)


def downgrade() -> None:
    op.drop_column("leads", "country", schema=CRM)
    op.drop_column("leads", "postal_code", schema=CRM)
    op.drop_column("leads", "state", schema=CRM)
    op.drop_column("leads", "city", schema=CRM)
    op.drop_column("leads", "address_line1", schema=CRM)
