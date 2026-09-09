"""Tenant-defined fields, picklists, and the column that holds their values (Phase E).

Revision ID: 20260910_0100
Revises: 20260909_0100
Create Date: 2026-09-10 01:00:00.000000

Three tenant-scoped tables in ``crm``, one new permission module, and a
``custom_fields`` JSONB column on each of the five record types that support
them.

**Why a column on each record rather than a values table.** The obvious shape
is entity-attribute-value: one row per record per field. It was rejected for
three reasons, in order of weight. First, every list screen in the product
would need a second query per page — or a join whose row multiplication has to
be collapsed again — to show a single custom column; the N+1 would be built in
rather than introduced by accident. Second, a stored value would become a
foreign key to an option, which makes retiring an option either blocked or
destructive, where the whole requirement is that a retired option keeps
rendering on the records that already hold it. Third, this is the only DDL the
feature ever needs: an administrator's fortieth field changes no schema.

The cost is that a JSONB value is text at the storage layer, so a comparison
has to be told what it means. That lives in ``custom_fields/filters.py``, which
casts per the definition's declared type — never per anything in the request —
and guards every cast so one malformed document cannot fail a whole list query.

**The GIN indexes** are ``jsonb_path_ops``, not the default. They are half the
size and faster for the containment queries this column actually receives
(``custom_fields @> '{"region": ["EMEA"]}'``); what they give up is key-exists
(``?``) support, which no query path here uses — filtering on presence goes
through ``->>`` ``IS NULL``, which is not an index-only question in any case.

**Backfill is not needed and not attempted.** The column is
``NOT NULL DEFAULT '{}'``, and PostgreSQL 11+ stores a non-volatile default in
the catalogue rather than rewriting the table, so adding it to five populated
tables is a metadata change. Existing rows read as ``{}`` without a single page
being touched — which is what makes this migration safe to run against a
production-sized database.

**The ``custom_fields`` permission module** is granted like every module before
it: to the ``organization_id IS NULL`` role templates, which every
organization's memberships reference, so one insert reaches every existing
tenant without a per-organization loop. What is unusual is that ``VIEW`` goes
to *every* system role including ``User``, and it is worth saying why that is
not a widening. Reading the definitions is what makes a record form drawable at
all — a rep who cannot see that "Leads have a Region field" gets a form missing
half its inputs. It grants sight of the tenant's own configuration and nothing
else: a record's custom *values* live in the record, behind that record's own
module permission and record-level visibility.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260910_0100"
down_revision: str | Sequence[str] | None = "20260909_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: Created in dependency order, dropped in reverse.
_TABLES: tuple[str, ...] = ("picklists", "picklist_options", "custom_field_definitions")

#: Record types gaining the value column. The same five ``crm_entity_type``
#: members activities, tasks and notes already attach to.
_VALUE_TABLES: tuple[str, ...] = (
    "accounts",
    "contacts",
    "leads",
    "opportunities",
    "campaigns",
)

#: Pinned snapshot of the action vocabulary as of this revision. Not imported
#: from ``app.platform.authorization.catalog``: a migration is a snapshot of
#: history, and reading live code means a later edit silently rewrites what an
#: old revision does — the failure that broke revision ``8224845a67ac`` on a
#: from-zero run.
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

#: Manager and User both get read-only. Defining a field is administration;
#: seeing which fields exist is what makes a form renderable.
_READ_ONLY: tuple[str, ...] = ("VIEW",)

_MODULE = "custom_fields"

#: Mirrors ``models.CustomFieldType``. Spelled out rather than imported, for
#: the reason ``_ACTIONS`` is.
_FIELD_TYPES: tuple[str, ...] = (
    "TEXT",
    "TEXTAREA",
    "NUMBER",
    "DECIMAL",
    "DATE",
    "DATETIME",
    "BOOLEAN",
    "EMAIL",
    "URL",
    "PHONE",
    "PICKLIST",
    "MULTI_PICKLIST",
)


def _timestamps() -> list[sa.Column[object]]:
    """The mixin columns every CRM table carries, spelled out once."""
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

    # --- Enums -------------------------------------------------------------
    #
    # `crm_entity_type` already exists — activities, tasks, notes and email all
    # use it — so it is referenced with `create_type=False` and never created
    # here. Emitting CREATE TYPE for it would fail on every database this
    # revision will ever run against.
    sa.Enum(*_FIELD_TYPES, name="custom_field_type", schema=CRM).create(
        connection, checkfirst=True
    )
    custom_field_type = postgresql.ENUM(
        *_FIELD_TYPES, name="custom_field_type", schema=CRM, create_type=False
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

    # --- Picklists ---------------------------------------------------------

    op.create_table(
        "picklists",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("api_name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index("ix_picklists_organization_id", "picklists", ["organization_id"], schema=CRM)
    op.create_index("ix_picklists_deleted_at", "picklists", ["deleted_at"], schema=CRM)
    # Partial, so a retired list's api_name is free again: deletion here is
    # soft and the row never leaves, so an unconditional constraint would burn
    # every name anybody ever retired.
    op.create_index(
        "uq_picklists_organization_id_api_name_live",
        "picklists",
        ["organization_id", "api_name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "picklist_options",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "picklist_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.picklists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_picklist_options_organization_id",
        "picklist_options",
        ["organization_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_picklist_options_deleted_at", "picklist_options", ["deleted_at"], schema=CRM
    )
    op.create_index(
        "ix_picklist_options_organization_id_picklist_id",
        "picklist_options",
        ["organization_id", "picklist_id"],
        schema=CRM,
    )
    op.create_index(
        "uq_picklist_options_picklist_id_value_live",
        "picklist_options",
        ["picklist_id", "value"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # At most one default per list. Partial on both conditions, so it
    # constrains only the rows that make the claim.
    op.create_index(
        "uq_picklist_options_picklist_id_default",
        "picklist_options",
        ["picklist_id"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("is_default AND deleted_at IS NULL"),
    )

    # --- Field definitions -------------------------------------------------

    op.create_table(
        "custom_field_definitions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entity_type", crm_entity_type, nullable=False),
        sa.Column("api_name", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("field_type", custom_field_type, nullable=False),
        sa.Column("help_text", sa.String(length=500), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column(
            "picklist_id",
            sa.Uuid(as_uuid=True),
            # RESTRICT: deleting a list a field still draws from would leave
            # that field unrenderable and its stored values unexplainable. The
            # service turns the refusal into a 409 naming the fields.
            sa.ForeignKey(f"{CRM}.picklists.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("min_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("max_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("min_length", sa.Integer(), nullable=True),
        sa.Column("max_length", sa.Integer(), nullable=True),
        sa.Column("pattern", sa.String(length=255), nullable=True),
        # A picklist field without a list, or a non-picklist field with one,
        # are both configurations that cannot be rendered or validated. The
        # service refuses them with a 422; the table refuses them absolutely,
        # so a path that bypassed the schema still cannot store one.
        sa.CheckConstraint(
            "(field_type IN ('PICKLIST', 'MULTI_PICKLIST')) = (picklist_id IS NOT NULL)",
            name="ck_custom_field_definitions_picklist_type_requires_picklist",
        ),
        sa.CheckConstraint(
            "min_value IS NULL OR max_value IS NULL OR min_value <= max_value",
            name="ck_custom_field_definitions_value_range_ordered",
        ),
        sa.CheckConstraint(
            "min_length IS NULL OR max_length IS NULL OR min_length <= max_length",
            name="ck_custom_field_definitions_length_range_ordered",
        ),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_custom_field_definitions_organization_id",
        "custom_field_definitions",
        ["organization_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_custom_field_definitions_deleted_at",
        "custom_field_definitions",
        ["deleted_at"],
        schema=CRM,
    )
    # The read on the write path of every record: "which fields apply to this
    # entity type in this organization".
    op.create_index(
        "ix_custom_field_definitions_organization_id_entity_type",
        "custom_field_definitions",
        ["organization_id", "entity_type"],
        schema=CRM,
    )
    op.create_index(
        "uq_custom_field_definitions_org_entity_api_name_live",
        "custom_field_definitions",
        ["organization_id", "entity_type", "api_name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- The value column on each record type ------------------------------

    for table in _VALUE_TABLES:
        op.add_column(
            table,
            sa.Column(
                "custom_fields",
                postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            schema=CRM,
        )
        # `jsonb_path_ops`: half the size of the default operator class and
        # faster for the containment queries this column receives. What it
        # gives up is `?` key-exists support, which no query path here uses.
        op.create_index(
            f"ix_{table}_custom_fields",
            table,
            ["custom_fields"],
            schema=CRM,
            postgresql_using="gin",
            postgresql_ops={"custom_fields": "jsonb_path_ops"},
        )

    # --- Row-Level Security ------------------------------------------------

    for table in _TABLES:
        enable_rls(connection, table, schema=CRM)

    # --- The `custom_fields` permission module ------------------------------

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
                "description": f"{action} custom field definitions and picklists",
            },
        )

    _grant("Admin", _ACTIONS, connection)
    _grant("Manager", _READ_ONLY, connection)
    _grant("User", _READ_ONLY, connection)


def _grant(role: str, actions: tuple[str, ...], connection: sa.Connection) -> None:
    """Grant ``custom_fields.<action>`` to a system role template.

    Templates are the rows with ``organization_id IS NULL``; every
    organization's memberships reference them, so granting once here reaches
    every existing tenant without a per-organization loop.
    """
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

    # Dropping the value columns discards every custom value in the database.
    # That is what a downgrade of this revision means and there is no way to
    # keep them — the tables that explain what they are go with it. Said out
    # loud here because a downgrade is usually reversible and this one is not.
    for table in _VALUE_TABLES:
        op.drop_index(f"ix_{table}_custom_fields", table_name=table, schema=CRM)
        op.drop_column(table, "custom_fields", schema=CRM)

    for table in reversed(_TABLES):
        disable_rls(connection, table, schema=CRM)

    op.drop_table("custom_field_definitions", schema=CRM)
    op.drop_table("picklist_options", schema=CRM)
    op.drop_table("picklists", schema=CRM)

    sa.Enum(name="custom_field_type", schema=CRM).drop(connection, checkfirst=True)
