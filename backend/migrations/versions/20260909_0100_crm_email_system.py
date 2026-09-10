"""User-authored CRM email: threads, messages and templates (Phase D).

Revision ID: 20260909_0100
Revises: 20260908_0100
Create Date: 2026-09-09 01:00:00.000000

Three tenant-scoped tables in ``crm``, all with the standard fail-closed
policy, and one new permission module.

**Why these are CRM tables and not more of ``platform.email_deliveries``.**
The delivery log records what the *product* handed to a relay: an address, a
subject, an outcome, no body. It is an operational record, pruned on an
operational schedule, readable by whoever holds ``audit.VIEW``. What Phase D
adds is different in kind — a message a salesperson wrote to a customer, filed
against that customer's record, retained as long as the relationship is. Same
transport underneath, and deliberately so; different lifetime, different
readers, different table.

**``email_messages`` carries its own ``related_entity_*`` even though its
thread has them.** Denormalized on purpose: the record timeline asks
"everything that happened to this account", and answering it through a join to
``email_threads`` would be a join per timeline render for a value that never
changes after the row is written.

**The partial unique index on ``outbox_event_id``** is what makes a retried
send safe, exactly as it is on ``platform.email_deliveries``. Partial because
a draft has no event, and NULLs under a plain unique index collide in
PostgreSQL only if you assume they do — they do not, but the intent is worth
stating in the predicate rather than relying on the reader knowing that.

**The ``emails`` permission module is granted like every module before it**:
to the ``organization_id IS NULL`` role templates, which every organization's
memberships reference, so one insert reaches every existing tenant without a
per-organization loop. ``VIEW_TEAM`` is inserted and granted to nobody but
Admin (who holds the catalogue by wildcard) — Manager already holds the wider
``VIEW_ALL``, and giving it to User would widen every rep's reach as a side
effect of a migration rather than as an administrator's decision. That is the
reasoning revision ``20260905_0100`` established, and this follows it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260909_0100"
down_revision: str | Sequence[str] | None = "20260908_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: Created in dependency order, dropped in reverse, so a child is always gone
#: before its parent.
_TABLES: tuple[str, ...] = ("email_templates", "email_threads", "email_messages")

#: Pinned snapshot of the action vocabulary as of this revision. Not imported
#: from ``app.platform.authorization.catalog``: a migration is a snapshot of
#: history, and reading live code means a later edit silently rewrites what an
#: old revision does — the failure that broke revision ``8224845a67ac`` on a
#: from-zero run.
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

_MODULE = "emails"

#: Mirrors ``models.MAX_RECIPIENTS_PER_FIELD``. Spelled out rather than
#: imported, for the reason ``_ACTIONS`` is.
_MAX_RECIPIENTS = 50

_ADDRESS = 320
_SUBJECT = 500


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
    # `crm_entity_type` already exists — activities, tasks and notes all use
    # it — so it is referenced with `create_type=False` and never created here.
    # Emitting CREATE TYPE for it would fail on a database that has it, which
    # is every database this revision will ever run against.
    sa.Enum(
        "OUTBOUND", "INBOUND", name="email_direction", schema=CRM
    ).create(connection, checkfirst=True)
    sa.Enum(
        "DRAFT", "QUEUED", "SENT", "FAILED", name="email_status", schema=CRM
    ).create(connection, checkfirst=True)

    email_direction = postgresql.ENUM(
        "OUTBOUND", "INBOUND", name="email_direction", schema=CRM, create_type=False
    )
    email_status = postgresql.ENUM(
        "DRAFT",
        "QUEUED",
        "SENT",
        "FAILED",
        name="email_status",
        schema=CRM,
        create_type=False,
    )
    crm_entity_type = postgresql.ENUM(
        "ACCOUNT",
        "CONTACT",
        "LEAD",
        "OPPORTUNITY",
        "CAMPAIGN",
        name="crm_entity_type",
        schema=CRM,
        create_type=False,
    )
    address_array = postgresql.ARRAY(sa.String(length=_ADDRESS))

    # --- Templates ---------------------------------------------------------

    op.create_table(
        "email_templates",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("subject", sa.String(length=_SUBJECT), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column(
            "is_shared", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=True),
        *_timestamps(),
        schema=CRM,
    )
    # Partial unique: a retired template's name is free again. Deletion here is
    # soft and the row never leaves, so a plain unique constraint would burn
    # every name anybody ever retired.
    op.create_index(
        "uq_email_templates_organization_id_name",
        "email_templates",
        ["organization_id", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- Threads -----------------------------------------------------------

    op.create_table(
        "email_threads",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(length=_SUBJECT), nullable=False),
        sa.Column("normalized_subject", sa.String(length=_SUBJECT), nullable=False),
        sa.Column("related_entity_type", crm_entity_type, nullable=True),
        sa.Column("related_entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "message_count", sa.Integer(), nullable=False, server_default="0"
        ),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_email_threads_organization_id_related",
        "email_threads",
        ["organization_id", "related_entity_type", "related_entity_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_email_threads_organization_id_last_message_at",
        "email_threads",
        ["organization_id", "last_message_at"],
        schema=CRM,
    )
    # Thread resolution reads this on every send.
    op.create_index(
        "ix_email_threads_organization_id_normalized_subject",
        "email_threads",
        ["organization_id", "normalized_subject"],
        schema=CRM,
    )

    # --- Messages ----------------------------------------------------------

    op.create_table(
        "email_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "thread_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(f"{CRM}.email_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "direction", email_direction, nullable=False, server_default="OUTBOUND"
        ),
        sa.Column("status", email_status, nullable=False, server_default="DRAFT"),
        sa.Column("subject", sa.String(length=_SUBJECT), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("from_address", sa.String(length=_ADDRESS), nullable=False),
        sa.Column("from_name", sa.String(length=160), nullable=True),
        sa.Column("reply_to", sa.String(length=_ADDRESS), nullable=True),
        sa.Column("to_addresses", address_array, nullable=False),
        sa.Column(
            "cc_addresses", address_array, nullable=False, server_default="{}"
        ),
        sa.Column(
            "bcc_addresses", address_array, nullable=False, server_default="{}"
        ),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("in_reply_to", sa.String(length=255), nullable=True),
        sa.Column(
            "template_id",
            sa.Uuid(as_uuid=True),
            # SET NULL, not RESTRICT: retiring a template must neither be
            # blocked by, nor destroy, the history of what was sent with it.
            sa.ForeignKey(f"{CRM}.email_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("related_entity_type", crm_entity_type, nullable=True),
        sa.Column("related_entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=200), nullable=True),
        sa.Column("outbox_event_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.CheckConstraint(
            "cardinality(to_addresses) > 0", name="to_addresses_not_empty"
        ),
        # The API refuses politely with a 422 and the table refuses absolutely,
        # so a path that bypassed the schema still cannot turn composed mail
        # into a bulk sender.
        sa.CheckConstraint(
            f"cardinality(to_addresses) <= {_MAX_RECIPIENTS} "
            f"AND cardinality(cc_addresses) <= {_MAX_RECIPIENTS} "
            f"AND cardinality(bcc_addresses) <= {_MAX_RECIPIENTS}",
            name="recipient_lists_within_limit",
        ),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_email_messages_organization_id_thread_id",
        "email_messages",
        ["organization_id", "thread_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_email_messages_organization_id_related",
        "email_messages",
        ["organization_id", "related_entity_type", "related_entity_id"],
        schema=CRM,
    )
    op.create_index(
        "ix_email_messages_organization_id_status",
        "email_messages",
        ["organization_id", "status"],
        schema=CRM,
    )
    # At most one message per outbox event, which is what makes a retried send
    # safe. Partial, because a draft has no event.
    op.create_index(
        "uq_email_messages_outbox_event_id",
        "email_messages",
        ["outbox_event_id"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("outbox_event_id IS NOT NULL"),
    )

    # --- Row-Level Security ------------------------------------------------

    for table in _TABLES:
        enable_rls(connection, table, schema=CRM)

    # --- The `emails` permission module -------------------------------------

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
                "description": f"{action} customer email and email templates",
            },
        )

    _grant("Admin", _ACTIONS, connection)
    _grant("Manager", _MANAGER_ACTIONS, connection)
    _grant("User", _USER_ACTIONS, connection)


def _grant(role: str, actions: tuple[str, ...], connection: sa.Connection) -> None:
    """Grant ``emails.<action>`` to a system role template.

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

    op.drop_table("email_messages", schema=CRM)
    op.drop_table("email_threads", schema=CRM)
    op.drop_table("email_templates", schema=CRM)

    for enum_name in ("email_status", "email_direction"):
        sa.Enum(name=enum_name, schema=CRM).drop(connection, checkfirst=True)
