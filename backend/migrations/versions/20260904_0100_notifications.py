"""Notifications: the in-app inbox and the reminder dedupe key (Phase A).

Revision ID: 20260904_0100
Revises: 20260903_0100
Create Date: 2026-09-04 01:00:00.000000

Adds ``platform.notifications``, tenant-scoped with RLS enabled and forced,
like every other table holding customer data. No permission-catalogue rows
are added: unlike every other Platform and CRM module, notifications carries
no ``require_permission`` gate at all — a notification is scoped to its
recipient, not to a role's reach, and enforcing that is
``NotificationRepository`` filtering every query on ``recipient_user_id`` as
well as ``organization_id`` rather than a grant an administrator holds or
withholds. See ``app/platform/notifications/policies.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_rls, enable_rls

revision: str = "20260904_0100"
down_revision: str | None = "20260903_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "notifications",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("recipient_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        schema=PLATFORM,
    )

    # Leads the caller's own reads: "my notifications" and "my unread
    # notifications" are both this one index, newest first.
    op.create_index(
        "ix_notifications_organization_id_recipient_user_id_created_at",
        "notifications",
        ["organization_id", "recipient_user_id", "created_at"],
        unique=False,
        schema=PLATFORM,
    )

    # Reminder idempotency. NULL is exempt from a unique index in PostgreSQL,
    # so a direct notify() call (dedupe_key always NULL) is never refused by
    # this — only two reminder rows for the same (recipient, key) collide.
    op.create_index(
        "uq_notifications_org_id_recipient_user_id_dedupe_key",
        "notifications",
        ["organization_id", "recipient_user_id", "dedupe_key"],
        unique=True,
        schema=PLATFORM,
    )

    enable_rls(connection, "notifications", schema=PLATFORM)


def downgrade() -> None:
    connection = op.get_bind()
    disable_rls(connection, "notifications", schema=PLATFORM)
    op.drop_table("notifications", schema=PLATFORM)
