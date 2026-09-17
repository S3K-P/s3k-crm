"""Next Best Action engine: tenant rules, action log, Copilot drafts.

Revision ID: 20260921_0100
Revises: 20260920_0100
Create Date: 2026-09-21 01:00:00.000000

Two tenant-scoped tables and one enum value.

* ``crm.nba_rules`` — configuration: a tenant's own ``IF conditions THEN
  action`` rules, and its overrides of the built-in rules (active flag,
  priority, thresholds). Soft-deleted and audited like ``workflow_rules``.
* ``crm.nba_action_logs`` — history: a rep executed or dismissed a recommended
  action on a record. Append-only; the engine reads it to keep an action a rep
  has already dealt with from being recommended again within its cooldown.
* ``ai_feature`` gains ``NBA_COPILOT`` for Copilot drafts stored in
  ``ai_generations``.

No new permission module: reading and acting on recommendations uses the
existing ``ai_insights`` VIEW/CREATE grants, and editing the organization's
rules requires ``ai_insights.ADMIN``, which only the Admin role holds.

The enum value is not removed on downgrade — PostgreSQL cannot drop an enum
value, and rows using it may exist; an unused value is harmless.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260921_0100"
down_revision: str | Sequence[str] | None = "20260920_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"
_TABLES: tuple[str, ...] = ("nba_rules", "nba_action_logs")
_OUTCOMES: tuple[str, ...] = ("EXECUTED", "DISMISSED")


def upgrade() -> None:
    connection = op.get_bind()

    op.execute(f"ALTER TYPE {CRM}.ai_feature ADD VALUE IF NOT EXISTS 'NBA_COPILOT'")

    op.create_table(
        "nba_rules",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text("uuidv7()")
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("builtin_key", sa.String(length=80), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("applies_to", sa.String(length=16), nullable=False, server_default="BOTH"),
        sa.Column("condition_logic", sa.String(length=3), nullable=False, server_default="AND"),
        sa.Column(
            "conditions", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("action_code", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=8), nullable=False, server_default="MEDIUM"),
        sa.Column("reason", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("timing", sa.String(length=80), nullable=True),
        sa.Column("due_in_hours", sa.Integer(), nullable=True),
        sa.Column("cooldown_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema=CRM,
    )
    op.create_index("ix_nba_rules_organization_id", "nba_rules", ["organization_id"], schema=CRM)
    op.create_index("ix_nba_rules_deleted_at", "nba_rules", ["deleted_at"], schema=CRM)
    op.create_index(
        "uq_nba_rules_organization_id_builtin_key_live",
        "nba_rules",
        ["organization_id", "builtin_key"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("builtin_key IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_nba_rules_organization_id_name_live",
        "nba_rules",
        ["organization_id", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("builtin_key IS NULL AND deleted_at IS NULL"),
    )

    sa.Enum(*_OUTCOMES, name="nba_action_outcome", schema=CRM).create(connection, checkfirst=True)
    outcome = postgresql.ENUM(*_OUTCOMES, name="nba_action_outcome", schema=CRM, create_type=False)

    op.create_table(
        "nba_action_logs",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text("uuidv7()")
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("action_code", sa.String(length=64), nullable=False),
        sa.Column("outcome", outcome, nullable=False),
        sa.Column(
            "rule_keys", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("generation_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=CRM,
    )
    op.create_index(
        "ix_nba_action_logs_organization_id", "nba_action_logs", ["organization_id"], schema=CRM
    )
    op.create_index(
        "ix_nba_action_logs_org_entity_action_created",
        "nba_action_logs",
        ["organization_id", "entity_type", "entity_id", "action_code", "created_at"],
        schema=CRM,
    )

    for table in _TABLES:
        enable_rls(connection, table, schema=CRM)


def downgrade() -> None:
    connection = op.get_bind()
    for table in reversed(_TABLES):
        disable_rls(connection, table, schema=CRM)
        op.drop_table(table, schema=CRM)
    sa.Enum(name="nba_action_outcome", schema=CRM).drop(connection, checkfirst=True)
