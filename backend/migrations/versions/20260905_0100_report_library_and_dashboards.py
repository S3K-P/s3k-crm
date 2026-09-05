"""The saved-report library and configurable dashboards.

Revision ID: 20260905_0100
Revises: 20260903_0100
Create Date: 2026-09-05 01:00:00.000000

Phase B shipped a fixed catalogue of nine reports. This adds the layer people
actually work in: name a report, file it in a folder, share it, and arrange
several of them on a dashboard.

**Four tenant-scoped tables, all with the standard fail-closed policy.** Two
of them — ``dashboard_components`` and ``saved_reports`` — carry foreign keys
to rows in the same tenant, and RLS does not check that a referenced row is in
your organization. The service resolves every parent through the tenant-scoped
repository before writing the child, which is where that guarantee actually
comes from; the policies here stop a *read* crossing tenants, which is the
half RLS is for.

**No result is ever stored.** A saved report holds a catalogue key and a
period; running it recomputes against the runner's own record visibility. That
is what makes ``SHARED`` safe to offer — see ``reports/models.py``.

**The new ``reports`` permission module.** Running a report was, and remains,
authorized against the module the report reads: a pipeline report needs
``opportunities.VIEW``. What ``reports.*`` governs is the saved object's
lifecycle — naming, filing, sharing, deleting. The two are independent on
purpose, and holding one grants nothing under the other. Granted here the same
way revision ``20260824_0100`` granted ``teams``: to the ``organization_id IS
NULL`` role templates, which every organization's memberships point at.

``VIEW_TEAM`` is inserted for the module but granted to nobody except Admin
(who holds the catalogue by wildcard, an invariant
``test_the_admin_role_grants_the_whole_catalogue`` pins). Manager already
holds ``VIEW_ALL``, which is strictly wider; giving it to User would widen
every rep's reach as a side effect of a migration rather than as an
administrator's decision. That is the reasoning CR15 established and this
follows it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260905_0100"
down_revision: str | None = "20260903_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: The tables this revision creates, in dependency order. Reversed on the way
#: down so a child is always gone before its parent.
_TABLES: tuple[str, ...] = (
    "report_folders",
    "saved_reports",
    "dashboards",
    "dashboard_components",
)

#: Pinned snapshot of the action vocabulary as of this revision, for the same
#: reason revision ``8224845a67ac`` pins its own: importing the live catalogue
#: makes a from-zero migration run break the day somebody adds an action.
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

_MANAGER_ACTIONS: tuple[str, ...] = (
    "VIEW",
    "VIEW_ALL",
    "CREATE",
    "EDIT",
    "DELETE",
    "EXPORT",
)

_USER_ACTIONS: tuple[str, ...] = ("VIEW", "CREATE", "EDIT")

_MODULE = "reports"


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
    # ``share_scope`` is created once and referenced by two tables, so both
    # column definitions below use ``create_type=False``. Letting SQLAlchemy
    # emit CREATE TYPE per column would fail on the second one.
    sa.Enum("PRIVATE", "SHARED", name="share_scope", schema=CRM).create(connection, checkfirst=True)
    sa.Enum(
        "ALL_TIME",
        "TODAY",
        "LAST_7_DAYS",
        "LAST_30_DAYS",
        "LAST_90_DAYS",
        "THIS_MONTH",
        "LAST_MONTH",
        "THIS_QUARTER",
        "LAST_QUARTER",
        "THIS_YEAR",
        "CUSTOM",
        name="report_period",
        schema=CRM,
    ).create(connection, checkfirst=True)
    sa.Enum("CHART", "TABLE", "METRIC", name="component_display", schema=CRM).create(
        connection, checkfirst=True
    )

    share_scope = postgresql.ENUM(
        "PRIVATE", "SHARED", name="share_scope", schema=CRM, create_type=False
    )
    report_period = postgresql.ENUM(
        "ALL_TIME",
        "TODAY",
        "LAST_7_DAYS",
        "LAST_30_DAYS",
        "LAST_90_DAYS",
        "THIS_MONTH",
        "LAST_MONTH",
        "THIS_QUARTER",
        "LAST_QUARTER",
        "THIS_YEAR",
        "CUSTOM",
        name="report_period",
        schema=CRM,
        create_type=False,
    )
    component_display = postgresql.ENUM(
        "CHART", "TABLE", "METRIC", name="component_display", schema=CRM, create_type=False
    )

    # --- Folders -----------------------------------------------------------

    op.create_table(
        "report_folders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=True),
        *_timestamps(),
        schema=CRM,
    )
    # Partial unique: a deleted folder's name is free again, which matters
    # because deletion here is a soft delete and the row never leaves.
    op.create_index(
        "uq_report_folders_organization_id_name",
        "report_folders",
        ["organization_id", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- Saved reports -----------------------------------------------------

    op.create_table(
        "saved_reports",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_report_key", sa.String(length=64), nullable=False),
        sa.Column(
            "folder_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.report_folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("period", report_period, nullable=False, server_default="ALL_TIME"),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("visibility", share_scope, nullable=False, server_default="PRIVATE"),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "uq_saved_reports_organization_id_name",
        "saved_reports",
        ["organization_id", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_saved_reports_organization_id_folder_id",
        "saved_reports",
        ["organization_id", "folder_id"],
        schema=CRM,
    )

    # --- Dashboards --------------------------------------------------------

    op.create_table(
        "dashboards",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("visibility", share_scope, nullable=False, server_default="PRIVATE"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "uq_dashboards_organization_id_name",
        "dashboards",
        ["organization_id", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "dashboard_components",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "dashboard_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.dashboards.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # RESTRICT, so a saved report cannot vanish from under a tile. The
        # service converts the resulting constraint into a 409 that names the
        # dashboards using it, rather than letting an IntegrityError surface.
        sa.Column(
            "saved_report_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.saved_reports.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column("display", component_display, nullable=False, server_default="CHART"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="6"),
        *_timestamps(),
        sa.CheckConstraint("width BETWEEN 1 AND 12", name="ck_dashboard_components_width"),
        sa.CheckConstraint("sort_order >= 0", name="ck_dashboard_components_sort_order"),
        schema=CRM,
    )
    op.create_index(
        "ix_dashboard_components_organization_id_dashboard_id",
        "dashboard_components",
        ["organization_id", "dashboard_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_dashboard_components_organization_id_saved_report_id",
        "dashboard_components",
        ["organization_id", "saved_report_id"],
        schema=CRM,
    )

    # --- Row-Level Security ------------------------------------------------

    for table in _TABLES:
        enable_rls(connection, table, schema=CRM)

    # --- The `reports` permission module ------------------------------------

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
                "description": f"{action} saved reports and report folders",
            },
        )

    _grant("Admin", _ACTIONS, connection)
    _grant("Manager", _MANAGER_ACTIONS, connection)
    _grant("User", _USER_ACTIONS, connection)


def _grant(role: str, actions: tuple[str, ...], connection: sa.Connection) -> None:
    """Grant ``reports.<action>`` to a system role template.

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

    op.drop_table("dashboard_components", schema=CRM)
    op.drop_table("dashboards", schema=CRM)
    op.drop_table("saved_reports", schema=CRM)
    op.drop_table("report_folders", schema=CRM)

    for enum_name in ("component_display", "report_period", "share_scope"):
        sa.Enum(name=enum_name, schema=CRM).drop(connection, checkfirst=True)
