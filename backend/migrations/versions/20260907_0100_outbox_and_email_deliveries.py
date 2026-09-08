"""The transactional outbox and the email delivery log (Phase C, ADR-013).

Revision ID: 20260907_0100
Revises: 20260906_0100
Create Date: 2026-09-07 01:00:00.000000

Two tables, and one of them is deliberately **not** under RLS.

``platform.outbox_events`` is written inside a tenant's transaction and read by
a worker that is outside every tenant by construction — it processes all of
them. A tenant policy cannot express that, and the alternatives are worse: a
worker that re-scopes per organization would have to enumerate organizations
to find work, turning one indexed query into one per tenant per poll.

The exemption is narrow because the table holds **identifiers, not data**. A
payload names the ids a handler needs; the handler then scopes its session to
``organization_id`` and re-reads the record through tables that are still
under RLS. So the worst a reader of this table learns is that something
happened for some organization — never what. That is the same trade
``platform.organization_invitations`` makes (revision ``20260831_0200``), and
the same one ``app.core.database.provisioning_scope`` documents: a row read
while *establishing* the context that would protect it cannot also be
protected by it.

``platform.email_deliveries`` **is** under RLS, because it is the opposite
kind of table: it holds a recipient address and a subject line, which is
customer data, and it is read by administrators inside one tenant.

The partial index on claimable events is the worker's only hot query. Without
the predicate it would grow with the table's entire history while serving
reads that never leave its head — and this table is append-mostly, so that
history is the bulk of it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260907_0100"
down_revision: str | None = "20260906_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"


def upgrade() -> None:
    connection = op.get_bind()

    sa.Enum(
        "PENDING",
        "PROCESSING",
        "SUCCEEDED",
        "DEAD",
        name="event_status",
        schema=PLATFORM,
    ).create(connection, checkfirst=True)
    event_status = postgresql.ENUM(
        "PENDING",
        "PROCESSING",
        "SUCCEEDED",
        "DEAD",
        name="event_status",
        schema=PLATFORM,
        create_type=False,
    )

    sa.Enum(
        "PENDING",
        "SENT",
        "FAILED",
        "SUPPRESSED",
        name="email_delivery_status",
        schema=PLATFORM,
    ).create(connection, checkfirst=True)
    delivery_status = postgresql.ENUM(
        "PENDING",
        "SENT",
        "FAILED",
        "SUPPRESSED",
        name="email_delivery_status",
        schema=PLATFORM,
        create_type=False,
    )

    # --- The outbox ---------------------------------------------------------

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        # Nullable: a password-reset request is made by somebody who may belong
        # to no organization yet. Such an event may only be handled by a
        # handler registered as untenanted.
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("status", event_status, nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        schema=PLATFORM,
    )
    op.create_index(
        "ix_outbox_events_claimable",
        "outbox_events",
        ["available_at"],
        schema=PLATFORM,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_outbox_events_status_created_at",
        "outbox_events",
        ["status", "created_at"],
        schema=PLATFORM,
    )
    op.create_index(
        "ix_outbox_events_organization_id",
        "outbox_events",
        ["organization_id"],
        schema=PLATFORM,
    )

    # --- The email log ------------------------------------------------------

    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("to_address", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("template", sa.String(length=80), nullable=False),
        sa.Column("status", delivery_status, nullable=False, server_default="PENDING"),
        # What the provider called it. Null until sent; the handle an operator
        # needs to ask the provider what happened after we handed it over.
        sa.Column("provider_message_id", sa.String(length=200), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        # Ties a delivery back to the event that caused it, so "why did this
        # person get two of these" is answerable.
        sa.Column("outbox_event_id", sa.Uuid(as_uuid=True), nullable=True),
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
        schema=PLATFORM,
    )
    op.create_index(
        "ix_email_deliveries_organization_id_created_at",
        "email_deliveries",
        ["organization_id", "created_at"],
        schema=PLATFORM,
    )
    # One delivery per event, so a retried event does not send twice. Partial
    # because most rows have no event (an administrator's manual resend), and
    # NULLs would otherwise collide under a plain unique index.
    op.create_index(
        "uq_email_deliveries_outbox_event_id",
        "email_deliveries",
        ["outbox_event_id"],
        unique=True,
        schema=PLATFORM,
        postgresql_where=sa.text("outbox_event_id IS NOT NULL"),
    )

    # The log holds a recipient address and a subject: customer data, read by
    # administrators inside one tenant. Ordinary policy applies.
    enable_rls(connection, "email_deliveries", schema=PLATFORM)


def downgrade() -> None:
    connection = op.get_bind()

    disable_rls(connection, "email_deliveries", schema=PLATFORM)
    op.drop_table("email_deliveries", schema=PLATFORM)
    op.drop_table("outbox_events", schema=PLATFORM)

    for enum_name in ("email_delivery_status", "event_status"):
        sa.Enum(name=enum_name, schema=PLATFORM).drop(connection, checkfirst=True)
