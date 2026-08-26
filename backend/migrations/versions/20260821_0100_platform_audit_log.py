"""Audit trail: platform.audit_logs, tenant-isolated and append-only.

Revision ID: 20260821_0100
Revises: 20260819_0200
Create Date: 2026-08-21 01:00:00.000000

Closes `P1-W08-BE-03` / `P1-W08-BE-07` and blocker B03: the `audit` module had
no table, so nothing anywhere could satisfy the backend Definition of Done
("audit log emitted for sensitive actions").

Three things are created, and the third is the one that matters most.

**The table.** Tenant-scoped like every other, with five composite indexes
leading on ``organization_id`` — the column every query filters on first — so
the four questions the trail exists to answer (browse by time, by actor, by
record, by action) are index scans rather than sorts over the largest table in
the schema.

**RLS.** The standard ``FOR ALL`` policy from ``app.core.rls``, enabled and
FORCEd. One organization's administrator cannot read another's trail even
through raw SQL, and cannot insert a row attributed to another tenant either —
the policy's ``WITH CHECK`` half covers writes.

**An append-only trigger.** ``BEFORE UPDATE OR DELETE`` per row and
``BEFORE TRUNCATE`` per statement, both raising. This is deliberately *not*
expressed by withholding an UPDATE policy: RLS is ignored entirely by
superusers and by roles with ``BYPASSRLS``, and local development runs as
exactly such a role. A trigger binds every role. An audit trail the application
can quietly rewrite is not evidence of anything.

    Retention (doc 09: two years, then partition by month) is therefore a
    schema-owner operation, not something the application can perform:
    ``ALTER TABLE platform.audit_logs DISABLE TRIGGER audit_logs_append_only``,
    purge, re-enable. That requires table ownership, which the runtime role
    does not have, so expiring old records stays a deliberate, privileged,
    reviewable act. The integration suite cleans the table the same way.

The permission rows this is gated on (``audit.VIEW`` and friends) already exist:
revision ``8224845a67ac`` seeded ``audit`` as one of its pinned modules, and
``Admin`` holds the whole catalogue by wildcard. No seed is needed here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260821_0100"
down_revision: str | None = "20260819_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM_SCHEMA = "platform"
TABLE = "audit_logs"
TRIGGER = "audit_logs_append_only"
TRIGGER_FUNCTION = "reject_audit_log_mutation"

# Pinned literals, never imported from `app.platform.audit.models`: a migration
# is a snapshot of history (see tests/unit/test_migration_hygiene.py). A later
# outcome value is a later revision.
_AUDIT_STATUSES: tuple[str, ...] = ("SUCCESS", "FAILURE", "DENIED")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            server_default=sa.text("uuidv7()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        # No foreign key by design: the trail must outlive the identity it
        # names, exactly as `AuthorshipMixin` explains for CRM tables.
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("entity_label", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*_AUDIT_STATUSES, name="audit_status", schema=PLATFORM_SCHEMA),
            server_default="SUCCESS",
            nullable=False,
        ),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_logs"),
        schema=PLATFORM_SCHEMA,
    )

    op.create_index(
        "ix_audit_logs_organization_id", TABLE, ["organization_id"], schema=PLATFORM_SCHEMA
    )
    op.create_index(
        "ix_audit_logs_organization_id_created_at",
        TABLE,
        ["organization_id", "created_at"],
        schema=PLATFORM_SCHEMA,
    )
    op.create_index(
        "ix_audit_logs_organization_id_actor_id_created_at",
        TABLE,
        ["organization_id", "actor_id", "created_at"],
        schema=PLATFORM_SCHEMA,
    )
    op.create_index(
        "ix_audit_logs_organization_id_entity_created_at",
        TABLE,
        ["organization_id", "entity_type", "entity_id", "created_at"],
        schema=PLATFORM_SCHEMA,
    )
    op.create_index(
        "ix_audit_logs_organization_id_action_created_at",
        TABLE,
        ["organization_id", "action", "created_at"],
        schema=PLATFORM_SCHEMA,
    )
    op.create_index(
        "ix_audit_logs_organization_id_module_created_at",
        TABLE,
        ["organization_id", "module", "created_at"],
        schema=PLATFORM_SCHEMA,
    )

    connection = op.get_bind()
    enable_rls(connection, TABLE, schema=PLATFORM_SCHEMA)

    # --- Append-only enforcement -------------------------------------------
    #
    # `pg_trigger_depth() = 0` is not checked: there is no legitimate cascade
    # that should be allowed to delete an audit row either.
    connection.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {PLATFORM_SCHEMA}.{TRIGGER_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'platform.audit_logs is append-only: % is not permitted',
                    TG_OP
                    USING ERRCODE = 'restrict_violation',
                          HINT = 'Audit records are evidence. Retention is a '
                                 'schema-owner operation that disables this '
                                 'trigger deliberately.';
            END;
            $$;
            """
        )
    )
    connection.execute(
        sa.text(
            f"""
            CREATE TRIGGER {TRIGGER}
            BEFORE UPDATE OR DELETE ON {PLATFORM_SCHEMA}.{TABLE}
            FOR EACH ROW EXECUTE FUNCTION {PLATFORM_SCHEMA}.{TRIGGER_FUNCTION}()
            """
        )
    )
    # TRUNCATE never fires a row-level trigger, and it would empty the table.
    connection.execute(
        sa.text(
            f"""
            CREATE TRIGGER {TRIGGER}_truncate
            BEFORE TRUNCATE ON {PLATFORM_SCHEMA}.{TABLE}
            FOR EACH STATEMENT EXECUTE FUNCTION {PLATFORM_SCHEMA}.{TRIGGER_FUNCTION}()
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(f"DROP TRIGGER IF EXISTS {TRIGGER}_truncate ON {PLATFORM_SCHEMA}.{TABLE}")
    )
    connection.execute(
        sa.text(f"DROP TRIGGER IF EXISTS {TRIGGER} ON {PLATFORM_SCHEMA}.{TABLE}")
    )
    connection.execute(
        sa.text(f"DROP FUNCTION IF EXISTS {PLATFORM_SCHEMA}.{TRIGGER_FUNCTION}()")
    )

    disable_rls(connection, TABLE, schema=PLATFORM_SCHEMA)

    op.drop_table(TABLE, schema=PLATFORM_SCHEMA)
    sa.Enum(name="audit_status", schema=PLATFORM_SCHEMA).drop(connection, checkfirst=True)
