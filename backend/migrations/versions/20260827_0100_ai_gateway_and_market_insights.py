"""The AI gateway and Market Insights research (ADR-016).

Revision ID: 20260827_0100
Revises: 20260826_0200
Create Date: 2026-08-27 01:00:00.000000

Four tables and two permission modules.

**``platform.ai_prompt_versions``** is the prompt library, and it is append-only
by design. Publishing new wording inserts a row and moves the active flag; it
never rewrites a published version. That is the mechanism behind the rule that
editing a prompt changes future research and leaves completed research alone —
a session records the ``prompt_version_id`` it ran under, so the wording that
produced a report stays resolvable however many times the prompt is edited
afterwards. The partial unique index is what makes "exactly one active version
per key" a database guarantee rather than a service convention: two concurrent
publishes would otherwise both set the flag and later reads would pick between
them arbitrarily.

**The three ``crm.market_insight_*`` tables** hold research sessions, their
conversations and the sources actually retrieved. Sources are a table rather
than JSON on the message so the evidence panel can be queried, deduplicated
and counted without parsing a blob.

All four carry ``organization_id`` with RLS enabled and FORCEd, like every
other table naming a customer. ``app.core.schema_audit`` discovers tenant-
scoped tables from the catalogues rather than from a list, so any one of them
left unprotected here is a test failure, not a silent hole.

**Two new permission modules.** ``ai`` gates prompt configuration —
``ai.ADMIN`` is granted to no system template, so only the wildcard Admin role
holds it and an administrator is the only person who can reword what the AI
researches. ``market_insights`` is an ordinary CRM module and is granted to
Manager and User on the same terms as the rest of the CRM, because running
research is day-to-day sales work.

Every module name, action and role name below is a **pinned literal**. A
migration is a snapshot of history: importing ``authorization.catalog`` is what
broke revision ``8224845a67ac`` on a from-zero run, and
``tests/unit/test_migration_hygiene.py`` now enforces the rule.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260827_0100"
down_revision: str | None = "20260826_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"
CRM = "crm"

PROMPTS_TABLE = "ai_prompt_versions"
SESSIONS_TABLE = "market_insight_sessions"
MESSAGES_TABLE = "market_insight_messages"
SOURCES_TABLE = "market_insight_sources"

#: Pinned; see the module docstring on why this is not imported.
AI_MODULE = "ai"
MARKET_INSIGHTS_MODULE = "market_insights"

_ALL_ACTIONS: tuple[str, ...] = (
    "VIEW",
    "VIEW_TEAM",
    "VIEW_ALL",
    "CREATE",
    "EDIT",
    "DELETE",
    "EXPORT",
    "ADMIN",
)

#: What each system template gains on ``market_insights``. Admin is absent
#: because it holds every permission by wildcard and is granted the full set
#: below along with ``ai.*``.
_MANAGER_ACTIONS: tuple[str, ...] = (
    "VIEW",
    "VIEW_ALL",
    "CREATE",
    "EDIT",
    "DELETE",
    "EXPORT",
)
_USER_ACTIONS: tuple[str, ...] = ("VIEW", "CREATE", "EDIT")

#: The search vector on a research session. Company name at ``A`` because it is
#: what somebody types to find past research; the (renameable) title at ``B``.
#: Restated here rather than imported, for the same reason as everything else
#: in this file — and, as in revision ``20260826_0100``, the migration owns its
#: own copy so changing the model's string alone changes nothing in the
#: database.
_SESSION_SEARCH_VECTOR = (
    "setweight(to_tsvector('english'::regconfig, coalesce(company_name, '')), 'A') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'B')"
)


def upgrade() -> None:
    connection = op.get_bind()

    _create_prompt_versions(connection)
    _create_research_tables(connection)
    _seed_permissions(connection)


def downgrade() -> None:
    connection = op.get_bind()

    _remove_permissions(connection)

    for table in (SOURCES_TABLE, MESSAGES_TABLE, SESSIONS_TABLE):
        disable_rls(connection, table, schema=CRM)
    op.execute(sa.text(f"DROP INDEX IF EXISTS {CRM}.ix_{SESSIONS_TABLE}_search_vector"))
    op.drop_table(SOURCES_TABLE, schema=CRM)
    op.drop_table(MESSAGES_TABLE, schema=CRM)
    op.drop_table(SESSIONS_TABLE, schema=CRM)
    sa.Enum(name="market_insight_role", schema=CRM).drop(connection, checkfirst=True)
    sa.Enum(name="research_status", schema=CRM).drop(connection, checkfirst=True)

    disable_rls(connection, PROMPTS_TABLE, schema=PLATFORM)
    op.drop_table(PROMPTS_TABLE, schema=PLATFORM)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _create_prompt_versions(connection: sa.Connection) -> None:
    op.create_table(
        PROMPTS_TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("change_note", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint(
            "organization_id", "key", "version", name="uq_ai_prompt_versions_org_key_version"
        ),
        schema=PLATFORM,
        comment=(
            "Append-only prompt library. A published version is never rewritten, so "
            "research pinned to it stays reproducible."
        ),
    )
    op.create_index(
        f"ix_{PROMPTS_TABLE}_organization_id",
        PROMPTS_TABLE,
        ["organization_id"],
        schema=PLATFORM,
    )
    # Exactly one active version per (organization, key).
    op.create_index(
        "uq_ai_prompt_versions_active",
        PROMPTS_TABLE,
        ["organization_id", "key"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        schema=PLATFORM,
    )
    enable_rls(connection, PROMPTS_TABLE, schema=PLATFORM)


def _create_research_tables(connection: sa.Connection) -> None:
    # Created explicitly then referenced with ``create_type=False``: without
    # it SQLAlchemy emits CREATE TYPE again from inside create_table and the
    # migration dies on DuplicateObject.
    # No in-flight value: a session row is written only once a turn has
    # finished, so an enum member nothing can hold would be misleading.
    sa.Enum("READY", "FAILED", name="research_status", schema=CRM).create(
        connection, checkfirst=True
    )
    sa.Enum("USER", "ASSISTANT", name="market_insight_role", schema=CRM).create(
        connection, checkfirst=True
    )

    research_status = postgresql.ENUM(
        "READY", "FAILED", name="research_status", schema=CRM, create_type=False
    )
    message_role = postgresql.ENUM(
        "USER", "ASSISTANT", name="market_insight_role", schema=CRM, create_type=False
    )

    # --- Sessions ----------------------------------------------------------
    op.create_table(
        SESSIONS_TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        # Nullable on purpose: researching a company that is not in the CRM is
        # the primary case, not an edge one.
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", research_status, nullable=False, server_default="READY"),
        sa.Column("error_code", sa.String(64), nullable=True),
        # Not a foreign key: the prompt library is a Platform table and CRM
        # tables do not depend on Platform ones (ARCHITECTURE-BOUNDARIES rule 3).
        sa.Column("prompt_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column(
            "used_crm_context",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        comment="One company research session and the conversation about it.",
    )
    for columns in (
        ["organization_id"],
        ["organization_id", "owner_id"],
        ["organization_id", "account_id"],
        ["organization_id", "deleted_at"],
        ["organization_id", "last_activity_at"],
    ):
        op.create_index(
            f"ix_{SESSIONS_TABLE}_{'_'.join(columns)}",
            SESSIONS_TABLE,
            columns,
            schema=CRM,
        )
    op.create_index(f"ix_{SESSIONS_TABLE}_deleted_at", SESSIONS_TABLE, ["deleted_at"], schema=CRM)

    op.execute(
        sa.text(
            f"ALTER TABLE {CRM}.{SESSIONS_TABLE} "
            f"ADD COLUMN search_vector tsvector "
            f"GENERATED ALWAYS AS ({_SESSION_SEARCH_VECTOR}) STORED"
        )
    )
    # Partial: an archived session must never be a search result.
    op.execute(
        sa.text(
            f"CREATE INDEX ix_{SESSIONS_TABLE}_search_vector ON {CRM}.{SESSIONS_TABLE} "
            f"USING GIN (search_vector) WHERE deleted_at IS NULL"
        )
    )

    # --- Messages ----------------------------------------------------------
    op.create_table(
        MESSAGES_TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{CRM}.{SESSIONS_TABLE}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("search_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        comment="One turn of a Market Insights conversation.",
    )
    op.create_index(
        f"ix_{MESSAGES_TABLE}_organization_id",
        MESSAGES_TABLE,
        ["organization_id"],
        schema=CRM,
    )
    # Unique, which is what makes conversation order total even for two
    # messages written inside a single transaction.
    op.create_index(
        f"ix_{MESSAGES_TABLE}_session_id_sequence",
        MESSAGES_TABLE,
        ["session_id", "sequence"],
        unique=True,
        schema=CRM,
    )
    op.create_index(
        f"ix_{MESSAGES_TABLE}_organization_id_session_id",
        MESSAGES_TABLE,
        ["organization_id", "session_id"],
        schema=CRM,
    )

    # --- Sources -----------------------------------------------------------
    op.create_table(
        SOURCES_TABLE,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{CRM}.{SESSIONS_TABLE}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # SET NULL rather than CASCADE: the evidence outlives the turn that
        # fetched it, so a source never silently disappears from a session.
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{CRM}.{MESSAGES_TABLE}.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("page_age", sa.String(64), nullable=True),
        sa.Column("cited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
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
        comment=(
            "A page the web-search tool actually returned. Never written from prose: "
            "a fabricated citation in an intelligence report is worse than none."
        ),
    )
    op.create_index(
        f"ix_{SOURCES_TABLE}_organization_id",
        SOURCES_TABLE,
        ["organization_id"],
        schema=CRM,
    )
    op.create_index(
        f"ix_{SOURCES_TABLE}_organization_id_session_id",
        SOURCES_TABLE,
        ["organization_id", "session_id"],
        schema=CRM,
    )

    for table in (SESSIONS_TABLE, MESSAGES_TABLE, SOURCES_TABLE):
        enable_rls(connection, table, schema=CRM)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def _seed_permissions(connection: sa.Connection) -> None:
    """Add both modules to the catalogue and grant them to system templates."""
    for module in (AI_MODULE, MARKET_INSIGHTS_MODULE):
        for action in _ALL_ACTIONS:
            connection.execute(
                sa.text(
                    "INSERT INTO platform.permissions (module, action, description) "
                    "VALUES (:module, CAST(:action AS platform.permission_action), :description) "
                    "ON CONFLICT (module, action) DO NOTHING"
                ),
                {
                    "module": module,
                    "action": action,
                    "description": f"{action} on {module}",
                },
            )

    # Admin holds the catalogue by wildcard, so it takes every action on both.
    _grant("Admin", AI_MODULE, _ALL_ACTIONS, connection)
    _grant("Admin", MARKET_INSIGHTS_MODULE, _ALL_ACTIONS, connection)

    # Manager and User get research but not configuration: `ai` is deliberately
    # absent from both, which is what keeps the prompt administrator-only.
    _grant("Manager", MARKET_INSIGHTS_MODULE, _MANAGER_ACTIONS, connection)
    _grant("User", MARKET_INSIGHTS_MODULE, _USER_ACTIONS, connection)


def _grant(
    role: str, module: str, actions: Sequence[str], connection: sa.Connection
) -> None:
    """Grant ``module.action`` to a **system** role template.

    ``organization_id IS NULL`` restricts this to the shared templates, so a
    tenant that customised its own roles keeps exactly the permissions it had —
    nobody's access widens because a migration ran.
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
            {"role": role, "module": module, "action": action},
        )


def _remove_permissions(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            "DELETE FROM platform.role_permissions rp USING platform.permissions p "
            "WHERE rp.permission_id = p.id AND p.module IN (:ai, :market)"
        ),
        {"ai": AI_MODULE, "market": MARKET_INSIGHTS_MODULE},
    )
    connection.execute(
        sa.text("DELETE FROM platform.permissions WHERE module IN (:ai, :market)"),
        {"ai": AI_MODULE, "market": MARKET_INSIGHTS_MODULE},
    )
