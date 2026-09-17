"""AI provider credentials, configurable per organization.

Revision ID: 20260831_0300
Revises: 20260831_0200
Create Date: 2026-08-31 03:00:00.000000

Until now the only way to give the AI gateway a key was ``ANTHROPIC_API_KEY``
in the deployment's environment, which made connecting AI a redeploy and made
it deployment-wide rather than per tenant. This table is the other half:
an organization's administrator can store a credential from Settings, and the
gateway prefers it over the environment.

**The one reversibly-encrypted column in the schema.** Everything else secret
is hashed — argon2id for passwords, SHA-256 for refresh and invitation tokens —
because verification only ever needs a comparison. This value has to be handed
to the provider verbatim, so ``secret_ciphertext`` holds Fernet ciphertext
(AES-128-CBC with an HMAC tag) and the key that opens it lives in the
environment, never in this database. ``app/core/secrets.py`` sets out why an
ephemeral or generated key would be worse than refusing to store anything.

``masked_key`` and ``key_fingerprint`` are written alongside so that listing
credentials, telling two apart, and auditing a change never require the
decryption key at all. The plaintext leaves the process in exactly one
direction: towards the provider.

Tenant-scoped and RLS-FORCEd like the prompt library beside it. A partial
unique index keeps at most one default per organization, for the same reason
the prompt library allows only one active version: two concurrent writes would
otherwise both set the flag and resolution would pick arbitrarily.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260831_0300"
down_revision: str | None = "20260831_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"
TABLE = "ai_provider_credentials"


def upgrade() -> None:
    connection = op.get_bind()

    # Built once then referenced with ``create_type=False`` — see the note in
    # 20260827_0100 on why create_table would otherwise re-emit CREATE TYPE.
    sa.Enum(
        "UNVERIFIED",
        "CONNECTED",
        "INVALID",
        name="ai_credential_status",
        schema=PLATFORM,
    ).create(connection, checkfirst=True)
    status_enum = postgresql.ENUM(
        "UNVERIFIED",
        "CONNECTED",
        "INVALID",
        name="ai_credential_status",
        schema=PLATFORM,
        create_type=False,
    )

    op.create_table(
        TABLE,
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        # Fernet ciphertext. Text rather than bytea because Fernet emits
        # url-safe base64, and keeping it printable means a support engineer
        # reading a row sees obvious ciphertext rather than a binary blob they
        # might mistake for something they can interpret.
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("masked_key", sa.String(length=64), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status", status_enum, nullable=False, server_default="UNVERIFIED"
        ),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_error", sa.String(length=255), nullable=True),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{PLATFORM}.organizations.id"],
            name=f"fk_{TABLE}_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id", "provider", name=f"uq_{TABLE}_org_provider"
        ),
        schema=PLATFORM,
        comment=(
            "Per-organization AI provider credentials. secret_ciphertext is Fernet "
            "ciphertext; the key lives in the environment, never here."
        ),
    )
    op.create_index(
        f"ix_{TABLE}_organization_id", TABLE, ["organization_id"], schema=PLATFORM
    )
    # At most one default per organization.
    op.create_index(
        f"uq_{TABLE}_default",
        TABLE,
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
        schema=PLATFORM,
    )

    enable_rls(connection, TABLE, schema=PLATFORM)


def downgrade() -> None:
    connection = op.get_bind()

    disable_rls(connection, TABLE, schema=PLATFORM)
    op.drop_table(TABLE, schema=PLATFORM)
    sa.Enum(name="ai_credential_status", schema=PLATFORM).drop(connection, checkfirst=True)
