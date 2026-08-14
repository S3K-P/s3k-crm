"""Data access for roles and permissions.

``roles`` has no RLS policy because ``organization_id IS NULL`` marks a system
template that every tenant must be able to see. Every read below therefore
filters explicitly to *either* the caller's organization *or* the system
templates — never to another tenant's custom roles.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.authorization.models import (
    MembershipRole,
    Permission,
    PermissionAction,
    Role,
    RolePermission,
)


class AuthorizationRepository:
    """Queries over the four RBAC tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Permissions -------------------------------------------------------

    async def list_permissions(self) -> Sequence[Permission]:
        result = await self._session.execute(
            select(Permission).order_by(Permission.module, Permission.action)
        )
        return result.scalars().all()

    async def get_permission(self, *, module: str, action: PermissionAction) -> Permission | None:
        result = await self._session.execute(
            select(Permission).where(Permission.module == module, Permission.action == action)
        )
        return result.scalar_one_or_none()

    # --- Roles -------------------------------------------------------------

    async def list_roles_visible_to(self, organization_id: uuid.UUID) -> Sequence[Role]:
        """System templates plus the organization's own roles — nothing else."""
        result = await self._session.execute(
            select(Role)
            .where(
                or_(
                    Role.organization_id.is_(None),
                    Role.organization_id == organization_id,
                )
            )
            .order_by(Role.is_system.desc(), Role.name)
        )
        return result.scalars().all()

    async def get_role_visible_to(
        self, role_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Role | None:
        """Fetch a role only if the organization is allowed to see it.

        Filtering here rather than after the fetch is what stops an IDOR: a
        caller passing another tenant's role id gets ``None``, which the
        service turns into 404.
        """
        result = await self._session.execute(
            select(Role).where(
                Role.id == role_id,
                or_(
                    Role.organization_id.is_(None),
                    Role.organization_id == organization_id,
                ),
            )
        )
        return result.scalar_one_or_none()

    async def get_system_role_by_name(self, name: str) -> Role | None:
        result = await self._session.execute(
            select(Role).where(Role.organization_id.is_(None), Role.name == name)
        )
        return result.scalar_one_or_none()

    async def add_role(self, role: Role) -> Role:
        self._session.add(role)
        await self._session.flush()
        return role

    async def set_role_permissions(
        self, role_id: uuid.UUID, permission_ids: Sequence[uuid.UUID]
    ) -> None:
        await self._session.execute(
            delete(RolePermission).where(RolePermission.role_id == role_id)
        )
        for permission_id in permission_ids:
            self._session.add(RolePermission(role_id=role_id, permission_id=permission_id))
        await self._session.flush()

    # --- Assignments -------------------------------------------------------

    async def assign_role(self, *, membership_id: uuid.UUID, role_id: uuid.UUID) -> None:
        existing = await self._session.execute(
            select(MembershipRole).where(
                MembershipRole.membership_id == membership_id,
                MembershipRole.role_id == role_id,
            )
        )
        if existing.scalar_one_or_none() is None:
            self._session.add(MembershipRole(membership_id=membership_id, role_id=role_id))
            await self._session.flush()

    async def revoke_role(self, *, membership_id: uuid.UUID, role_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(MembershipRole).where(
                MembershipRole.membership_id == membership_id,
                MembershipRole.role_id == role_id,
            )
        )

    async def list_roles_for_membership(self, membership_id: uuid.UUID) -> Sequence[Role]:
        result = await self._session.execute(
            select(Role)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(MembershipRole.membership_id == membership_id)
            .order_by(Role.name)
        )
        return result.scalars().all()

    async def permission_codes_for_membership(self, membership_id: uuid.UUID) -> set[str]:
        """Every permission the membership's roles grant, as ``module.ACTION``.

        One join rather than per-role lookups: this runs on every authorized
        request via the resolver's cache miss path.
        """
        result = await self._session.execute(
            select(Permission.module, Permission.action)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
            .where(MembershipRole.membership_id == membership_id)
        )
        return {f"{module}.{action.value}" for module, action in result.all()}


__all__ = ["AuthorizationRepository"]
