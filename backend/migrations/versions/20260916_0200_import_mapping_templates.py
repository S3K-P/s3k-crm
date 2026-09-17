"""Saved CSV import mapping templates (Checkpoint 4).

Revision ID: 20260916_0200
Revises: 20260916_0100
Create Date: 2026-09-16 02:00:00.000000

One tenant-scoped table, no new permission module. A template is authorized
against the *imported entity's own* module — the same ``leads``/``accounts``/
``contacts`` permission the preview/commit endpoints already require, decided
from the ``{slug}`` path parameter at request time
(``app/products/crm/imports/router.py``) — for the identical reason the CSV
import feature itself has no ``imports.CREATE`` of its own: importing (and now
saving how a file maps) is creating records, and the catalogue already has an
action for that.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260916_0200"
down_revision: str | Sequence[str] | None = "20260916_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "import_mapping_templates",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entity_slug", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "mapping", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "duplicate_policy", sa.String(length=16), nullable=False, server_default="SKIP"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=CRM,
    )
    op.create_index(
        "ix_import_mapping_templates_organization_id",
        "import_mapping_templates",
        ["organization_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_import_mapping_templates_deleted_at",
        "import_mapping_templates",
        ["deleted_at"],
        schema=CRM,
    )
    op.create_index(
        "ix_import_mapping_templates_organization_id_entity_slug",
        "import_mapping_templates",
        ["organization_id", "entity_slug"],
        schema=CRM,
    )
    op.create_index(
        "uq_import_mapping_templates_org_entity_name_live",
        "import_mapping_templates",
        ["organization_id", "entity_slug", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    enable_rls(connection, "import_mapping_templates", schema=CRM)


def downgrade() -> None:
    connection = op.get_bind()
    disable_rls(connection, "import_mapping_templates", schema=CRM)
    op.drop_table("import_mapping_templates", schema=CRM)
