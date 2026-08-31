"""Organization invitations: joining a tenant you were asked to join.

Revision ID: 20260831_0200
Revises: 20260831_0100
Create Date: 2026-08-31 02:00:00.000000

Until now the only way into an organization was for an administrator to create
the account outright (``POST /organizations/current/users``), which means
choosing somebody else's password for them. An invitation inverts that: the
administrator names an address and a role, and the person themselves sets the
credential.

**The token is stored as a SHA-256 digest, never in the clear.** The row is
therefore useless to anyone who reads the table — a database dump does not
yield working invitations — which is the same rule
``platform.sessions`` already applies to refresh tokens.

**Why this table is RLS-exempt, and why that is not a weakening.** Redeeming an
invitation is, by definition, something a person does *before* they belong to
the organization. There is no tenant context to scope the lookup by, and there
cannot be one: the row is what establishes it. This is the same reason
``platform.organizations`` and ``platform.organization_memberships`` are
exempt, and the rationale ``app.core.database.provisioning_scope`` already
states — tables read while *establishing* context cannot also be protected by
it.

What replaces the policy is threefold, and all three matter:

1. The redemption lookup is by token digest alone. The token is 256 bits of
   ``secrets.token_urlsafe`` entropy, so possessing it *is* the authorization;
   an organization id is never accepted from the caller.
2. Every administrator-facing read filters on ``organization_id`` explicitly in
   the repository, which is the isolation the policy would otherwise provide.
   See ``InvitationRepository`` — no query there omits it.
3. The table holds an email address and a role, and no CRM data whatsoever, so
   the exemption's blast radius does not extend to customer records.

A partial unique index keeps one PENDING invitation per address per
organization, while allowing any number of historical ACCEPTED or REVOKED rows
for the same address — re-inviting somebody who declined must not collide with
the record that they declined.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0200"
down_revision: str | None = "20260831_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"


def upgrade() -> None:
    connection = op.get_bind()

    sa.Enum(
        "PENDING",
        "ACCEPTED",
        "REVOKED",
        name="invitation_status",
        schema=PLATFORM,
    ).create(connection, checkfirst=True)
    invitation_status = postgresql.ENUM(
        "PENDING",
        "ACCEPTED",
        "REVOKED",
        name="invitation_status",
        schema=PLATFORM,
        create_type=False,
    )

    op.create_table(
        "organization_invitations",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        # The role the invitee receives on joining. Nullable so an invitation
        # can be sent before the organization has decided; SET NULL rather than
        # CASCADE so deleting a role does not silently delete the invitation
        # and with it the record that somebody was invited at all.
        sa.Column("role_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", invitation_status, nullable=False, server_default="PENDING"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_invitations")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            [f"{PLATFORM}.organizations.id"],
            name="fk_organization_invitations_organization_id_organizations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            [f"{PLATFORM}.roles.id"],
            name="fk_organization_invitations_role_id_roles",
            ondelete="SET NULL",
        ),
        schema=PLATFORM,
    )

    op.create_index(
        op.f("ix_organization_invitations_organization_id"),
        "organization_invitations",
        ["organization_id"],
        unique=False,
        schema=PLATFORM,
    )
    # Redemption looks the row up by this and nothing else, so it must be
    # unique and indexed: the digest is the credential.
    op.create_index(
        "uq_organization_invitations_token_hash",
        "organization_invitations",
        ["token_hash"],
        unique=True,
        schema=PLATFORM,
    )
    # One live invitation per address per organization. Partial, so the history
    # of accepted and revoked ones does not block a fresh invite.
    op.create_index(
        "uq_organization_invitations_pending_email",
        "organization_invitations",
        ["organization_id", "email"],
        unique=True,
        schema=PLATFORM,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    connection = op.get_bind()

    op.drop_table("organization_invitations", schema=PLATFORM)
    sa.Enum(name="invitation_status", schema=PLATFORM).drop(connection, checkfirst=True)
