"""Indexes for the columns a merge repoints (Phase H).

Revision ID: 20260913_0100
Revises: 20260912_0100
Create Date: 2026-09-13 01:00:00.000000

Four indexes, each justified by a query that exists rather than by a general
rule about foreign keys.

``MergeService._repoint`` moves every reference from the losing records to the
survivor with one bulk UPDATE per referencing column, filtered as
``organization_id = :org AND <column> IN (:losers)``. Four of those columns had
nothing an index could match that shape against, so each UPDATE was a scan of
the whole tenant's table — during an interactive operation, at the moment a
person is watching a spinner:

* ``crm.accounts.primary_contact_id``
* ``crm.opportunities.primary_contact_id``
* ``crm.leads.converted_account_id``
* ``crm.leads.converted_contact_id``

**Why not the other unindexed foreign keys.** A scan of ``pg_constraint``
reports twenty-three foreign keys with no index leading on their column, and
adding an index to each would be the obvious move and the wrong one — every one
costs write throughput on every insert and update of the table, forever, and
most of them are never queried by that column alone. The application filters by
``organization_id`` first in every single query it makes, and the composite
``(organization_id, <column>)`` indexes that already exist serve those. What
this revision adds is the four cases where such a composite was genuinely
missing *and* a real query needs it.

**Composite, leading on the tenant, matching the query.** Not an index on the
column alone: that would serve PostgreSQL's own referential-integrity check on
a parent delete — which this product never performs, because deletion is soft
everywhere — while missing the tenant predicate the application's query always
carries.

**Partial on ``IS NOT NULL``.** All four columns are null on the overwhelming
majority of rows: most accounts name no primary contact, and most leads were
never converted. Excluding the nulls keeps each index proportional to the rows
that can actually match rather than to the table, which on the ``leads``
converted-* pair is the difference between an index over a handful of rows and
one over every lead the tenant has ever had.

Index creation takes a brief ``SHARE`` lock, which blocks writes to the table
for its duration. On a table of any size the deployment procedure is
``CREATE INDEX CONCURRENTLY``, which Alembic cannot run inside its transactional
DDL — so it is called out here rather than silently assumed: for a large
existing deployment, create these four by hand outside the migration and stamp
the revision.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260913_0100"
down_revision: str | Sequence[str] | None = "20260912_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: ``(table, column)`` — each one a column ``MergeService._repoint`` filters on.
_REFERENCES: tuple[tuple[str, str], ...] = (
    ("accounts", "primary_contact_id"),
    ("opportunities", "primary_contact_id"),
    ("leads", "converted_account_id"),
    ("leads", "converted_contact_id"),
)


def upgrade() -> None:
    for table, column in _REFERENCES:
        op.create_index(
            f"ix_{table}_organization_id_{column}",
            table,
            ["organization_id", column],
            schema=CRM,
            postgresql_where=sa.text(f"{column} IS NOT NULL"),
        )


def downgrade() -> None:
    for table, column in reversed(_REFERENCES):
        op.drop_index(
            f"ix_{table}_organization_id_{column}", table_name=table, schema=CRM
        )
