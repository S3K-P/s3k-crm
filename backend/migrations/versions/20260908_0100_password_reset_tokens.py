"""Self-service password reset (Phase C).

Revision ID: 20260908_0100
Revises: 20260907_0100
Create Date: 2026-09-08 01:00:00.000000

One new table and one altered column, and the second is the one worth reading.

``platform.password_reset_tokens`` is **not** under RLS, for the same reason
``platform.users`` is not: a password belongs to a global identity. The person
redeeming a link may be a member of several organizations or — having signed
up and not yet founded or joined one — of none, so there is no
``organization_id`` to scope the row to and a tenant policy would have nothing
to compare. Isolation comes from the token itself: only a SHA-256 digest is
stored, the row is reachable by digest alone, and there is deliberately no
query anywhere that lists a user's tokens.

``platform.email_deliveries.organization_id`` becomes **nullable**, and its
policy becomes NULL-aware. That is a widening of a tenant table and it needs
its justification here rather than in a commit message.

Every message the product sent until now belonged to an organization: an
invitation is sent *by* one, a meeting reminder is *about* a record inside one.
A password reset is not, and the delivery row still has to be written — the
unique index on ``outbox_event_id`` is the entire exactly-once guarantee, and
without a row a retried event puts a second working reset link in somebody's
inbox.

So the column admits NULL and the policy compares with ``IS NOT DISTINCT
FROM``, which is NULL-aware equality: an untenanted row matches a session with
no organization in scope, and nothing else; a tenant's row matches that tenant,
and nothing else. Both directions still fail closed, which a plain ``=`` cannot
express because ``NULL = NULL`` is NULL — under the old policy an untenanted
row would have been invisible to *everyone*, which is a trap rather than
isolation.

``app.core.schema_audit`` checks that shape explicitly. A table named in its
optional-tenant map is held to a *stricter* standard than an ordinary one, not
a laxer one: it must still be RLS-enabled, FORCEd and policy-covered for all
four commands, and it must additionally prove the NULL branch is written.

No data migration is needed. Existing rows all carry an organization and keep
it; the column only gains the ability to be NULL for rows written from now on.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import enable_rls

revision: str = "20260908_0100"
down_revision: str | Sequence[str] | None = "20260907_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"


def upgrade() -> None:
    connection = op.get_bind()

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(
                f"{PLATFORM}.users.id",
                ondelete="CASCADE",
                name="fk_password_reset_tokens_user_id_users",
            ),
            nullable=False,
        ),
        # 64 hex characters: a SHA-256 digest, never the token. Chosen over
        # argon2 for the same reason as `sessions.refresh_token_hash` — this is
        # 48 bytes of generated entropy rather than a human-chosen secret, so
        # it is not brute-forceable and the digest has to stay cheap to look up.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Spent rather than deleted. A used token presented again is a signal —
        # either a double click or somebody else holding the link — and a
        # deleted row is indistinguishable from one that never existed, which
        # turns that signal into "invalid token" and loses it.
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_ip", sa.String(length=45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema=PLATFORM,
    )
    # Unique: two live tokens sharing a digest would make redemption
    # ambiguous, and the digest is the only handle a redeemer has.
    op.create_index(
        "uq_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
        schema=PLATFORM,
    )
    # Not for looking tokens up — nothing may do that by user — but for
    # spending a user's outstanding tokens when one is redeemed or a new one
    # is requested.
    op.create_index(
        "ix_password_reset_tokens_user_id",
        "password_reset_tokens",
        ["user_id"],
        schema=PLATFORM,
    )

    # --- The delivery log's tenant becomes optional -------------------------
    op.alter_column(
        "email_deliveries",
        "organization_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=True,
        schema=PLATFORM,
    )
    # Replaces the policy created by 20260907_0100 with the NULL-aware form.
    # `enable_rls` drops the existing policy by name before creating it, so
    # this is idempotent and leaves exactly one policy on the table.
    enable_rls(connection, "email_deliveries", schema=PLATFORM, optional_tenant=True)


def downgrade() -> None:
    connection = op.get_bind()

    # Untenanted rows cannot exist under the old NOT NULL column, and they are
    # password-reset records rather than anything a tenant would miss. Removed
    # rather than reassigned: there is no organization they could honestly be
    # given, and inventing one would put a person's reset into somebody's
    # delivery log on the way *down* a migration.
    op.execute(
        sa.delete(
            sa.table(
                "email_deliveries",
                sa.column("organization_id"),
                schema=PLATFORM,
            )
        ).where(sa.column("organization_id").is_(None))
    )
    op.alter_column(
        "email_deliveries",
        "organization_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
        schema=PLATFORM,
    )
    enable_rls(connection, "email_deliveries", schema=PLATFORM)

    op.drop_index(
        "ix_password_reset_tokens_user_id",
        table_name="password_reset_tokens",
        schema=PLATFORM,
    )
    op.drop_index(
        "uq_password_reset_tokens_token_hash",
        table_name="password_reset_tokens",
        schema=PLATFORM,
    )
    op.drop_table("password_reset_tokens", schema=PLATFORM)
