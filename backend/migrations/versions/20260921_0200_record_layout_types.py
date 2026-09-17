"""Record layouts: Create / Quick Create / Detail View (Zoho field/layout parity).

Revision ID: 20260921_0200
Revises: 20260921_0100
Create Date: 2026-09-21 02:00:00.000000

Adds ``layout_type`` to ``record_layouts`` and folds it into both partial
unique indexes, so "at most one published layout" and "unique name" are now
scoped per entity type *and screen* rather than per entity type alone — see
``app/products/crm/layouts/models.py::LayoutType`` for the full reasoning.

Every existing row is backfilled as ``DETAIL``: that was the one layout type
driving every screen before this migration, so an organization that had
already published a layout keeps exactly the same behavior on every screen
until it deliberately publishes a narrower ``CREATE`` or ``QUICK_CREATE`` one
(the server-side fallback in
``RecordLayoutRepository.published_for_with_fallback`` is what makes that
true at read time; this migration is what makes it true in the data).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0200"
down_revision: str | Sequence[str] | None = "20260921_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    connection = op.get_bind()

    sa.Enum("CREATE", "QUICK_CREATE", "DETAIL", name="layout_type", schema=CRM).create(
        connection, checkfirst=True
    )
    layout_type = sa.Enum(
        "CREATE", "QUICK_CREATE", "DETAIL", name="layout_type", schema=CRM, create_type=False
    )
    op.add_column(
        "record_layouts",
        sa.Column("layout_type", layout_type, nullable=False, server_default="DETAIL"),
        schema=CRM,
    )

    op.drop_index(
        "uq_record_layouts_organization_id_entity_type_name_live",
        table_name="record_layouts",
        schema=CRM,
    )
    op.drop_index(
        "uq_record_layouts_organization_id_entity_type_published",
        table_name="record_layouts",
        schema=CRM,
    )
    op.create_index(
        "uq_record_layouts_organization_id_entity_type_name_live",
        "record_layouts",
        ["organization_id", "entity_type", "layout_type", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_record_layouts_organization_id_entity_type_published",
        "record_layouts",
        ["organization_id", "entity_type", "layout_type"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("status = 'PUBLISHED' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    connection = op.get_bind()

    op.drop_index(
        "uq_record_layouts_organization_id_entity_type_published",
        table_name="record_layouts",
        schema=CRM,
    )
    op.drop_index(
        "uq_record_layouts_organization_id_entity_type_name_live",
        table_name="record_layouts",
        schema=CRM,
    )
    op.create_index(
        "uq_record_layouts_organization_id_entity_type_published",
        "record_layouts",
        ["organization_id", "entity_type"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("status = 'PUBLISHED' AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_record_layouts_organization_id_entity_type_name_live",
        "record_layouts",
        ["organization_id", "entity_type", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.drop_column("record_layouts", "layout_type", schema=CRM)
    sa.Enum(name="layout_type", schema=CRM).drop(connection, checkfirst=True)
