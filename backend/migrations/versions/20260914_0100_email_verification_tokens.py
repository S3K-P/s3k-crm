"""Email verification tokens (P1-W05-BE-01).

Revision ID: 20260914_0100
Revises: 20260913_0100
Create Date: 2026-09-14 01:00:00.000000

One table, ``platform.email_verification_tokens``, built exactly like
``platform.password_reset_tokens`` beside it and **not** under RLS for the same
reason: an email address belongs to a global identity, which may be a member
of several organizations or — straight after signup — of none, so there is no
``organization_id`` to scope a row to. Isolation comes from the token: only a
SHA-256 digest is stored, and a row is reachable by presenting the secret it
was made from and in no other way.

``email`` records the address the link was sent to. Redemption refuses a token
whose address no longer matches the account's, so a link issued before an
address change cannot verify the new address.

``platform.users.email_verified_at`` already exists (revision
``8224845a67ac``); this revision only adds the means of setting it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0100"
down_revision: str | Sequence[str] | None = "20260913_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"


def upgrade() -> None:
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey(
                f"{PLATFORM}.users.id",
                ondelete="CASCADE",
                name="fk_email_verification_tokens_user_id_users",
            ),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        # A SHA-256 digest of 48 bytes of generated entropy, never the token.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Spent rather than deleted, like a reset token: a spent link presented
        # again is a signal worth being able to tell from one never issued.
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index(
        "uq_email_verification_tokens_token_hash",
        "email_verification_tokens",
        ["token_hash"],
        unique=True,
        schema=PLATFORM,
    )
    # For spending a user's outstanding tokens, never for looking one up.
    op.create_index(
        "ix_email_verification_tokens_user_id",
        "email_verification_tokens",
        ["user_id"],
        schema=PLATFORM,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verification_tokens_user_id",
        table_name="email_verification_tokens",
        schema=PLATFORM,
    )
    op.drop_index(
        "uq_email_verification_tokens_token_hash",
        table_name="email_verification_tokens",
        schema=PLATFORM,
    )
    op.drop_table("email_verification_tokens", schema=PLATFORM)
