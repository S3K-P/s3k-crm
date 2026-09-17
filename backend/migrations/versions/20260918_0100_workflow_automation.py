"""Workflow automation: trigger -> conditions -> actions (Checkpoint 6).

Revision ID: 20260918_0100
Revises: 20260917_0300
Create Date: 2026-09-18 01:00:00.000000

Two tenant-scoped tables, the same split ``blueprints``/``blueprint_transitions``
use and for the same reason: **configuration** (``workflow_rules`` — what to
watch for, what to check, what to do) is edited and soft-deleted like every
other CRM configuration object; **history** (``workflow_runs`` — what
actually happened one time a rule fired) is append-only, the same shape as
``platform.outbox_events``.

**Idempotency lives in two partial unique indexes, not application code
alone.** ``uq_workflow_runs_rule_source_event`` is what stops the *same*
outbox event, redelivered because the dispatcher's own completion write was
lost between two commits, from running a rule's actions twice —
``EventDispatcher`` itself only promises at-least-once delivery, by design
(see ``platform.events.service``'s module docstring), so the guarantee that
one event's automation runs once has to live here. ``uq_workflow_runs_rule_dedupe_key``
is the equivalent for a scheduled/date rule, which has no outbox event to key
on at all — the scanner mints ``f"{rule_id}:{record_id}:{date}"`` so an
hourly tick finding the same overdue record again does not re-fire it the
same day.

**The ``workflows`` permission module.** Same shape as ``blueprints``: ``VIEW``
goes to every system role — a rep whose record a workflow touched has to be
able to see which rule did it in the execution history — and everything else
stays with Admin, since a workflow decides what happens to every matching
record in the organization.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260918_0100"
down_revision: str | Sequence[str] | None = "20260917_0300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: Created in dependency order, dropped in reverse.
_TABLES: tuple[str, ...] = ("workflow_rules", "workflow_runs")

#: Pinned snapshot of the action vocabulary as of this revision — not
#: imported from ``app.platform.authorization.catalog``, for the reason
#: ``blueprints``' migration gives: a migration is a snapshot of history, and
#: reading live code means a later edit silently rewrites what an old
#: revision does.
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
_MODULE = "workflows"

#: Mirrors ``workflows.models.WorkflowEntityType``. Spelled out rather than
#: imported, for the reason ``_ACTIONS`` is.
_ENTITY_TYPES: tuple[str, ...] = (
    "ACCOUNT",
    "CONTACT",
    "LEAD",
    "OPPORTUNITY",
    "CAMPAIGN",
    "TASK",
)
_TRIGGER_TYPES: tuple[str, ...] = (
    "RECORD_CREATED",
    "RECORD_UPDATED",
    "FIELD_CHANGED",
    "STAGE_CHANGED",
    "STATUS_CHANGED",
    "OWNER_CHANGED",
    "SCHEDULED",
    "TASK_DUE",
)
_RUN_STATUSES: tuple[str, ...] = ("SUCCEEDED", "PARTIAL", "FAILED")


def _timestamps() -> list[sa.Column[object]]:
    """The mixin columns every CRM configuration table carries."""
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

    sa.Enum(*_ENTITY_TYPES, name="workflow_entity_type", schema=CRM).create(
        connection, checkfirst=True
    )
    sa.Enum(*_TRIGGER_TYPES, name="workflow_trigger_type", schema=CRM).create(
        connection, checkfirst=True
    )
    sa.Enum(*_RUN_STATUSES, name="workflow_run_status", schema=CRM).create(
        connection, checkfirst=True
    )
    workflow_entity_type = postgresql.ENUM(
        *_ENTITY_TYPES, name="workflow_entity_type", schema=CRM, create_type=False
    )
    workflow_trigger_type = postgresql.ENUM(
        *_TRIGGER_TYPES, name="workflow_trigger_type", schema=CRM, create_type=False
    )
    workflow_run_status = postgresql.ENUM(
        *_RUN_STATUSES, name="workflow_run_status", schema=CRM, create_type=False
    )

    op.create_table(
        "workflow_rules",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("entity_type", workflow_entity_type, nullable=False),
        sa.Column("trigger_type", workflow_trigger_type, nullable=False),
        sa.Column(
            "trigger_config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "condition_logic", sa.String(length=3), nullable=False, server_default="AND"
        ),
        sa.Column(
            "conditions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "actions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_workflow_rules_organization_id", "workflow_rules", ["organization_id"], schema=CRM
    )
    op.create_index(
        "ix_workflow_rules_deleted_at", "workflow_rules", ["deleted_at"], schema=CRM
    )
    op.create_index(
        "ix_workflow_rules_organization_id_entity_type_active",
        "workflow_rules",
        ["organization_id", "entity_type", "is_active"],
        schema=CRM,
    )
    op.create_index(
        "uq_workflow_rules_organization_id_name_live",
        "workflow_rules",
        ["organization_id", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "workflow_rule_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.workflow_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", workflow_entity_type, nullable=False),
        sa.Column("record_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("source_event_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=160), nullable=True),
        sa.Column("correlation_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", workflow_run_status, nullable=False),
        sa.Column("actions_attempted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "action_results",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        schema=CRM,
    )
    op.create_index(
        "ix_workflow_runs_organization_id_created_at",
        "workflow_runs",
        ["organization_id", "created_at"],
        schema=CRM,
    )
    op.create_index(
        "ix_workflow_runs_organization_id_rule_id_created_at",
        "workflow_runs",
        ["organization_id", "workflow_rule_id", "created_at"],
        schema=CRM,
    )
    op.create_index(
        "ix_workflow_runs_organization_id_entity_type_record_id",
        "workflow_runs",
        ["organization_id", "entity_type", "record_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_workflow_runs_correlation_id", "workflow_runs", ["correlation_id"], schema=CRM
    )
    # Idempotency — see the module docstring.
    op.create_index(
        "uq_workflow_runs_rule_source_event",
        "workflow_runs",
        ["workflow_rule_id", "source_event_id"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )
    op.create_index(
        "uq_workflow_runs_rule_dedupe_key",
        "workflow_runs",
        ["workflow_rule_id", "dedupe_key"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
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
                "description": f"{action} workflow automation configuration",
            },
        )

    _grant("Admin", _ACTIONS, connection)
    _grant("Manager", _READ_ONLY, connection)
    _grant("User", _READ_ONLY, connection)


def _grant(role: str, actions: tuple[str, ...], connection: sa.Connection) -> None:
    """Grant ``workflows.<action>`` to a system role template.

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

    op.drop_table("workflow_runs", schema=CRM)
    op.drop_table("workflow_rules", schema=CRM)

    sa.Enum(name="workflow_run_status", schema=CRM).drop(connection, checkfirst=True)
    sa.Enum(name="workflow_trigger_type", schema=CRM).drop(connection, checkfirst=True)
    sa.Enum(name="workflow_entity_type", schema=CRM).drop(connection, checkfirst=True)
