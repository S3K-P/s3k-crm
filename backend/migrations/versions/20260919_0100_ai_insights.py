"""AI Insights: summaries, intelligence, next-best-action and more (Checkpoint 7).

Revision ID: 20260919_0100
Revises: 20260918_0100
Create Date: 2026-09-19 01:00:00.000000

One table, ``ai_generations`` — the stored result of one AI feature call.
**Append-only**, the same shape ``market_insight_sessions`` uses: a "Refresh"
writes a new row rather than overwriting the last one, so a record's AI
history is real history. See ``app.products.crm.ai_insights.models`` for why
it carries no ``deleted_at`` and is not one of ``OWNER_SCOPED_MODULES`` —
anyone who can see the account can see its AI summary, the same as any other
shared CRM record.

The ``ai_insights`` permission module. Same tier as ``market_insights``: a rep
may ask for a summary or a next-best-action on a record they can already
see (``VIEW``/``CREATE``), and submitting feedback on one (``EDIT``); the
manager/user split mirrors every other CRM module (see
``app.platform.authorization.catalog._CRM_MODULES``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260919_0100"
down_revision: str | Sequence[str] | None = "20260918_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"
TABLE = "ai_generations"

#: Pinned snapshot of the action vocabulary as of this revision — not
#: imported from ``app.platform.authorization.catalog``, for the reason every
#: other feature migration gives: a migration is a snapshot of history, and
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
#: Mirrors ``catalog._MANAGER_ACTIONS``/``_USER_ACTIONS`` for this module.
_MANAGER_ACTIONS: tuple[str, ...] = ("VIEW", "VIEW_ALL", "CREATE", "EDIT", "DELETE", "EXPORT")
_USER_ACTIONS: tuple[str, ...] = ("VIEW", "CREATE", "EDIT")
_MODULE = "ai_insights"

_FEATURES: tuple[str, ...] = (
    "ACCOUNT_SUMMARY",
    "ACCOUNT_INTELLIGENCE",
    "OPPORTUNITY_SUMMARY",
    "LEAD_SUMMARY",
    "NEXT_BEST_ACTION",
    "EMAIL_DRAFT",
    "MEETING_EXTRACTION",
    "NL_QUERY",
    "PRIORITIZATION_EXPLANATION",
)
_STATUSES: tuple[str, ...] = ("READY", "FAILED")
_FEEDBACK_RATINGS: tuple[str, ...] = ("UP", "DOWN")


def upgrade() -> None:
    connection = op.get_bind()

    sa.Enum(*_FEATURES, name="ai_feature", schema=CRM).create(connection, checkfirst=True)
    sa.Enum(*_STATUSES, name="ai_generation_status", schema=CRM).create(connection, checkfirst=True)
    sa.Enum(*_FEEDBACK_RATINGS, name="ai_feedback_rating", schema=CRM).create(
        connection, checkfirst=True
    )
    ai_feature = postgresql.ENUM(*_FEATURES, name="ai_feature", schema=CRM, create_type=False)
    ai_generation_status = postgresql.ENUM(
        *_STATUSES, name="ai_generation_status", schema=CRM, create_type=False
    )
    ai_feedback_rating = postgresql.ENUM(
        *_FEEDBACK_RATINGS, name="ai_feedback_rating", schema=CRM, create_type=False
    )

    op.create_table(
        TABLE,
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("feature", ai_feature, nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            ai_generation_status,
            nullable=False,
            server_default="READY",
        ),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "content",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "used_crm_context", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("feedback_rating", ai_feedback_rating, nullable=True),
        sa.Column("feedback_comment", sa.Text(), nullable=True),
        sa.Column("feedback_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema=CRM,
    )
    op.create_index(f"ix_{TABLE}_organization_id", TABLE, ["organization_id"], schema=CRM)
    op.create_index(
        f"ix_{TABLE}_org_entity_feature_created",
        TABLE,
        ["organization_id", "entity_type", "entity_id", "feature", "created_at"],
        schema=CRM,
    )
    op.create_index(
        f"ix_{TABLE}_org_feature_created",
        TABLE,
        ["organization_id", "feature", "created_at"],
        schema=CRM,
    )
    enable_rls(connection, TABLE, schema=CRM)

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
                "description": f"{action} AI Insights (account/deal/lead intelligence)",
            },
        )

    _grant("Admin", _ACTIONS, connection)
    _grant("Manager", _MANAGER_ACTIONS, connection)
    _grant("User", _USER_ACTIONS, connection)


def _grant(role: str, actions: tuple[str, ...], connection: sa.Connection) -> None:
    """Grant ``ai_insights.<action>`` to a system role template.

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

    disable_rls(connection, TABLE, schema=CRM)
    op.drop_table(TABLE, schema=CRM)

    sa.Enum(name="ai_feedback_rating", schema=CRM).drop(connection, checkfirst=True)
    sa.Enum(name="ai_generation_status", schema=CRM).drop(connection, checkfirst=True)
    sa.Enum(name="ai_feature", schema=CRM).drop(connection, checkfirst=True)
