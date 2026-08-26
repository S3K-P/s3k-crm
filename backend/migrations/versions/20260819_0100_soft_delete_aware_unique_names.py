"""Make name uniqueness soft-delete aware on CRM reference tables.

Revision ID: 20260819_0100
Revises: 20260818_1900
Create Date: 2026-08-19 01:00:00.000000

``lead_sources``, ``pipelines`` and ``pipeline_stages`` are all soft-deleted:
archiving one sets ``deleted_at`` and leaves the row in place. Their uniqueness
was an unconditional ``UNIQUE (organization_id, name)``, which therefore
counted archived rows — so an archived name could never be used again.

The service layer already had the correct rule (``_name_exists`` filters on
``deleted_at IS NULL``), which made the mismatch worse rather than better: the
pre-check passed, the INSERT then violated the constraint, and the caller got
an unhandled IntegrityError as a **500** where it should have seen either a
created row or a 409.

Reproduced before this change: archive the "Website" lead source, create
"Website" again → 500.

Each constraint becomes a partial unique index with the same predicate the
services use, so the database and the business rule finally agree.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0100"
down_revision: str | None = "20260818_1900"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (table, old constraint name, new index name, columns)
_TARGETS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "lead_sources",
        "uq_lead_sources_organization_id_name",
        "uq_lead_sources_organization_id_name_live",
        ("organization_id", "name"),
    ),
    (
        "pipelines",
        "uq_pipelines_organization_id_name",
        "uq_pipelines_organization_id_name_live",
        ("organization_id", "name"),
    ),
    (
        "pipeline_stages",
        "uq_pipeline_stages_pipeline_id_name",
        "uq_pipeline_stages_pipeline_id_name_live",
        ("pipeline_id", "name"),
    ),
)


def upgrade() -> None:
    for table, constraint, index, columns in _TARGETS:
        op.drop_constraint(constraint, table, schema="crm", type_="unique")
        op.create_index(
            index,
            table,
            list(columns),
            unique=True,
            schema="crm",
            postgresql_where=sa.text("deleted_at IS NULL"),
        )


def downgrade() -> None:
    # Reinstating the unconditional constraint fails if archived duplicates
    # have accumulated in the meantime — which is exactly the state this
    # migration made reachable. Nothing is deleted to force it through: a
    # downgrade that silently destroyed rows would be worse than one that
    # stops and asks.
    for table, constraint, index, columns in _TARGETS:
        op.drop_index(index, table_name=table, schema="crm")
        op.create_unique_constraint(constraint, table, list(columns), schema="crm")
