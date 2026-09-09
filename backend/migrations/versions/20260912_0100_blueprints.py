"""Blueprints: tenant-configured processes over a record's state field (Phase G).

Revision ID: 20260912_0100
Revises: 20260911_0100
Create Date: 2026-09-12 01:00:00.000000

Two tenant-scoped tables and one permission module.

**The two unique indexes are the schema's half of "no invalid states".** The
service refuses an unsatisfiable configuration with a message; these refuse the
two shapes that would have no meaning at all, absolutely, so a path that
bypassed the service still cannot create one.

``uq_blueprints_organization_id_field_active`` — at most one *active* blueprint
per governed field. Two active processes over one column is not a configuration
with an interpretation: a move would be permitted by one and refused by the
other, and which won would depend on the order the planner returned rows in.
Partial on ``is_active``, so a tenant may keep as many drafts and retired
processes as they like.

``uq_blueprint_transitions_from_to_live`` — one rule per origin/destination
pair. Two rules for the same move would mean two different sets of requirements
with nothing to say which applies.

**``from_state`` uses the literal ``'*'`` for "from anywhere", not NULL.** NULL
is not equal to NULL in a unique index, so a nullable column would let an
administrator create the same wildcard rule twice and then wonder which of the
two was being enforced.

**No state table.** A state is the enum the record's column already holds, or a
pipeline stage row. Copying them here would create a second list to drift from
the first and blueprints referring to states that no longer exist. Transitions
store the value as text, and :mod:`app.products.crm.blueprints.enforcement`
treats an unrecognised one as constraining nothing — which is what keeps
records that predate a blueprint, or outlive a stage, movable.

**The ``blueprints`` permission module.** ``VIEW`` goes to every system role,
which is the same call ``custom_fields`` made and for the same reason: a rep
whose transition was refused has to be able to see the rule that stopped them
and what would unblock it, and it grants sight of no record. Everything else
stays with Admin — a blueprint decides what everybody *else* in the
organization may do with a record, which is a wider power than editing any
single one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260912_0100"
down_revision: str | Sequence[str] | None = "20260911_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: Created in dependency order, dropped in reverse.
_TABLES: tuple[str, ...] = ("blueprints", "blueprint_transitions")

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

#: Manager and User get read-only. Configuring a process is administration.
_READ_ONLY: tuple[str, ...] = ("VIEW",)

_MODULE = "blueprints"

#: Mirrors ``models.BlueprintField``. Spelled out rather than imported, for the
#: reason ``_ACTIONS`` is.
_FIELDS: tuple[str, ...] = ("LEAD_STATUS", "OPPORTUNITY_STAGE")


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

    sa.Enum(*_FIELDS, name="blueprint_field", schema=CRM).create(connection, checkfirst=True)
    blueprint_field = postgresql.ENUM(
        *_FIELDS, name="blueprint_field", schema=CRM, create_type=False
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
        "blueprints",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("field", blueprint_field, nullable=False),
        sa.Column("entity_type", crm_entity_type, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # The pairing of field to record type is a fact about the schema, not a
        # tenant's choice. Enforced here as well as derived in the service, so
        # a blueprint claiming to govern a lead's status on an opportunity is
        # not a row the database will hold.
        sa.CheckConstraint(
            "(field = 'LEAD_STATUS' AND entity_type = 'LEAD') OR "
            "(field = 'OPPORTUNITY_STAGE' AND entity_type = 'OPPORTUNITY')",
            name="ck_blueprints_field_matches_entity_type",
        ),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_blueprints_organization_id", "blueprints", ["organization_id"], schema=CRM
    )
    op.create_index("ix_blueprints_deleted_at", "blueprints", ["deleted_at"], schema=CRM)
    # The read on the state-change path of every governed record.
    op.create_index(
        "ix_blueprints_organization_id_field",
        "blueprints",
        ["organization_id", "field"],
        schema=CRM,
    )
    op.create_index(
        "uq_blueprints_organization_id_name_live",
        "blueprints",
        ["organization_id", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # At most one *active* blueprint per field — see the module docstring.
    op.create_index(
        "uq_blueprints_organization_id_field_active",
        "blueprints",
        ["organization_id", "field"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("is_active AND deleted_at IS NULL"),
    )

    op.create_table(
        "blueprint_transitions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "blueprint_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.blueprints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        # NOT NULL with '*' for "from anywhere" — see the module docstring for
        # why a nullable column would break the unique index below.
        sa.Column("from_state", sa.String(length=64), nullable=False),
        sa.Column("to_state", sa.String(length=64), nullable=False),
        sa.Column(
            "required_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("required_permission", sa.String(length=80), nullable=True),
        sa.Column(
            "require_note", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_blueprint_transitions_organization_id",
        "blueprint_transitions",
        ["organization_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_blueprint_transitions_deleted_at",
        "blueprint_transitions",
        ["deleted_at"],
        schema=CRM,
    )
    op.create_index(
        "ix_blueprint_transitions_organization_id_blueprint_id",
        "blueprint_transitions",
        ["organization_id", "blueprint_id"],
        schema=CRM,
    )
    op.create_index(
        "uq_blueprint_transitions_from_to_live",
        "blueprint_transitions",
        ["blueprint_id", "from_state", "to_state"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
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
                "description": f"{action} blueprint process configuration",
            },
        )

    _grant("Admin", _ACTIONS, connection)
    _grant("Manager", _READ_ONLY, connection)
    _grant("User", _READ_ONLY, connection)


def _grant(role: str, actions: tuple[str, ...], connection: sa.Connection) -> None:
    """Grant ``blueprints.<action>`` to a system role template.

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

    for table in reversed(_TABLES):
        disable_rls(connection, table, schema=CRM)

    op.drop_table("blueprint_transitions", schema=CRM)
    op.drop_table("blueprints", schema=CRM)

    sa.Enum(name="blueprint_field", schema=CRM).drop(connection, checkfirst=True)
