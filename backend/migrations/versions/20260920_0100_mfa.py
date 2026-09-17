"""Multi-factor authentication: TOTP credentials and recovery codes (Checkpoint 8).

Revision ID: 20260920_0100
Revises: 20260919_0100
Create Date: 2026-09-20 01:00:00.000000

Two tables, ``platform.mfa_credentials`` and ``platform.mfa_recovery_codes``,
untenanted like ``users``/``password_reset_tokens`` — a second factor belongs
to the identity, not to any one organization it signs into, and no RLS
applies for the same reason. No permission catalogue change: every
authenticated user manages their own MFA through ``/auth/mfa/*``, gated on
being that person rather than on an RBAC grant.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0100"
down_revision: str | Sequence[str] | None = "20260919_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"


def upgrade() -> None:
    op.create_table(
        "mfa_credentials",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], [f"{PLATFORM}.users.id"], ondelete="CASCADE"),
        schema=PLATFORM,
    )
    op.create_index(
        "uq_mfa_credentials_user_id",
        "mfa_credentials",
        ["user_id"],
        unique=True,
        schema=PLATFORM,
    )

    op.create_table(
        "mfa_recovery_codes",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column("credential_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["credential_id"], [f"{PLATFORM}.mfa_credentials.id"], ondelete="CASCADE"
        ),
        schema=PLATFORM,
    )
    op.create_index(
        "ix_mfa_recovery_codes_credential_id",
        "mfa_recovery_codes",
        ["credential_id"],
        schema=PLATFORM,
    )


def downgrade() -> None:
    op.drop_table("mfa_recovery_codes", schema=PLATFORM)
    op.drop_table("mfa_credentials", schema=PLATFORM)
