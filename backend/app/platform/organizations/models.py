"""SQLAlchemy models for the organizations module (doc 04).

``organizations``             the tenant itself.
``organization_memberships``  the user ↔ tenant join, and the *only* thing that
                              authorizes a user to act inside an organization.

Neither table uses :class:`~app.core.models.TenantMixin`. ``organizations.id``
*is* the tenant discriminator, and a membership row must remain readable while
resolving which organizations a user may enter — that lookup happens before any
tenant context exists. Both are therefore protected by explicit query filters
and the authorization layer rather than by RLS; see ``13-SECURITY-AND-TENANT-
ISOLATION.md`` and the note in the Phase 1 migration.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin

PLATFORM_SCHEMA = "platform"


class OrganizationStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class MembershipStatus(enum.StrEnum):
    """A membership only grants access while ``ACTIVE``.

    ``INVITED`` and ``SUSPENDED`` members authenticate successfully but are
    refused tenant context — deactivating a member must revoke data access
    without deleting the audit trail of their past activity.
    """

    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    SUSPENDED = "SUSPENDED"


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A tenant. Its ``id`` is the value every RLS policy compares against."""

    __tablename__ = "organizations"
    __table_args__ = ({"schema": PLATFORM_SCHEMA},)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(
            OrganizationStatus,
            name="organization_status",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
        server_default=OrganizationStatus.ACTIVE.value,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    memberships: Mapped[list[OrganizationMembership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status is OrganizationStatus.ACTIVE and self.deleted_at is None


class OrganizationMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Links a user to an organization and carries their roles there.

    The unique constraint on ``(organization_id, user_id)`` is what makes
    membership lookup unambiguous; the authorization layer depends on it.
    """

    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", name="uq_organization_memberships_organization_id_user_id"
        ),
        Index("ix_organization_memberships_user_id", "user_id"),
        Index("ix_organization_memberships_organization_id", "organization_id"),
        {"schema": PLATFORM_SCHEMA},
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(
            MembershipStatus,
            name="membership_status",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=MembershipStatus.ACTIVE,
        server_default=MembershipStatus.ACTIVE.value,
    )
    #: Organization selected when the user signs in without naming one.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    joined_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="memberships")

    @property
    def grants_access(self) -> bool:
        return self.status is MembershipStatus.ACTIVE


class InvitationStatus(enum.StrEnum):
    """Where an invitation is in its one-way lifecycle."""

    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    #: Withdrawn by an administrator, or superseded. Never reverts to PENDING.
    REVOKED = "REVOKED"


class OrganizationInvitation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An outstanding offer to join an organization.

    Like the two tables above, and for the same reason, this one is **not**
    RLS-protected: it is read while a person who does not yet belong to the
    organization is establishing that they may. Isolation comes from the
    repository filtering every administrator-facing query on
    ``organization_id``, and from redemption being possible only with the token
    itself. The migration that creates it sets out the full argument.

    ``token_hash`` is a SHA-256 digest. The token is shown to the inviting
    administrator once, at creation, and is not recoverable from this row.
    """

    __tablename__ = "organization_invitations"
    __table_args__ = (
        Index("uq_organization_invitations_token_hash", "token_hash", unique=True),
        Index(
            "uq_organization_invitations_pending_email",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{PLATFORM_SCHEMA}.organizations.id",
            ondelete="CASCADE",
            name="fk_organization_invitations_organization_id_organizations",
        ),
        nullable=False,
        index=True,
    )
    #: Stored lower-cased. Redemption compares the *invited* address against the
    #: authenticated user's own, so an invitation cannot be redeemed by
    #: whoever happens to hold the link.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{PLATFORM_SCHEMA}.roles.id",
            ondelete="SET NULL",
            name="fk_organization_invitations_role_id_roles",
        ),
        nullable=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(
            InvitationStatus,
            name="invitation_status",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=InvitationStatus.PENDING,
        server_default=InvitationStatus.PENDING.value,
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    accepted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    def is_redeemable(self, *, now: dt.datetime) -> bool:
        """Whether this invitation can still be accepted.

        Expiry is read from the clock rather than from a status somebody has to
        remember to sweep, so a lapsed invitation is refused even if no
        background job has ever run.
        """
        return self.status is InvitationStatus.PENDING and self.expires_at > now


__all__ = [
    "InvitationStatus",
    "MembershipStatus",
    "Organization",
    "OrganizationInvitation",
    "OrganizationMembership",
    "OrganizationStatus",
]
