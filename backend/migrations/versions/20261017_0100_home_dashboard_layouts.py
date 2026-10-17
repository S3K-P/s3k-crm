"""Home dashboard layouts: a per-user, per-organization saved card order.

Revision ID: 20261017_0100
Revises: 20260924_0200
Create Date: 2026-10-17 01:00:00.000000

Backs the "Customize dashboard" feature on the CRM home page (``GET /crm/
dashboard/summary``'s fixed screen): which cards a user has shown, hidden and
in what order. **Not** related to ``crm.dashboards``/``crm.dashboard_components``
(the user-built report-dashboard "boards" feature) — this table is a personal
preference, nine booleans and a position, not CRM domain data.

It is still scoped to the organization a user set their layout up in, so it
carries ``organization_id`` and RLS exactly like every other tenant-scoped
table (ADR-007), the same way ``platform.teams`` and ``platform.departments``
do for the same reason.

``user_id`` is a real foreign key, ``ON DELETE CASCADE``, unlike the owner and
author columns CRM tables carry: a layout *is* that user's preference and has
no reason to survive them, so it goes when they do rather than being left
behind as a row pointing at nobody — the same rule ``platform.user_profiles``
and ``platform.sessions`` already follow for the same kind of column.

One row per user per organization: a partial or full history of past layouts
is not a feature here, so the unique index is plain rather than soft-delete
aware — there is no soft delete on this table at all. A user's PUT overwrites
their one row in place.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20261017_0100"
down_revision: str | None = "20260924_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "dashboard_layouts",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("cards", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dashboard_layouts")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{PLATFORM}.users.id"],
            name="fk_dashboard_layouts_user_id_users",
            ondelete="CASCADE",
        ),
        schema=PLATFORM,
    )
    op.create_index(
        op.f("ix_dashboard_layouts_organization_id"),
        "dashboard_layouts",
        ["organization_id"],
        unique=False,
        schema=PLATFORM,
    )
    op.create_index(
        "uq_dashboard_layouts_user_id_organization_id",
        "dashboard_layouts",
        ["user_id", "organization_id"],
        unique=True,
        schema=PLATFORM,
    )

    enable_rls(connection, "dashboard_layouts", schema=PLATFORM)


def downgrade() -> None:
    connection = op.get_bind()

    disable_rls(connection, "dashboard_layouts", schema=PLATFORM)
    op.drop_table("dashboard_layouts", schema=PLATFORM)
