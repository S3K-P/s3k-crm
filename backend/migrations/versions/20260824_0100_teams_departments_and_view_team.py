"""Teams, departments, membership, and the VIEW_TEAM permission.

Revision ID: 20260824_0100
Revises: 20260821_0100
Create Date: 2026-08-24 01:00:00.000000

Closes B02. Record-level visibility shipped as *owner vs organization-wide*
only (CR07) because no ``Team`` existed for a team predicate to resolve
against. This adds the three tables doc 04 specifies and the permission that
makes them mean something.

After this migration:

* ``platform.departments`` and ``platform.teams`` are tenant-scoped with RLS
  enabled *and* forced, like every other table holding customer data.
* ``platform.team_memberships`` carries no ``organization_id`` — a membership
  is reached only through its team. Its RLS policy is therefore an ``EXISTS``
  over ``teams``, which isolates it by the tenant of the team it points at.
  Duplicating the discriminator on the join would create a second place for it
  to disagree with the first.
* ``VIEW_TEAM`` exists on every module, granted to **no** system role. It is
  the middle rung between ``VIEW`` and ``VIEW_ALL``, and an administrator
  grants it deliberately. Auto-granting it to *User* would silently widen
  every rep's reach the moment this ran, which is exactly the kind of change
  that must be a decision rather than a migration side effect.
* A ``teams`` permission module is seeded so team administration can be gated
  without borrowing another module's permission.

The module and action lists below are **pinned**, not imported from
``app.platform.authorization.catalog``. Reading live code from a migration is
what broke revision ``8224845a67ac`` on a from-zero run: a migration is a
snapshot of history, and a later catalogue edit must not rewrite what an old
revision does.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_rls, enable_rls

revision: str = "20260824_0100"
down_revision: str | None = "20260821_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"

#: Every module that existed when this revision was written, plus ``teams``.
_MODULES: tuple[str, ...] = (
    "users",
    "organizations",
    "roles",
    "audit",
    "teams",
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

#: The standard action set, matching revision ``8224845a67ac``.
_ACTIONS: tuple[str, ...] = ("VIEW", "CREATE", "EDIT", "DELETE", "EXPORT", "ADMIN")


def upgrade() -> None:
    connection = op.get_bind()

    # --- Tables ------------------------------------------------------------
    op.create_table(
        "departments",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
        schema=PLATFORM,
    )
    op.create_index(
        op.f("ix_departments_organization_id"),
        "departments",
        ["organization_id"],
        unique=False,
        schema=PLATFORM,
    )
    op.create_index(
        op.f("ix_departments_deleted_at"),
        "departments",
        ["deleted_at"],
        unique=False,
        schema=PLATFORM,
    )
    op.create_index(
        "uq_departments_organization_id_name_live",
        "departments",
        ["organization_id", "name"],
        unique=True,
        schema=PLATFORM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "teams",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("department_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        # RESTRICT: deleting a department must not silently take its teams —
        # and with them every member's visibility — with it.
        sa.ForeignKeyConstraint(
            ["department_id"],
            [f"{PLATFORM}.departments.id"],
            name="fk_teams_department_id_departments",
            ondelete="RESTRICT",
        ),
        schema=PLATFORM,
    )
    op.create_index(
        op.f("ix_teams_organization_id"),
        "teams",
        ["organization_id"],
        unique=False,
        schema=PLATFORM,
    )
    op.create_index(
        op.f("ix_teams_deleted_at"), "teams", ["deleted_at"], unique=False, schema=PLATFORM
    )
    op.create_index(
        "ix_teams_department_id", "teams", ["department_id"], unique=False, schema=PLATFORM
    )
    op.create_index(
        "uq_teams_organization_id_name_live",
        "teams",
        ["organization_id", "name"],
        unique=True,
        schema=PLATFORM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "team_memberships",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("team_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_memberships")),
        sa.ForeignKeyConstraint(
            ["team_id"],
            [f"{PLATFORM}.teams.id"],
            name="fk_team_memberships_team_id_teams",
            ondelete="CASCADE",
        ),
        schema=PLATFORM,
    )
    op.create_index(
        "uq_team_memberships_team_id_user_id",
        "team_memberships",
        ["team_id", "user_id"],
        unique=True,
        schema=PLATFORM,
    )
    op.create_index(
        "ix_team_memberships_user_id",
        "team_memberships",
        ["user_id"],
        unique=False,
        schema=PLATFORM,
    )

    # --- Row-Level Security ------------------------------------------------
    enable_rls(connection, "departments", schema=PLATFORM)
    enable_rls(connection, "teams", schema=PLATFORM)

    # The join has no organization_id of its own, so its policy borrows the
    # tenant of the team it points at. Written as EXISTS rather than a column
    # comparison because there is no column here to compare.
    op.execute(
        sa.text(
            "ALTER TABLE platform.team_memberships ENABLE ROW LEVEL SECURITY"
        )
    )
    op.execute(
        sa.text("ALTER TABLE platform.team_memberships FORCE ROW LEVEL SECURITY")
    )
    # Fully literal: no interpolation, so nothing here can be influenced by
    # anything outside this file.
    op.execute(
        sa.text(
            "CREATE POLICY team_memberships_tenant_isolation "
            "ON platform.team_memberships "
            "USING (EXISTS (SELECT 1 FROM platform.teams t "
            "  WHERE t.id = team_id "
            "    AND t.organization_id = NULLIF("
            "      current_setting('app.current_org_id', true), '')::uuid)) "
            "WITH CHECK (EXISTS (SELECT 1 FROM platform.teams t "
            "  WHERE t.id = team_id "
            "    AND t.organization_id = NULLIF("
            "      current_setting('app.current_org_id', true), '')::uuid))"
        )
    )

    # --- Permissions -------------------------------------------------------
    # ADD VALUE IF NOT EXISTS is transaction-safe on PG 12+. The new label is
    # not visible to later statements in the same transaction, so commit the
    # type change before using it as a value.
    op.execute(
        sa.text(
            "ALTER TYPE platform.permission_action "
            "ADD VALUE IF NOT EXISTS 'VIEW_TEAM' AFTER 'VIEW'"
        )
    )
    connection.execute(sa.text("COMMIT"))

    # The new `teams` module needs its standard actions.
    for action in _ACTIONS:
        connection.execute(
            sa.text(
                "INSERT INTO platform.permissions (module, action, description) "
                "VALUES ('teams', CAST(:action AS platform.permission_action), :description) "
                "ON CONFLICT (module, action) DO NOTHING"
            ),
            {"action": action, "description": f"{action} teams and departments"},
        )

    # VIEW_TEAM on every module, including the new one.
    for module in _MODULES:
        connection.execute(
            sa.text(
                "INSERT INTO platform.permissions (module, action, description) "
                "VALUES (:module, CAST('VIEW_TEAM' AS platform.permission_action), :description) "
                "ON CONFLICT (module, action) DO NOTHING"
            ),
            {
                "module": module,
                "description": f"Read {module} records owned by the caller's team-mates",
            },
        )

    # `teams` module grants for the system templates (organization_id IS NULL).
    # Admin administers teams; Manager reads the org chart; User gets nothing.
    #
    # VIEW_TEAM is granted to **Admin only**, and for a structural reason
    # rather than a permissions one: Admin is defined as the whole catalogue
    # (``SYSTEM_ROLES`` expresses it as a wildcard precisely so a newly added
    # module cannot silently leave administrators without access to it), and
    # ``test_the_admin_role_grants_the_whole_catalogue`` pins that invariant.
    # It widens nothing — Admin already holds VIEW_ALL, which is strictly
    # wider than VIEW_TEAM.
    #
    # Manager and User are deliberately left without it. Manager already holds
    # VIEW_ALL, so it would be redundant; giving it to User would widen every
    # rep's reach as a side effect of running a migration rather than as an
    # administrator's decision. See CR15.
    for action in _ACTIONS:
        connection.execute(
            sa.text(
                "INSERT INTO platform.role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
                "WHERE r.organization_id IS NULL AND r.name = 'Admin' "
                "  AND p.module = 'teams' "
                "  AND p.action = CAST(:action AS platform.permission_action) "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"action": action},
        )
    connection.execute(
        sa.text(
            "INSERT INTO platform.role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
            "WHERE r.organization_id IS NULL AND r.name = 'Manager' "
            "  AND p.module = 'teams' "
            "  AND p.action = CAST('VIEW' AS platform.permission_action) "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        )
    )
    # Admin holds every permission by wildcard elsewhere, but VIEW_ALL on the
    # new `teams` module has to be inserted and granted explicitly — revision
    # 20260819_0200 ran before this module existed.
    connection.execute(
        sa.text(
            "INSERT INTO platform.permissions (module, action, description) "
            "VALUES ('teams', CAST('VIEW_ALL' AS platform.permission_action), "
            "        'Read teams records owned by anyone in the organization') "
            "ON CONFLICT (module, action) DO NOTHING"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO platform.role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
            "WHERE r.organization_id IS NULL AND r.name = 'Admin' "
            "  AND p.module = 'teams' "
            "  AND p.action = CAST('VIEW_ALL' AS platform.permission_action) "
            "ON CONFLICT (role_id, permission_id) DO NOTHING"
        )
    )

    # Admin gets VIEW_TEAM everywhere, keeping the wildcard invariant intact.
    for module in _MODULES:
        connection.execute(
            sa.text(
                "INSERT INTO platform.role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
                "WHERE r.organization_id IS NULL AND r.name = 'Admin' "
                "  AND p.module = :module "
                "  AND p.action = CAST('VIEW_TEAM' AS platform.permission_action) "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"module": module},
        )


def downgrade() -> None:
    connection = op.get_bind()

    # Grants and permission rows go; the enum *label* stays. PostgreSQL cannot
    # drop a value from an enum type, and recreating it would mean rewriting
    # every dependent column — far more destructive than an unused label.
    connection.execute(
        sa.text(
            "DELETE FROM platform.role_permissions rp USING platform.permissions p "
            "WHERE rp.permission_id = p.id "
            "  AND (p.action = 'VIEW_TEAM' OR p.module = 'teams')"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM platform.permissions "
            "WHERE action = 'VIEW_TEAM' OR module = 'teams'"
        )
    )

    op.execute(
        sa.text(
            f"DROP POLICY IF EXISTS team_memberships_tenant_isolation "
            f"ON {PLATFORM}.team_memberships"
        )
    )
    op.drop_table("team_memberships", schema=PLATFORM)

    disable_rls(connection, "teams", schema=PLATFORM)
    op.drop_table("teams", schema=PLATFORM)

    disable_rls(connection, "departments", schema=PLATFORM)
    op.drop_table("departments", schema=PLATFORM)
