"""SQLAlchemy models for the authorization module (doc 04 "Role & Permission").

Four tables implement RBAC:

``permissions``       the catalogue of ``module.action`` capabilities. Global,
                      not tenant-scoped — the vocabulary is the same for every
                      organization.
``roles``             named bundles of permissions. ``organization_id IS NULL``
                      marks a **system role template** shared by all tenants;
                      a non-null value is a tenant's own custom role.
``role_permissions``  role → permission.
``membership_roles``  membership → role. Roles are assigned per organization,
                      so the same user can be an Admin in one tenant and a
                      read-only User in another.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin

PLATFORM_SCHEMA = "platform"


class PermissionAction(enum.StrEnum):
    """The actions every module supports (doc 04).

    ``VIEW``, ``VIEW_TEAM`` and ``VIEW_ALL`` are deliberately separate and form
    three widening rungs. ``VIEW`` answers *may this caller read this module at
    all*; ``VIEW_TEAM`` answers *may they read their team-mates' records*;
    ``VIEW_ALL`` answers *may they read anybody's*. Splitting them is what
    makes record-level authorization (ADR-010) a data question the catalogue
    answers, rather than a role name hardcoded in a query.
    """

    VIEW = "VIEW"
    #: Read across the caller's team-mates. Resolved from live team membership
    #: (B02); a holder who is on no team sees only their own records, which is
    #: the safe direction to degrade in.
    VIEW_TEAM = "VIEW_TEAM"
    #: Read across owners. Without it a caller sees only records they own.
    VIEW_ALL = "VIEW_ALL"
    CREATE = "CREATE"
    EDIT = "EDIT"
    DELETE = "DELETE"
    EXPORT = "EXPORT"
    ADMIN = "ADMIN"


class Permission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One ``module.action`` capability, e.g. ``leads.CREATE``."""

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("module", "action", name="uq_permissions_module_action"),
        {"schema": PLATFORM_SCHEMA},
    )

    module: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[PermissionAction] = mapped_column(
        Enum(
            PermissionAction,
            name="permission_action",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def code(self) -> str:
        """Canonical wire form, e.g. ``leads.CREATE``."""
        return f"{self.module}.{self.action.value}"


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named bundle of permissions.

    ``organization_id IS NULL`` means a system template every tenant inherits.
    Tenant-defined roles carry their organization and are filtered by it on
    every read — a tenant must never see or assign another tenant's role.
    """

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_roles_organization_id_name"),
        Index("ix_roles_organization_id", "organization_id"),
        {"schema": PLATFORM_SCHEMA},
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    permissions: Mapped[list[Permission]] = relationship(
        secondary=f"{PLATFORM_SCHEMA}.role_permissions", lazy="selectin"
    )


class RolePermission(Base):
    """Join table: which permissions a role grants."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        PrimaryKeyConstraint("role_id", "permission_id", name="pk_role_permissions"),
        {"schema": PLATFORM_SCHEMA},
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.permissions.id", ondelete="CASCADE"),
        nullable=False,
    )


class MembershipRole(Base):
    """Join table: which roles a membership holds inside its organization."""

    __tablename__ = "membership_roles"
    __table_args__ = (
        PrimaryKeyConstraint("membership_id", "role_id", name="pk_membership_roles"),
        Index("ix_membership_roles_membership_id", "membership_id"),
        {"schema": PLATFORM_SCHEMA},
    )

    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.organization_memberships.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    role: Mapped[Role] = relationship(lazy="selectin")


__all__ = [
    "MembershipRole",
    "Permission",
    "PermissionAction",
    "Role",
    "RolePermission",
]
