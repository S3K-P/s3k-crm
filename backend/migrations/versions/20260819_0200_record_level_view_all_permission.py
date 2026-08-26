"""Add the VIEW_ALL permission and grant it to Admin and Manager.

Revision ID: 20260819_0200
Revises: 20260819_0100
Create Date: 2026-08-19 02:00:00.000000

Record-level authorization (ADR-010, `P1-W07-BE-04` / `P2-W10-BE-06`) needs a
way to say "may read records somebody else owns" that is *data*, not a role
name compiled into a query. ``VIEW`` alone could not express it: every role
that could read a module could read all of it.

After this migration:

* **Admin** holds every permission by wildcard, so it gains ``VIEW_ALL``
  everywhere automatically.
* **Manager** gains ``VIEW_ALL`` on the CRM modules — a manager runs the
  team's pipeline.
* **User** does not, which is the point: a rep's reads narrow to the records
  they own.

Tenant-defined roles are left untouched. An organization that cloned a role
before this ran keeps exactly the permissions it had, so nobody's access
silently widens; an administrator grants ``VIEW_ALL`` deliberately.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260819_0200"
down_revision: str | None = "20260819_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The module list is pinned rather than imported from
# `app.platform.authorization.catalog`. That import is what broke revision
# 8224845a67ac on a from-zero run: a migration is a snapshot of history, and
# reading live code means a later edit silently rewrites what an old revision
# does. A module added to the catalogue later needs its own migration.

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

#: CRM modules only — what Manager runs a pipeline over.
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

#: role name -> modules it gains ``VIEW_ALL`` on. ``User`` is absent on
#: purpose: a rep reading only their own records is the point of the change.
_GRANTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Admin", _MODULES),
    ("Manager", _CRM_MODULES),
)


def upgrade() -> None:
    connection = op.get_bind()

    # ADD VALUE IF NOT EXISTS is transaction-safe on PG 12+, which is what
    # Alembic's default transactional DDL gives us.
    op.execute(
        sa.text(
            "ALTER TYPE platform.permission_action ADD VALUE IF NOT EXISTS 'VIEW_ALL' AFTER 'VIEW'"
        )
    )
    # The new label is not visible to later statements in the *same*
    # transaction on some versions, so commit the type change before it is
    # used as a value below.
    connection.execute(sa.text("COMMIT"))

    # One `module.VIEW_ALL` row per module.
    for module in _MODULES:
        connection.execute(
            sa.text(
                "INSERT INTO platform.permissions (module, action, description) "
                "VALUES (:module, CAST('VIEW_ALL' AS platform.permission_action), :description) "
                "ON CONFLICT (module, action) DO NOTHING"
            ),
            {
                "module": module,
                "description": f"Read {module} records owned by anyone in the organization",
            },
        )

    # Grant it to the shared system templates only (organization_id IS NULL).
    # Nothing else about those roles is touched, so a re-run cannot widen a
    # grant that was deliberately revoked.
    for role_name, modules in _GRANTS:
        for module in modules:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.role_permissions (role_id, permission_id) "
                    "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
                    "WHERE r.organization_id IS NULL AND r.name = :role "
                    "  AND p.module = :module "
                    "  AND p.action = CAST('VIEW_ALL' AS platform.permission_action) "
                    "ON CONFLICT (role_id, permission_id) DO NOTHING"
                ),
                {"role": role_name, "module": module},
            )


def downgrade() -> None:
    # The grants and the permission rows are removed; the enum *label* stays.
    # PostgreSQL cannot drop a value from an enum type, and recreating the type
    # would require rewriting every dependent column — far more destructive
    # than leaving an unused label behind.
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM platform.role_permissions rp USING platform.permissions p "
            "WHERE rp.permission_id = p.id AND p.action = 'VIEW_ALL'"
        )
    )
    connection.execute(
        sa.text("DELETE FROM platform.permissions WHERE action = 'VIEW_ALL'")
    )
