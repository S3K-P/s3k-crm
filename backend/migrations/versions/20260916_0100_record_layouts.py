"""Record layouts: the admin form/layout builder (Checkpoint 4).

Revision ID: 20260916_0100
Revises: 20260915_0100
Create Date: 2026-09-16 01:00:00.000000

Four tenant-scoped tables and one permission module.

**Why four tables and not one JSONB layout document.** A layout is edited a
field or a section at a time by a drag-and-drop canvas — reordered, moved
between sections, individually patched — and a document column would need to
be read, mutated in Python and rewritten whole on every one of those. This is
the same call ``dashboard_components`` (migration `20260905_0100`) and
``custom_field_definitions`` (`20260910_0100`) already made, for the identical
reason; see ``app/products/crm/layouts/models.py`` for the rest of the design.

**The two partial unique indexes on ``record_layouts`` are the schema's half
of "no invalid states".** ``uq_record_layouts_organization_id_entity_type_published``
allows at most one *published* layout per entity type — the layout a form
renders against and the one custom-field validation consults
(``app/products/crm/custom_fields/service.py:_layout_overrides``); two would
mean two different sets of conditional rules with nothing to say which one a
write was actually validated against. Partial on ``status = 'PUBLISHED'`` so a
tenant may keep as many drafts as they like.

**``record_layouts`` permission module.** ``VIEW`` goes to every system role,
the same call ``blueprints`` made and for the same reason: a rep's own
create/edit form has to fetch the published layout to render against, and it
grants sight of no record — only the tenant's own field arrangement.
Everything else stays with Admin: publishing a layout changes what every rep's
form looks like and, through a rule's ``effect_required``, what is demanded of
them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260916_0100"
down_revision: str | Sequence[str] | None = "20260915_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: Created in dependency order, dropped in reverse.
_TABLES: tuple[str, ...] = (
    "layout_field_rules",
    "layout_fields",
    "layout_sections",
    "record_layouts",
)

#: Pinned snapshot of the action vocabulary as of this revision — see
#: `20260912_0100_blueprints.py` for why this is spelled out rather than
#: imported from live code.
_ACTIONS: tuple[str, ...] = (
    "VIEW",
    "VIEW_TEAM",
    "VIEW_ALL",
    "CREATE",
    "EDIT",
    "DELETE",
    "EXPORT",
    "ADMIN",
)

_READ_ONLY: tuple[str, ...] = ("VIEW",)

_MODULE = "record_layouts"

_MAX_SECTION_COLUMNS = 2


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    connection = op.get_bind()

    sa.Enum("DRAFT", "PUBLISHED", name="layout_status", schema=CRM).create(
        connection, checkfirst=True
    )
    sa.Enum("AND", "OR", name="layout_rule_logic", schema=CRM).create(
        connection, checkfirst=True
    )
    layout_status = postgresql.ENUM(
        "DRAFT", "PUBLISHED", name="layout_status", schema=CRM, create_type=False
    )
    layout_rule_logic = postgresql.ENUM(
        "AND", "OR", name="layout_rule_logic", schema=CRM, create_type=False
    )
    crm_entity_type = postgresql.ENUM(
        "ACCOUNT",
        "CONTACT",
        "LEAD",
        "OPPORTUNITY",
        "CAMPAIGN",
        name="crm_entity_type",
        schema=CRM,
        create_type=False,
    )

    op.create_table(
        "record_layouts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entity_type", crm_entity_type, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("status", layout_status, nullable=False, server_default="DRAFT"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_record_layouts_organization_id", "record_layouts", ["organization_id"], schema=CRM
    )
    op.create_index(
        "ix_record_layouts_deleted_at", "record_layouts", ["deleted_at"], schema=CRM
    )
    op.create_index(
        "ix_record_layouts_organization_id_entity_type",
        "record_layouts",
        ["organization_id", "entity_type"],
        schema=CRM,
    )
    op.create_index(
        "uq_record_layouts_organization_id_entity_type_name_live",
        "record_layouts",
        ["organization_id", "entity_type", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_record_layouts_organization_id_entity_type_published",
        "record_layouts",
        ["organization_id", "entity_type"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("status = 'PUBLISHED' AND deleted_at IS NULL"),
    )

    op.create_table(
        "layout_sections",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "layout_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.record_layouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("columns", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            f"columns BETWEEN 1 AND {_MAX_SECTION_COLUMNS}", name="ck_layout_sections_columns"
        ),
        sa.CheckConstraint("position >= 0", name="ck_layout_sections_position"),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_layout_sections_organization_id", "layout_sections", ["organization_id"], schema=CRM
    )
    op.create_index(
        "ix_layout_sections_deleted_at", "layout_sections", ["deleted_at"], schema=CRM
    )
    op.create_index(
        "ix_layout_sections_organization_id_layout_id",
        "layout_sections",
        ["organization_id", "layout_id"],
        schema=CRM,
    )

    op.create_table(
        "layout_fields",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "layout_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.record_layouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.layout_sections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_key", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_span", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_required_override", sa.Boolean(), nullable=True),
        sa.Column("is_read_only", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("label_override", sa.String(length=160), nullable=True),
        sa.Column("help_text_override", sa.String(length=500), nullable=True),
        sa.Column("placeholder_override", sa.String(length=160), nullable=True),
        sa.CheckConstraint(
            f"column_span BETWEEN 1 AND {_MAX_SECTION_COLUMNS}",
            name="ck_layout_fields_column_span",
        ),
        sa.CheckConstraint("position >= 0", name="ck_layout_fields_position"),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_layout_fields_organization_id", "layout_fields", ["organization_id"], schema=CRM
    )
    op.create_index("ix_layout_fields_deleted_at", "layout_fields", ["deleted_at"], schema=CRM)
    op.create_index(
        "ix_layout_fields_organization_id_layout_id",
        "layout_fields",
        ["organization_id", "layout_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_layout_fields_organization_id_section_id",
        "layout_fields",
        ["organization_id", "section_id"],
        schema=CRM,
    )
    op.create_index(
        "uq_layout_fields_layout_id_field_key_live",
        "layout_fields",
        ["layout_id", "field_key"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "layout_field_rules",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "layout_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.record_layouts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=True),
        sa.Column("target_field_key", sa.String(length=80), nullable=False),
        sa.Column("logic", layout_rule_logic, nullable=False, server_default="AND"),
        sa.Column(
            "conditions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("effect_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("effect_required", sa.Boolean(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("position >= 0", name="ck_layout_field_rules_position"),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_layout_field_rules_organization_id",
        "layout_field_rules",
        ["organization_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_layout_field_rules_deleted_at", "layout_field_rules", ["deleted_at"], schema=CRM
    )
    op.create_index(
        "ix_layout_field_rules_organization_id_layout_id",
        "layout_field_rules",
        ["organization_id", "layout_id"],
        schema=CRM,
    )

    for table in _TABLES:
        enable_rls(connection, table, schema=CRM)

    for action in _ACTIONS:
        connection.execute(
            sa.text(
                "INSERT INTO platform.permissions (module, action, description) "
                "VALUES (:module, CAST(:action AS platform.permission_action), :description) "
                "ON CONFLICT (module, action) DO NOTHING"
            ),
            {
                "module": _MODULE,
                "action": action,
                "description": f"{action} record layout (form builder) configuration",
            },
        )

    _grant("Admin", _ACTIONS, connection)
    _grant("Manager", _READ_ONLY, connection)
    _grant("User", _READ_ONLY, connection)


def _grant(role: str, actions: tuple[str, ...], connection: sa.Connection) -> None:
    for action in actions:
        connection.execute(
            sa.text(
                "INSERT INTO platform.role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
                "WHERE r.organization_id IS NULL AND r.name = :role "
                "  AND p.module = :module "
                "  AND p.action = CAST(:action AS platform.permission_action) "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"role": role, "module": _MODULE, "action": action},
        )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            "DELETE FROM platform.role_permissions WHERE permission_id IN "
            "(SELECT id FROM platform.permissions WHERE module = :module)"
        ),
        {"module": _MODULE},
    )
    connection.execute(
        sa.text("DELETE FROM platform.permissions WHERE module = :module"),
        {"module": _MODULE},
    )

    for table in reversed(_TABLES):
        disable_rls(connection, table, schema=CRM)

    op.drop_table("layout_field_rules", schema=CRM)
    op.drop_table("layout_fields", schema=CRM)
    op.drop_table("layout_sections", schema=CRM)
    op.drop_table("record_layouts", schema=CRM)

    sa.Enum(name="layout_rule_logic", schema=CRM).drop(connection, checkfirst=True)
    sa.Enum(name="layout_status", schema=CRM).drop(connection, checkfirst=True)
