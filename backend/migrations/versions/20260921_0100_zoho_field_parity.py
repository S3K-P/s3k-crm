"""Zoho field-parity: high-value fields on Leads, Accounts, Contacts, Deals.

Revision ID: 20260921_0100
Revises: 20260920_0100
Create Date: 2026-09-21 01:00:00.000000

Adds the highest-value Zoho standard fields that S3K's core four modules were
missing (docs/S3K_CRM_Zoho_Analysis.md §1.2). Every column is nullable (or a
defaulted boolean), so this is purely additive — no backfill, no risk to
existing rows.

* ``crm.leads``: ``title``, ``secondary_email``, ``rating``, ``email_opt_out``.
* ``crm.accounts``: ``account_type``, ``fax``, ``email``, ``rating``,
  ``parent_account_id`` (company hierarchy), and a second, ``shipping_*``
  address block alongside the existing (billing) one.
* ``crm.contacts``: ``salutation``, ``secondary_email``, ``email_opt_out``.
* ``crm.opportunities``: ``deal_type``, ``next_step``.

A single ``crm_rating`` enum (HOT/WARM/COLD) is shared by Leads and Accounts,
mirroring Zoho's "Rating" field on both.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260921_0100"
down_revision: str | Sequence[str] | None = "20260920_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    connection = op.get_bind()

    sa.Enum("HOT", "WARM", "COLD", name="crm_rating", schema=CRM).create(
        connection, checkfirst=True
    )
    crm_rating = postgresql.ENUM(
        "HOT", "WARM", "COLD", name="crm_rating", schema=CRM, create_type=False
    )

    # --- Leads ---------------------------------------------------------
    op.add_column("leads", sa.Column("title", sa.String(length=100), nullable=True), schema=CRM)
    op.add_column(
        "leads",
        sa.Column("secondary_email", sa.String(length=320), nullable=True),
        schema=CRM,
    )
    op.add_column("leads", sa.Column("rating", crm_rating, nullable=True), schema=CRM)
    op.add_column(
        "leads",
        sa.Column(
            "email_opt_out", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema=CRM,
    )

    # --- Accounts --------------------------------------------------------
    op.add_column(
        "accounts", sa.Column("account_type", sa.String(length=64), nullable=True), schema=CRM
    )
    op.add_column("accounts", sa.Column("fax", sa.String(length=32), nullable=True), schema=CRM)
    op.add_column(
        "accounts", sa.Column("email", sa.String(length=320), nullable=True), schema=CRM
    )
    op.add_column("accounts", sa.Column("rating", crm_rating, nullable=True), schema=CRM)
    op.add_column(
        "accounts",
        sa.Column("parent_account_id", sa.Uuid(as_uuid=True), nullable=True),
        schema=CRM,
    )
    op.create_foreign_key(
        "fk_accounts_parent_account_id_accounts",
        "accounts",
        "accounts",
        ["parent_account_id"],
        ["id"],
        source_schema=CRM,
        referent_schema=CRM,
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_accounts_organization_id_parent_account_id",
        "accounts",
        ["organization_id", "parent_account_id"],
        schema=CRM,
    )
    op.add_column(
        "accounts",
        sa.Column("shipping_address_line1", sa.String(length=255), nullable=True),
        schema=CRM,
    )
    op.add_column(
        "accounts",
        sa.Column("shipping_city", sa.String(length=120), nullable=True),
        schema=CRM,
    )
    op.add_column(
        "accounts",
        sa.Column("shipping_state", sa.String(length=120), nullable=True),
        schema=CRM,
    )
    op.add_column(
        "accounts",
        sa.Column("shipping_postal_code", sa.String(length=32), nullable=True),
        schema=CRM,
    )
    op.add_column(
        "accounts",
        sa.Column("shipping_country", sa.String(length=120), nullable=True),
        schema=CRM,
    )

    # --- Contacts ----------------------------------------------------------
    op.add_column(
        "contacts", sa.Column("salutation", sa.String(length=20), nullable=True), schema=CRM
    )
    op.add_column(
        "contacts",
        sa.Column("secondary_email", sa.String(length=320), nullable=True),
        schema=CRM,
    )
    op.add_column(
        "contacts",
        sa.Column(
            "email_opt_out", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        schema=CRM,
    )

    # --- Opportunities -------------------------------------------------
    op.add_column(
        "opportunities",
        sa.Column("deal_type", sa.String(length=64), nullable=True),
        schema=CRM,
    )
    op.add_column(
        "opportunities",
        sa.Column("next_step", sa.String(length=255), nullable=True),
        schema=CRM,
    )


def downgrade() -> None:
    op.drop_column("opportunities", "next_step", schema=CRM)
    op.drop_column("opportunities", "deal_type", schema=CRM)

    op.drop_column("contacts", "email_opt_out", schema=CRM)
    op.drop_column("contacts", "secondary_email", schema=CRM)
    op.drop_column("contacts", "salutation", schema=CRM)

    op.drop_column("accounts", "shipping_country", schema=CRM)
    op.drop_column("accounts", "shipping_postal_code", schema=CRM)
    op.drop_column("accounts", "shipping_state", schema=CRM)
    op.drop_column("accounts", "shipping_city", schema=CRM)
    op.drop_column("accounts", "shipping_address_line1", schema=CRM)
    op.drop_index(
        "ix_accounts_organization_id_parent_account_id", table_name="accounts", schema=CRM
    )
    op.drop_constraint(
        "fk_accounts_parent_account_id_accounts",
        "accounts",
        schema=CRM,
        type_="foreignkey",
    )
    op.drop_column("accounts", "parent_account_id", schema=CRM)
    op.drop_column("accounts", "rating", schema=CRM)
    op.drop_column("accounts", "email", schema=CRM)
    op.drop_column("accounts", "fax", schema=CRM)
    op.drop_column("accounts", "account_type", schema=CRM)

    op.drop_column("leads", "email_opt_out", schema=CRM)
    op.drop_column("leads", "rating", schema=CRM)
    op.drop_column("leads", "secondary_email", schema=CRM)
    op.drop_column("leads", "title", schema=CRM)

    connection = op.get_bind()
    sa.Enum(name="crm_rating", schema=CRM).drop(connection, checkfirst=True)
