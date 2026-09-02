"""Assignment rules and per-organization automation settings.

Revision ID: 20260903_0200
Revises: 20260903_0100
Create Date: 2026-09-03 02:00:00.000000

Both tables are configuration, not a workflow engine (analysis §4.4, §5.6).

``assignment_rules`` decides who owns a new record: an ordered list, each with
up to three criteria and a set of candidate owners cycled round-robin.
``owner_ids`` is an array of plain user ids rather than a join table with
foreign keys, because ``owner_id`` is deliberately not a foreign key anywhere in
CRM (constraint C2) — ownership has to survive the owner leaving the platform,
and a rule naming a departed user is a configuration problem, not a broken
reference.

``automation_settings`` holds the switches. Scoring and health default to
**off**: a wrong score erodes trust faster than a missing one, and a tenant
should not find their accounts relabelled AT_RISK overnight by a model they
have never looked at. Reminders default to on, because a nudge about your own
stale deal is helpful and reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260903_0200"
down_revision: str | None = "20260903_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM_SCHEMA = "crm"


def _crm_entity_columns() -> list[sa.Column[object]]:
    """The standard CrmEntityMixin column set, spelled out.

    Pinned rather than derived from the mixin: a migration is a snapshot, and
    importing the live mixin would let a later edit silently rewrite what this
    revision created.
    """
    return [
        sa.Column(
            "id", sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text("uuidv7()")
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "assignment_rules",
        *_crm_entity_columns(),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("match_country", sa.String(length=120), nullable=True),
        sa.Column("match_industry", sa.String(length=120), nullable=True),
        sa.Column("match_lead_source_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "owner_ids",
            postgresql.ARRAY(sa.Uuid(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("last_assigned_index", sa.Integer(), nullable=False, server_default="-1"),
        sa.CheckConstraint("sort_order >= 0", name="ck_assignment_rules_sort_order_non_negative"),
        sa.CheckConstraint(
            "last_assigned_index >= 0",
            name="ck_assignment_rules_last_assigned_index_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["match_lead_source_id"],
            [f"{CRM_SCHEMA}.lead_sources.id"],
            name="fk_assignment_rules_match_lead_source_id_lead_sources",
            ondelete="SET NULL",
        ),
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_assignment_rules_organization_id",
        "assignment_rules",
        ["organization_id"],
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_assignment_rules_deleted_at",
        "assignment_rules",
        ["deleted_at"],
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_assignment_rules_organization_id_module_active",
        "assignment_rules",
        ["organization_id", "module", "sort_order"],
        schema=CRM_SCHEMA,
        postgresql_where=sa.text("is_active AND deleted_at IS NULL"),
    )

    op.create_table(
        "automation_settings",
        *_crm_entity_columns(),
        sa.Column(
            "lead_scoring_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "contact_scoring_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "account_health_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "account_status_automation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "stale_reminders_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("stale_opportunity_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("stale_lead_days", sa.Integer(), nullable=False, server_default="7"),
        sa.CheckConstraint(
            "stale_opportunity_days > 0 AND stale_lead_days > 0",
            name="ck_automation_settings_stale_windows_positive",
        ),
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_automation_settings_organization_id",
        "automation_settings",
        ["organization_id"],
        schema=CRM_SCHEMA,
    )
    op.create_index(
        "ix_automation_settings_deleted_at",
        "automation_settings",
        ["deleted_at"],
        schema=CRM_SCHEMA,
    )
    # One live settings row per organization. Partial so an archived row does
    # not block creating a replacement, matching every other soft-delete-aware
    # uniqueness rule in the schema.
    op.create_index(
        "uq_automation_settings_organization_id_live",
        "automation_settings",
        ["organization_id"],
        unique=True,
        schema=CRM_SCHEMA,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    for table in ("assignment_rules", "automation_settings"):
        enable_rls(connection, table, schema=CRM_SCHEMA)


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("automation_settings", "assignment_rules"):
        disable_rls(connection, table, schema=CRM_SCHEMA)
    op.drop_table("automation_settings", schema=CRM_SCHEMA)
    op.drop_table("assignment_rules", schema=CRM_SCHEMA)
