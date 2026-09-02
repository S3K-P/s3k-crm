"""Indexed phone matching on contacts, and a mandatory opportunity close date.

Revision ID: 20260902_0100
Revises: 20260826_0200
Create Date: 2026-09-02 01:00:00.000000

Two Stage 0 foundations from ``docs/S3K_CRM_Zoho_Analysis.md``.

**1. ``crm.contacts.phone_digits``** — a generated column holding the last ten
digits of ``phone``, plus an index on it.

Lead conversion matched an existing contact by phone like this::

    select ... from crm.contacts where phone is not null
    order by created_at limit 50          -- then filter in Python

Two defects, not one. The obvious one is that it cannot use an index. The
serious one is ``limit 50``: those are the *fifty oldest* contacts in the
organization, so an organization with more than fifty contacts would not find a
match on the fifty-first — conversion then created a duplicate contact and
reported success. The bug got worse the longer a tenant used the product.

The column normalizes what humans type ("+91 98765 43210", "(555) 010-9999")
down to a comparable form, so the lookup becomes an indexed equality.
``nullif(..., '')`` maps "no phone" to NULL rather than to the empty string,
because otherwise every contact without a number would compare equal to every
other one.

The expression is pinned here as a literal and declared again on the model
(``app.products.crm.common.PHONE_DIGITS``). That duplication is deliberate and
is the rule ``tests/unit/test_migration_hygiene.py`` exists to protect: this
file is a snapshot of what was built, the model is the live definition, and
they may only diverge through a migration that changes both.

**2. ``crm.opportunities.expected_close_date`` becomes NOT NULL.**

A deal with no close date cannot be placed in a forecast period, so it silently
drops out of every pipeline projection while still looking like live pipeline
on the board. Zoho makes Closing Date mandatory on Deals for exactly this
reason, and the analysis adopts it.

Existing rows are backfilled to thirty days after creation rather than deleted
or left null: a placeholder date that is visibly approximate is more useful
than a hole, and the rows are still identifiable afterwards by their date being
exactly ``created_at + 30 days``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260902_0100"
down_revision: str | None = "20260826_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM_SCHEMA = "crm"

#: Must stay character-for-character identical to
#: ``app.products.crm.common.PHONE_DIGITS``. Pinned, not imported: a migration
#: that reads living code rewrites its own history when that code changes.
PHONE_DIGITS = "nullif(right(regexp_replace(coalesce(phone, ''), '[^0-9]', '', 'g'), 10), '')"

PHONE_INDEX = "ix_contacts_organization_id_phone_digits"

#: Backfill for rows that predate the NOT NULL. Thirty days after creation:
#: long enough to be plausible, short enough that it surfaces in "closing soon"
#: rather than hiding at the far end of the pipeline. Written as a literal
#: statement rather than assembled from parts — a migration is a snapshot, and
#: a fully-spelled-out statement is what it should be a snapshot of.
BACKFILL_SQL = (
    "UPDATE crm.opportunities "
    "SET expected_close_date = (created_at + interval '30 days')::date "
    "WHERE expected_close_date IS NULL"
)


def upgrade() -> None:
    # --- 1. Indexed phone matching on contacts -----------------------------
    op.add_column(
        "contacts",
        sa.Column(
            "phone_digits",
            sa.String(length=10),
            sa.Computed(PHONE_DIGITS, persisted=True),
            nullable=True,
            comment=(
                "Last ten digits of phone, generated. NULL when there is no "
                "phone, so missing numbers never compare equal to each other."
            ),
        ),
        schema=CRM_SCHEMA,
    )
    op.create_index(
        PHONE_INDEX,
        "contacts",
        ["organization_id", "phone_digits"],
        schema=CRM_SCHEMA,
    )

    # --- 2. A deal must have a close date ----------------------------------
    op.execute(sa.text(BACKFILL_SQL))
    op.alter_column(
        "opportunities",
        "expected_close_date",
        existing_type=sa.Date(),
        nullable=False,
        schema=CRM_SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        "opportunities",
        "expected_close_date",
        existing_type=sa.Date(),
        nullable=True,
        schema=CRM_SCHEMA,
    )
    # The backfilled dates are left in place. Nulling them again would mean
    # guessing which rows were backfilled and which were always set, and
    # getting that wrong destroys a real forecast date.

    op.drop_index(PHONE_INDEX, table_name="contacts", schema=CRM_SCHEMA)
    op.drop_column("contacts", "phone_digits", schema=CRM_SCHEMA)
