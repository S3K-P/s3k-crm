"""Constrain and expose contacts.reporting_manager_id.

Revision ID: 20260924_0100
Revises: 20260923_0100
Create Date: 2026-09-24 01:00:00.000000

``reporting_manager_id`` has existed on ``crm.contacts`` since the very first
migration (``8224845a67ac``) as a bare ``uuid`` column: no foreign key, no
index, and never read or written by the API. It was reserved and never
finished.

This revision finishes it, on the same pattern ``merged_into_id`` already
uses on this table (``20260911_0100``): self-referential, ``ON DELETE SET
NULL`` so removing a manager's own contact record clears the pointer rather
than blocking the delete or cascading into an unrelated row, and a partial
index for the "who reports to this person" query the contact detail page
will run. No data backfill — existing rows are all ``NULL`` already, since
nothing has ever written to this column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0100"
down_revision: str | Sequence[str] | None = "20260923_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    op.create_foreign_key(
        "fk_contacts_reporting_manager_id_contacts",
        "contacts",
        "contacts",
        ["reporting_manager_id"],
        ["id"],
        source_schema=CRM,
        referent_schema=CRM,
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_contacts_reporting_manager_id",
        "contacts",
        ["reporting_manager_id"],
        schema=CRM,
        postgresql_where=sa.text("reporting_manager_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_contacts_reporting_manager_id", table_name="contacts", schema=CRM)
    op.drop_constraint(
        "fk_contacts_reporting_manager_id_contacts", "contacts", schema=CRM
    )
