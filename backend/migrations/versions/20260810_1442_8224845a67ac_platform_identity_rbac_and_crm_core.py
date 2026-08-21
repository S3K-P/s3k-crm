"""platform identity, rbac and crm core

Revision ID: 8224845a67ac
Revises: 0001_initial_schemas
Create Date: 2026-08-10 14:42:58.038107+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

# ---------------------------------------------------------------------------
# The permission vocabulary **as of this revision**, pinned.
#
# This migration used to import PERMISSION_ACTIONS / PERMISSION_MODULES /
# SYSTEM_ROLES from `app.platform.authorization.catalog`, on the reasoning that
# the database could then never disagree with the code. The opposite happened:
# the catalogue is living code, this migration is history, and the moment an
# action was added to the catalogue (`VIEW_ALL`, revision 20260819_0200) a
# **fresh** database broke — the seed tried to insert a value the CREATE TYPE
# a few hundred lines below does not contain:
#
#     invalid input value for enum platform.permission_action: "VIEW_ALL"
#
# Existing databases were unaffected, because the seed had already run there,
# which is exactly why it went unnoticed until a from-zero run.
#
# So the vocabulary is a literal snapshot now. It must match the enum values
# in the `permissions.action` column definition below and must never be
# "kept in sync" with the catalogue again: a later action is a later migration.
# ---------------------------------------------------------------------------

_ACTIONS: tuple[str, ...] = ("VIEW", "CREATE", "EDIT", "DELETE", "EXPORT", "ADMIN")

_MODULES: tuple[str, ...] = (
    "users",
    "organizations",
    "roles",
    "audit",
    "accounts",
    "contacts",
    "leads",
    "lead_sources",
    "opportunities",
    "campaigns",
    "activities",
    "tasks",
    "notes",
    "documents",
    "dashboard",
)

_CRM_MODULES: tuple[str, ...] = (
    "accounts",
    "contacts",
    "leads",
    "lead_sources",
    "opportunities",
    "campaigns",
    "activities",
    "tasks",
    "notes",
    "documents",
    "dashboard",
)


def _codes(modules: tuple[str, ...], actions: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{module}.{action}" for module in modules for action in actions)


#: name -> (description, granted codes). Mirrors SYSTEM_ROLES at this revision.
_SYSTEM_ROLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "Admin": (
        "Full access to the organization, its members and all CRM data.",
        _codes(_MODULES, _ACTIONS),
    ),
    "Manager": (
        "Manages CRM data and the sales pipeline; may delete and export records.",
        (
            *_codes(_CRM_MODULES, ("VIEW", "CREATE", "EDIT", "DELETE", "EXPORT")),
            "users.VIEW",
            "organizations.VIEW",
        ),
    ),
    "User": (
        "Works day to day in the CRM: may read, create and edit records.",
        _codes(_CRM_MODULES, ("VIEW", "CREATE", "EDIT")),
    ),
}

revision: str = "8224845a67ac"
down_revision: str | None = "0001_initial_schemas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Row-Level Security
# ---------------------------------------------------------------------------

#: Every table carrying an ``organization_id``. Each one gets the standard
#: fail-closed tenant policy from :mod:`app.core.rls`.
#:
#: Tables deliberately excluded, with the reason:
#:
#: ``platform.users``, ``user_profiles``, ``sessions``
#:     Global identity. A user is not owned by one organization; scoping runs
#:     through ``organization_memberships``.
#: ``platform.organizations``, ``organization_memberships``
#:     Read while *establishing* tenant context, before any context exists. A
#:     policy here would make login impossible. Protected by explicit query
#:     filters in the organizations repository instead.
#: ``platform.roles``, ``role_permissions``, ``membership_roles``, ``permissions``
#:     ``roles.organization_id`` is nullable — NULL marks a system template
#:     shared by all tenants, and the standard predicate would hide exactly
#:     those rows. Authorization filters these explicitly.
#: ``crm.meetings``
#:     A one-to-one extension of ``crm.activities``; reaching it requires first
#:     reading the parent activity, which is policy-filtered.
TENANT_SCOPED_TABLES: tuple[tuple[str, str], ...] = (
    ("platform", "attachments"),
    ("crm", "accounts"),
    ("crm", "activities"),
    ("crm", "campaign_members"),
    ("crm", "campaigns"),
    ("crm", "contacts"),
    ("crm", "lead_sources"),
    ("crm", "leads"),
    ("crm", "notes"),
    ("crm", "opportunities"),
    ("crm", "opportunity_stage_history"),
    ("crm", "pipeline_stages"),
    ("crm", "pipelines"),
    ("crm", "tasks"),
)

#: Native enum types created implicitly by ``create_table``. PostgreSQL does not
#: drop them with the table, so downgrade must do it explicitly or a re-upgrade
#: fails with "type already exists".
ENUM_TYPES: tuple[tuple[str, str], ...] = (
    ("platform", "user_status"),
    ("platform", "organization_status"),
    ("platform", "membership_status"),
    ("platform", "permission_action"),
    ("platform", "attachment_status"),
    ("crm", "account_status"),
    ("crm", "contact_status"),
    ("crm", "lead_status"),
    ("crm", "lead_source_status"),
    ("crm", "crm_priority"),
    ("crm", "campaign_type"),
    ("crm", "campaign_status"),
    ("crm", "campaign_member_type"),
    ("crm", "activity_type"),
    ("crm", "activity_status"),
    ("crm", "meeting_type"),
    ("crm", "task_status"),
    ("crm", "note_visibility"),
    ("crm", "crm_entity_type"),
)


def _enable_tenant_rls(connection: sa.engine.Connection) -> None:
    for schema, table in TENANT_SCOPED_TABLES:
        enable_rls(connection, table, schema=schema)


def _disable_tenant_rls(connection: sa.engine.Connection) -> None:
    for schema, table in TENANT_SCOPED_TABLES:
        disable_rls(connection, table, schema=schema)


def _drop_enum_types(connection: sa.engine.Connection) -> None:
    for schema, name in ENUM_TYPES:
        connection.execute(sa.text(f'DROP TYPE IF EXISTS "{schema}"."{name}"'))


# ---------------------------------------------------------------------------
# Reference data: the permission catalogue and the three system roles
# ---------------------------------------------------------------------------


def _seed_permissions_and_system_roles(connection: sa.engine.Connection) -> None:
    """Insert the permission vocabulary and the Admin/Manager/User templates.

    Sourced from the pinned snapshot at the top of this file, **not** from the
    live catalogue — see the note there for why.
    """
    for module in _MODULES:
        for action in _ACTIONS:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.permissions (module, action, description) "
                    "VALUES (:module, CAST(:action AS platform.permission_action), :description) "
                    "ON CONFLICT (module, action) DO NOTHING"
                ),
                {
                    "module": module,
                    "action": action,
                    "description": f"{action.title()} access to {module.replace('_', ' ')}.",
                },
            )

    for role_name, (description, granted) in _SYSTEM_ROLES.items():
        connection.execute(
            sa.text(
                "INSERT INTO platform.roles (organization_id, name, description, is_system) "
                "VALUES (NULL, :name, :description, true) "
                "ON CONFLICT (organization_id, name) DO NOTHING"
            ),
            {"name": role_name, "description": description},
        )

        for code in granted:
            module, _, action = code.partition(".")
            connection.execute(
                sa.text(
                    "INSERT INTO platform.role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
                    "WHERE r.organization_id IS NULL AND r.name = :role_name "
                    "  AND p.module = :module "
                    "  AND p.action = CAST(:action AS platform.permission_action) "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"role_name": role_name, "module": module, "action": action},
            )


def _drop_seed_data(connection: sa.engine.Connection) -> None:
    """Remove only what this migration seeded.

    Scoped to system roles (``organization_id IS NULL``) so a tenant's own
    custom roles are never touched by a downgrade.
    """
    connection.execute(
        sa.text(
            "DELETE FROM platform.role_permissions rp USING platform.roles r "
            "WHERE rp.role_id = r.id AND r.organization_id IS NULL AND r.is_system"
        )
    )
    connection.execute(
        sa.text("DELETE FROM platform.roles WHERE organization_id IS NULL AND is_system")
    )
    connection.execute(sa.text("DELETE FROM platform.permissions"))


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "accounts",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("company_size", sa.String(length=64), nullable=True),
        sa.Column("annual_revenue", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE", "ONBOARDING", "AT_RISK", "CHURNED", name="account_status", schema="crm"
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("primary_contact_id", sa.Uuid(), nullable=True),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("integration_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "health_score IS NULL OR (health_score >= 0 AND health_score <= 100)",
            name=op.f("ck_accounts_health_score_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_accounts_deleted_at"), "accounts", ["deleted_at"], unique=False, schema="crm"
    )
    op.create_index(
        op.f("ix_accounts_organization_id"),
        "accounts",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_accounts_organization_id_deleted_at",
        "accounts",
        ["organization_id", "deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_accounts_organization_id_name",
        "accounts",
        ["organization_id", "name"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_accounts_organization_id_owner_id",
        "accounts",
        ["organization_id", "owner_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_accounts_organization_id_status",
        "accounts",
        ["organization_id", "status"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "activities",
        sa.Column(
            "type",
            sa.Enum("CALL", "EMAIL", "MEETING", "NOTE", "TASK", name="activity_type", schema="crm"),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PLANNED", "COMPLETED", "CANCELLED", name="activity_status", schema="crm"),
            server_default="PLANNED",
            nullable=False,
        ),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column(
            "related_entity_type",
            sa.Enum(
                "ACCOUNT",
                "CONTACT",
                "LEAD",
                "OPPORTUNITY",
                "CAMPAIGN",
                name="crm_entity_type",
                schema="crm",
            ),
            nullable=True,
        ),
        sa.Column("related_entity_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_activities_deleted_at"), "activities", ["deleted_at"], unique=False, schema="crm"
    )
    op.create_index(
        op.f("ix_activities_organization_id"),
        "activities",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_activities_organization_id_deleted_at",
        "activities",
        ["organization_id", "deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_activities_organization_id_due_date",
        "activities",
        ["organization_id", "due_date"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_activities_organization_id_related",
        "activities",
        ["organization_id", "related_entity_type", "related_entity_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_activities_organization_id_type_status",
        "activities",
        ["organization_id", "type", "status"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "lead_sources",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "INACTIVE", name="lead_source_status", schema="crm"),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_sources")),
        sa.UniqueConstraint("organization_id", "name", name="uq_lead_sources_organization_id_name"),
        schema="crm",
    )
    op.create_index(
        op.f("ix_lead_sources_deleted_at"),
        "lead_sources",
        ["deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        op.f("ix_lead_sources_organization_id"),
        "lead_sources",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_lead_sources_organization_id_status",
        "lead_sources",
        ["organization_id", "status"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "notes",
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "visibility",
            sa.Enum("PRIVATE", "TEAM", "ORGANIZATION", name="note_visibility", schema="crm"),
            server_default="TEAM",
            nullable=False,
        ),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column(
            "related_entity_type",
            sa.Enum(
                "ACCOUNT",
                "CONTACT",
                "LEAD",
                "OPPORTUNITY",
                "CAMPAIGN",
                name="crm_entity_type",
                schema="crm",
            ),
            nullable=False,
        ),
        sa.Column("related_entity_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_notes_deleted_at"), "notes", ["deleted_at"], unique=False, schema="crm"
    )
    op.create_index(
        op.f("ix_notes_organization_id"), "notes", ["organization_id"], unique=False, schema="crm"
    )
    op.create_index(
        "ix_notes_organization_id_deleted_at",
        "notes",
        ["organization_id", "deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_notes_organization_id_related",
        "notes",
        ["organization_id", "related_entity_type", "related_entity_id"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "pipelines",
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipelines")),
        sa.UniqueConstraint("organization_id", "name", name="uq_pipelines_organization_id_name"),
        schema="crm",
    )
    op.create_index(
        op.f("ix_pipelines_deleted_at"), "pipelines", ["deleted_at"], unique=False, schema="crm"
    )
    op.create_index(
        op.f("ix_pipelines_organization_id"),
        "pipelines",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "tasks",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED", name="task_status", schema="crm"
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("HIGH", "MEDIUM", "LOW", name="crm_priority", schema="crm"),
            server_default="MEDIUM",
            nullable=False,
        ),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column(
            "related_entity_type",
            sa.Enum(
                "ACCOUNT",
                "CONTACT",
                "LEAD",
                "OPPORTUNITY",
                "CAMPAIGN",
                name="crm_entity_type",
                schema="crm",
            ),
            nullable=True,
        ),
        sa.Column("related_entity_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_tasks_deleted_at"), "tasks", ["deleted_at"], unique=False, schema="crm"
    )
    op.create_index(
        op.f("ix_tasks_organization_id"), "tasks", ["organization_id"], unique=False, schema="crm"
    )
    op.create_index(
        "ix_tasks_organization_id_assigned_to_id_status",
        "tasks",
        ["organization_id", "assigned_to_id", "status"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_tasks_organization_id_deleted_at",
        "tasks",
        ["organization_id", "deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_tasks_organization_id_due_date",
        "tasks",
        ["organization_id", "due_date"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_tasks_organization_id_related",
        "tasks",
        ["organization_id", "related_entity_type", "related_entity_id"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "attachments",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "ACTIVE", "QUARANTINED", name="attachment_status", schema="platform"
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 52428800",
            name=op.f("ck_attachments_size_bytes_within_limit"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_attachments_storage_key")),
        schema="platform",
    )
    op.create_index(
        op.f("ix_attachments_deleted_at"),
        "attachments",
        ["deleted_at"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        op.f("ix_attachments_organization_id"),
        "attachments",
        ["organization_id"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_attachments_organization_id_created_at",
        "attachments",
        ["organization_id", "created_at"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_attachments_organization_id_entity",
        "attachments",
        ["organization_id", "entity_type", "entity_id"],
        unique=False,
        schema="platform",
    )
    op.create_table(
        "organizations",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE", "SUSPENDED", "ARCHIVED", name="organization_status", schema="platform"
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        schema="platform",
    )
    op.create_index(
        op.f("ix_organizations_deleted_at"),
        "organizations",
        ["deleted_at"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        op.f("ix_organizations_slug"), "organizations", ["slug"], unique=True, schema="platform"
    )
    op.create_table(
        "permissions",
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column(
            "action",
            sa.Enum(
                "VIEW",
                "CREATE",
                "EDIT",
                "DELETE",
                "EXPORT",
                "ADMIN",
                name="permission_action",
                schema="platform",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permissions")),
        sa.UniqueConstraint("module", "action", name="uq_permissions_module_action"),
        schema="platform",
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "DISABLED", "PENDING", name="user_status", schema="platform"),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "tokens_valid_from",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        schema="platform",
    )
    op.create_index(
        op.f("ix_users_deleted_at"), "users", ["deleted_at"], unique=False, schema="platform"
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True, schema="platform")
    op.create_table(
        "campaigns",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "EMAIL",
                "WEBINAR",
                "SOCIAL_MEDIA",
                "EVENT",
                "ADVERTISEMENT",
                name="campaign_type",
                schema="crm",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PLANNING",
                "ACTIVE",
                "PAUSED",
                "COMPLETED",
                "CANCELLED",
                name="campaign_status",
                schema="crm",
            ),
            server_default="PLANNING",
            nullable=False,
        ),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("budget", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("expected_revenue", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("target_audience", sa.String(length=255), nullable=True),
        sa.Column("lead_source_id", sa.Uuid(), nullable=True),
        sa.Column("products", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("leads_generated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("opportunities_generated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conversion_rate", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("roi", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name=op.f("ck_campaigns_end_date_after_start_date"),
        ),
        sa.ForeignKeyConstraint(
            ["lead_source_id"],
            ["crm.lead_sources.id"],
            name=op.f("fk_campaigns_lead_source_id_lead_sources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_campaigns_deleted_at"), "campaigns", ["deleted_at"], unique=False, schema="crm"
    )
    op.create_index(
        op.f("ix_campaigns_organization_id"),
        "campaigns",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_campaigns_organization_id_deleted_at",
        "campaigns",
        ["organization_id", "deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_campaigns_organization_id_status",
        "campaigns",
        ["organization_id", "status"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "contacts",
        sa.Column("account_id", sa.Uuid(), nullable=True),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("mobile", sa.String(length=32), nullable=True),
        sa.Column("job_title", sa.String(length=160), nullable=True),
        sa.Column("department", sa.String(length=120), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("reporting_manager_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "INACTIVE", name="contact_status", schema="crm"),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column("preferred_communication", sa.String(length=64), nullable=True),
        sa.Column("linkedin_url", sa.String(length=512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("state", sa.String(length=120), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("country", sa.String(length=120), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 100)",
            name=op.f("ck_contacts_ai_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["crm.accounts.id"],
            name=op.f("fk_contacts_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_contacts_deleted_at"), "contacts", ["deleted_at"], unique=False, schema="crm"
    )
    op.create_index(
        op.f("ix_contacts_organization_id"),
        "contacts",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_contacts_organization_id_account_id",
        "contacts",
        ["organization_id", "account_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_contacts_organization_id_deleted_at",
        "contacts",
        ["organization_id", "deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_contacts_organization_id_email",
        "contacts",
        ["organization_id", "email"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_contacts_organization_id_owner_id",
        "contacts",
        ["organization_id", "owner_id"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "meetings",
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "meeting_type",
            sa.Enum("IN_PERSON", "VIDEO", "PHONE", name="meeting_type", schema="crm"),
            nullable=False,
        ),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("meeting_link", sa.String(length=1024), nullable=True),
        sa.Column("agenda", sa.Text(), nullable=True),
        sa.Column("reminder_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "internal_participant_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["crm.activities.id"],
            name=op.f("fk_meetings_activity_id_activities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meetings")),
        sa.UniqueConstraint("activity_id", name=op.f("uq_meetings_activity_id")),
        schema="crm",
    )
    op.create_table(
        "pipeline_stages",
        sa.Column("pipeline_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("default_probability", sa.Integer(), nullable=True),
        sa.Column("is_won", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_lost", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "NOT (is_won AND is_lost)", name=op.f("ck_pipeline_stages_not_both_won_and_lost")
        ),
        sa.CheckConstraint(
            "default_probability IS NULL OR (default_probability >= 0 AND default_probability <= 100)",
            name=op.f("ck_pipeline_stages_default_probability_range"),
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["crm.pipelines.id"],
            name=op.f("fk_pipeline_stages_pipeline_id_pipelines"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_stages")),
        sa.UniqueConstraint("pipeline_id", "name", name="uq_pipeline_stages_pipeline_id_name"),
        schema="crm",
    )
    op.create_index(
        op.f("ix_pipeline_stages_deleted_at"),
        "pipeline_stages",
        ["deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        op.f("ix_pipeline_stages_organization_id"),
        "pipeline_stages",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_pipeline_stages_pipeline_id_sort_order",
        "pipeline_stages",
        ["pipeline_id", "sort_order"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "organization_memberships",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "INVITED", "SUSPENDED", name="membership_status", schema="platform"),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["platform.organizations.id"],
            name=op.f("fk_organization_memberships_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform.users.id"],
            name=op.f("fk_organization_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_memberships")),
        sa.UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_memberships_organization_id_user_id"
        ),
        schema="platform",
    )
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
        unique=False,
        schema="platform",
    )
    op.create_index(
        "ix_organization_memberships_user_id",
        "organization_memberships",
        ["user_id"],
        unique=False,
        schema="platform",
    )
    op.create_table(
        "roles",
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["platform.organizations.id"],
            name=op.f("fk_roles_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("organization_id", "name", name="uq_roles_organization_id_name"),
        schema="platform",
    )
    op.create_index(
        "ix_roles_organization_id", "roles", ["organization_id"], unique=False, schema="platform"
    )
    op.create_table(
        "sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform.users.id"],
            name=op.f("fk_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        schema="platform",
    )
    op.create_index(
        "ix_sessions_family_id", "sessions", ["family_id"], unique=False, schema="platform"
    )
    op.create_index(
        "ix_sessions_refresh_token_hash",
        "sessions",
        ["refresh_token_hash"],
        unique=True,
        schema="platform",
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False, schema="platform")
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("avatar_url", sa.String(length=2048), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="UTC", nullable=False),
        sa.Column("locale", sa.String(length=16), server_default="en", nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["platform.users.id"],
            name=op.f("fk_user_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_profiles_user_id")),
        schema="platform",
    )
    op.create_table(
        "campaign_members",
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column(
            "entity_type",
            sa.Enum("LEAD", "CONTACT", name="campaign_member_type", schema="crm"),
            nullable=False,
        ),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["crm.campaigns.id"],
            name=op.f("fk_campaign_members_campaign_id_campaigns"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaign_members")),
        sa.UniqueConstraint(
            "campaign_id",
            "entity_type",
            "entity_id",
            name="uq_campaign_members_campaign_id_entity_type_entity_id",
        ),
        schema="crm",
    )
    op.create_index(
        op.f("ix_campaign_members_organization_id"),
        "campaign_members",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_campaign_members_organization_id_campaign_id",
        "campaign_members",
        ["organization_id", "campaign_id"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "leads",
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("lead_source_id", sa.Uuid(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "NEW",
                "CONTACTED",
                "QUALIFIED",
                "PROPOSAL_SENT",
                "NEGOTIATION",
                "CONVERTED",
                "LOST",
                name="lead_status",
                schema="crm",
            ),
            server_default="NEW",
            nullable=False,
        ),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column(
            "priority",
            sa.Enum("HIGH", "MEDIUM", "LOW", name="crm_priority", schema="crm"),
            nullable=True,
        ),
        sa.Column("expected_deal_size", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("company_size", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_account_id", sa.Uuid(), nullable=True),
        sa.Column("converted_contact_id", sa.Uuid(), nullable=True),
        sa.Column("converted_opportunity_id", sa.Uuid(), nullable=True),
        sa.Column("campaign_id", sa.Uuid(), nullable=True),
        sa.Column("lost_reason", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 100)",
            name=op.f("ck_leads_ai_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["crm.campaigns.id"],
            name=op.f("fk_leads_campaign_id_campaigns"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["converted_account_id"],
            ["crm.accounts.id"],
            name=op.f("fk_leads_converted_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["converted_contact_id"],
            ["crm.contacts.id"],
            name=op.f("fk_leads_converted_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lead_source_id"],
            ["crm.lead_sources.id"],
            name=op.f("fk_leads_lead_source_id_lead_sources"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_leads_deleted_at"), "leads", ["deleted_at"], unique=False, schema="crm"
    )
    op.create_index(
        op.f("ix_leads_organization_id"), "leads", ["organization_id"], unique=False, schema="crm"
    )
    op.create_index(
        "ix_leads_organization_id_created_at",
        "leads",
        ["organization_id", "created_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_leads_organization_id_deleted_at",
        "leads",
        ["organization_id", "deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_leads_organization_id_email",
        "leads",
        ["organization_id", "email"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_leads_organization_id_owner_id",
        "leads",
        ["organization_id", "owner_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_leads_organization_id_status",
        "leads",
        ["organization_id", "status"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "opportunities",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("primary_contact_id", sa.Uuid(), nullable=True),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("stage_id", sa.Uuid(), nullable=False),
        sa.Column("deal_value", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("win_probability", sa.Integer(), nullable=True),
        sa.Column("expected_close_date", sa.Date(), nullable=True),
        sa.Column("health_score", sa.Integer(), nullable=True),
        sa.Column("forecast_category", sa.String(length=64), nullable=True),
        sa.Column("competitor", sa.String(length=160), nullable=True),
        sa.Column("lead_source_id", sa.Uuid(), nullable=True),
        sa.Column("products", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("won_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("loss_reason", sa.String(length=255), nullable=True),
        sa.Column("win_reason", sa.String(length=255), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "deal_value IS NULL OR deal_value >= 0",
            name=op.f("ck_opportunities_deal_value_non_negative"),
        ),
        sa.CheckConstraint(
            "win_probability IS NULL OR (win_probability >= 0 AND win_probability <= 100)",
            name=op.f("ck_opportunities_win_probability_range"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["crm.accounts.id"],
            name=op.f("fk_opportunities_account_id_accounts"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lead_source_id"],
            ["crm.lead_sources.id"],
            name=op.f("fk_opportunities_lead_source_id_lead_sources"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["primary_contact_id"],
            ["crm.contacts.id"],
            name=op.f("fk_opportunities_primary_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["crm.pipeline_stages.id"],
            name=op.f("fk_opportunities_stage_id_pipeline_stages"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
        schema="crm",
    )
    op.create_index(
        op.f("ix_opportunities_deleted_at"),
        "opportunities",
        ["deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        op.f("ix_opportunities_organization_id"),
        "opportunities",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_opportunities_organization_id_account_id",
        "opportunities",
        ["organization_id", "account_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_opportunities_organization_id_deleted_at",
        "opportunities",
        ["organization_id", "deleted_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_opportunities_organization_id_expected_close_date",
        "opportunities",
        ["organization_id", "expected_close_date"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_opportunities_organization_id_owner_id",
        "opportunities",
        ["organization_id", "owner_id"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        "ix_opportunities_organization_id_stage_id",
        "opportunities",
        ["organization_id", "stage_id"],
        unique=False,
        schema="crm",
    )
    op.create_table(
        "membership_roles",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["platform.organization_memberships.id"],
            name=op.f("fk_membership_roles_membership_id_organization_memberships"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["platform.roles.id"],
            name=op.f("fk_membership_roles_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("membership_id", "role_id", name="pk_membership_roles"),
        schema="platform",
    )
    op.create_index(
        "ix_membership_roles_membership_id",
        "membership_roles",
        ["membership_id"],
        unique=False,
        schema="platform",
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), nullable=False),
        sa.Column("permission_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["platform.permissions.id"],
            name=op.f("fk_role_permissions_permission_id_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["platform.roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
        schema="platform",
    )
    op.create_table(
        "opportunity_stage_history",
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("from_stage_id", sa.Uuid(), nullable=True),
        sa.Column("to_stage_id", sa.Uuid(), nullable=False),
        sa.Column("changed_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("note", sa.String(length=512), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["crm.opportunities.id"],
            name=op.f("fk_opportunity_stage_history_opportunity_id_opportunities"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunity_stage_history")),
        schema="crm",
    )
    op.create_index(
        "ix_opportunity_stage_history_opportunity_id_changed_at",
        "opportunity_stage_history",
        ["opportunity_id", "changed_at"],
        unique=False,
        schema="crm",
    )
    op.create_index(
        op.f("ix_opportunity_stage_history_organization_id"),
        "opportunity_stage_history",
        ["organization_id"],
        unique=False,
        schema="crm",
    )
    # NOTE: autogenerate proposed dropping platform.tenant_isolation_probe here
    # because it has no model. It is retained deliberately: the Phase 0 RLS gate
    # suite (tests/integration/test_tenant_isolation.py) asserts against it, and
    # that suite is non-waivable. Retiring the probe is a separate change that
    # must move those assertions onto a real table first.

    # --- Row-Level Security -------------------------------------------------
    _enable_tenant_rls(op.get_bind())

    # --- Reference data -----------------------------------------------------
    _seed_permissions_and_system_roles(op.get_bind())


def downgrade() -> None:
    _drop_seed_data(op.get_bind())
    _disable_tenant_rls(op.get_bind())

    op.drop_index(
        op.f("ix_opportunity_stage_history_organization_id"),
        table_name="opportunity_stage_history",
        schema="crm",
    )
    op.drop_index(
        "ix_opportunity_stage_history_opportunity_id_changed_at",
        table_name="opportunity_stage_history",
        schema="crm",
    )
    op.drop_table("opportunity_stage_history", schema="crm")
    op.drop_table("role_permissions", schema="platform")
    op.drop_index(
        "ix_membership_roles_membership_id", table_name="membership_roles", schema="platform"
    )
    op.drop_table("membership_roles", schema="platform")
    op.drop_index(
        "ix_opportunities_organization_id_stage_id", table_name="opportunities", schema="crm"
    )
    op.drop_index(
        "ix_opportunities_organization_id_owner_id", table_name="opportunities", schema="crm"
    )
    op.drop_index(
        "ix_opportunities_organization_id_expected_close_date",
        table_name="opportunities",
        schema="crm",
    )
    op.drop_index(
        "ix_opportunities_organization_id_deleted_at", table_name="opportunities", schema="crm"
    )
    op.drop_index(
        "ix_opportunities_organization_id_account_id", table_name="opportunities", schema="crm"
    )
    op.drop_index(
        op.f("ix_opportunities_organization_id"), table_name="opportunities", schema="crm"
    )
    op.drop_index(op.f("ix_opportunities_deleted_at"), table_name="opportunities", schema="crm")
    op.drop_table("opportunities", schema="crm")
    op.drop_index("ix_leads_organization_id_status", table_name="leads", schema="crm")
    op.drop_index("ix_leads_organization_id_owner_id", table_name="leads", schema="crm")
    op.drop_index("ix_leads_organization_id_email", table_name="leads", schema="crm")
    op.drop_index("ix_leads_organization_id_deleted_at", table_name="leads", schema="crm")
    op.drop_index("ix_leads_organization_id_created_at", table_name="leads", schema="crm")
    op.drop_index(op.f("ix_leads_organization_id"), table_name="leads", schema="crm")
    op.drop_index(op.f("ix_leads_deleted_at"), table_name="leads", schema="crm")
    op.drop_table("leads", schema="crm")
    op.drop_index(
        "ix_campaign_members_organization_id_campaign_id",
        table_name="campaign_members",
        schema="crm",
    )
    op.drop_index(
        op.f("ix_campaign_members_organization_id"), table_name="campaign_members", schema="crm"
    )
    op.drop_table("campaign_members", schema="crm")
    op.drop_table("user_profiles", schema="platform")
    op.drop_index("ix_sessions_user_id", table_name="sessions", schema="platform")
    op.drop_index("ix_sessions_refresh_token_hash", table_name="sessions", schema="platform")
    op.drop_index("ix_sessions_family_id", table_name="sessions", schema="platform")
    op.drop_table("sessions", schema="platform")
    op.drop_index("ix_roles_organization_id", table_name="roles", schema="platform")
    op.drop_table("roles", schema="platform")
    op.drop_index(
        "ix_organization_memberships_user_id",
        table_name="organization_memberships",
        schema="platform",
    )
    op.drop_index(
        "ix_organization_memberships_organization_id",
        table_name="organization_memberships",
        schema="platform",
    )
    op.drop_table("organization_memberships", schema="platform")
    op.drop_index(
        "ix_pipeline_stages_pipeline_id_sort_order", table_name="pipeline_stages", schema="crm"
    )
    op.drop_index(
        op.f("ix_pipeline_stages_organization_id"), table_name="pipeline_stages", schema="crm"
    )
    op.drop_index(op.f("ix_pipeline_stages_deleted_at"), table_name="pipeline_stages", schema="crm")
    op.drop_table("pipeline_stages", schema="crm")
    op.drop_table("meetings", schema="crm")
    op.drop_index("ix_contacts_organization_id_owner_id", table_name="contacts", schema="crm")
    op.drop_index("ix_contacts_organization_id_email", table_name="contacts", schema="crm")
    op.drop_index("ix_contacts_organization_id_deleted_at", table_name="contacts", schema="crm")
    op.drop_index("ix_contacts_organization_id_account_id", table_name="contacts", schema="crm")
    op.drop_index(op.f("ix_contacts_organization_id"), table_name="contacts", schema="crm")
    op.drop_index(op.f("ix_contacts_deleted_at"), table_name="contacts", schema="crm")
    op.drop_table("contacts", schema="crm")
    op.drop_index("ix_campaigns_organization_id_status", table_name="campaigns", schema="crm")
    op.drop_index("ix_campaigns_organization_id_deleted_at", table_name="campaigns", schema="crm")
    op.drop_index(op.f("ix_campaigns_organization_id"), table_name="campaigns", schema="crm")
    op.drop_index(op.f("ix_campaigns_deleted_at"), table_name="campaigns", schema="crm")
    op.drop_table("campaigns", schema="crm")
    op.drop_index(op.f("ix_users_email"), table_name="users", schema="platform")
    op.drop_index(op.f("ix_users_deleted_at"), table_name="users", schema="platform")
    op.drop_table("users", schema="platform")
    op.drop_table("permissions", schema="platform")
    op.drop_index(op.f("ix_organizations_slug"), table_name="organizations", schema="platform")
    op.drop_index(
        op.f("ix_organizations_deleted_at"), table_name="organizations", schema="platform"
    )
    op.drop_table("organizations", schema="platform")
    op.drop_index(
        "ix_attachments_organization_id_entity", table_name="attachments", schema="platform"
    )
    op.drop_index(
        "ix_attachments_organization_id_created_at", table_name="attachments", schema="platform"
    )
    op.drop_index(
        op.f("ix_attachments_organization_id"), table_name="attachments", schema="platform"
    )
    op.drop_index(op.f("ix_attachments_deleted_at"), table_name="attachments", schema="platform")
    op.drop_table("attachments", schema="platform")
    op.drop_index("ix_tasks_organization_id_related", table_name="tasks", schema="crm")
    op.drop_index("ix_tasks_organization_id_due_date", table_name="tasks", schema="crm")
    op.drop_index("ix_tasks_organization_id_deleted_at", table_name="tasks", schema="crm")
    op.drop_index(
        "ix_tasks_organization_id_assigned_to_id_status", table_name="tasks", schema="crm"
    )
    op.drop_index(op.f("ix_tasks_organization_id"), table_name="tasks", schema="crm")
    op.drop_index(op.f("ix_tasks_deleted_at"), table_name="tasks", schema="crm")
    op.drop_table("tasks", schema="crm")
    op.drop_index(op.f("ix_pipelines_organization_id"), table_name="pipelines", schema="crm")
    op.drop_index(op.f("ix_pipelines_deleted_at"), table_name="pipelines", schema="crm")
    op.drop_table("pipelines", schema="crm")
    op.drop_index("ix_notes_organization_id_related", table_name="notes", schema="crm")
    op.drop_index("ix_notes_organization_id_deleted_at", table_name="notes", schema="crm")
    op.drop_index(op.f("ix_notes_organization_id"), table_name="notes", schema="crm")
    op.drop_index(op.f("ix_notes_deleted_at"), table_name="notes", schema="crm")
    op.drop_table("notes", schema="crm")
    op.drop_index("ix_lead_sources_organization_id_status", table_name="lead_sources", schema="crm")
    op.drop_index(op.f("ix_lead_sources_organization_id"), table_name="lead_sources", schema="crm")
    op.drop_index(op.f("ix_lead_sources_deleted_at"), table_name="lead_sources", schema="crm")
    op.drop_table("lead_sources", schema="crm")
    op.drop_index(
        "ix_activities_organization_id_type_status", table_name="activities", schema="crm"
    )
    op.drop_index("ix_activities_organization_id_related", table_name="activities", schema="crm")
    op.drop_index("ix_activities_organization_id_due_date", table_name="activities", schema="crm")
    op.drop_index("ix_activities_organization_id_deleted_at", table_name="activities", schema="crm")
    op.drop_index(op.f("ix_activities_organization_id"), table_name="activities", schema="crm")
    op.drop_index(op.f("ix_activities_deleted_at"), table_name="activities", schema="crm")
    op.drop_table("activities", schema="crm")
    op.drop_index("ix_accounts_organization_id_status", table_name="accounts", schema="crm")
    op.drop_index("ix_accounts_organization_id_owner_id", table_name="accounts", schema="crm")
    op.drop_index("ix_accounts_organization_id_name", table_name="accounts", schema="crm")
    op.drop_index("ix_accounts_organization_id_deleted_at", table_name="accounts", schema="crm")
    op.drop_index(op.f("ix_accounts_organization_id"), table_name="accounts", schema="crm")
    op.drop_index(op.f("ix_accounts_deleted_at"), table_name="accounts", schema="crm")
    op.drop_table("accounts", schema="crm")

    # PostgreSQL keeps native enum types after their tables are dropped; without
    # this a re-upgrade fails with "type already exists".
    _drop_enum_types(op.get_bind())
