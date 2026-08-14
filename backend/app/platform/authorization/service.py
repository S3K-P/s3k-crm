"""Authorization use cases: effective permissions and role management.

This module is the **only** place that answers "may this principal do X?".
Route handlers ask through :func:`require_permission`; they never inspect roles
themselves, and the frontend's own permission checks are treated as UX, never
as enforcement (doc 13, "Frontend vs Backend").
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import structlog
from fastapi import status

from app.core.exceptions import AppError, NotFoundError
from app.platform.authorization.catalog import (
    SYSTEM_ROLES,
    permission_code,
    permissions_for_system_role,
)
from app.platform.authorization.models import PermissionAction, Role
from app.platform.authorization.repository import AuthorizationRepository

logger = structlog.get_logger(__name__)

#: Re-exported so product modules can name a permission without importing this
#: module's ``models`` — ARCHITECTURE-BOUNDARIES.md rule 2: products consume
#: Platform through service interfaces only.
Action = PermissionAction


class PermissionDeniedError(AppError):
    """The caller is authenticated but lacks the required permission."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "permission_denied"
    message = "You do not have permission to perform this action."


class AuthorizationService:
    """Resolves effective permissions and manages role assignments."""

    def __init__(self, repository: AuthorizationRepository) -> None:
        self._repository = repository

    # --- Effective permissions --------------------------------------------

    async def effective_permissions(self, membership_id: uuid.UUID) -> set[str]:
        """Every ``module.ACTION`` the membership's roles grant."""
        return await self._repository.permission_codes_for_membership(membership_id)

    async def has_permission(
        self, *, membership_id: uuid.UUID, module: str, action: PermissionAction
    ) -> bool:
        granted = await self.effective_permissions(membership_id)
        return permission_code(module, action) in granted

    async def require(
        self, *, membership_id: uuid.UUID, module: str, action: PermissionAction
    ) -> None:
        """Raise unless the membership holds ``module.action``.

        Raises:
            PermissionDeniedError: 403. The message never names the missing
                permission back to the caller — an attacker should not be able
                to map the permission model by probing endpoints. The detail
                goes to the structured log instead.
        """
        if not await self.has_permission(
            membership_id=membership_id, module=module, action=action
        ):
            logger.info(
                "permission_denied",
                membership_id=str(membership_id),
                required=permission_code(module, action),
            )
            raise PermissionDeniedError

    # --- Roles -------------------------------------------------------------

    async def list_roles(self, organization_id: uuid.UUID) -> Sequence[Role]:
        return await self._repository.list_roles_visible_to(organization_id)

    async def get_role(self, role_id: uuid.UUID, organization_id: uuid.UUID) -> Role:
        role = await self._repository.get_role_visible_to(role_id, organization_id)
        if role is None:
            # 404 rather than 403: confirming a role exists in another tenant
            # would itself be a disclosure.
            raise NotFoundError("Role not found.")
        return role

    async def assign_role_to_membership(
        self, *, membership_id: uuid.UUID, role_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """Assign a role, refusing any role the organization cannot see."""
        await self.get_role(role_id, organization_id)
        await self._repository.assign_role(membership_id=membership_id, role_id=role_id)

    async def revoke_role_from_membership(
        self, *, membership_id: uuid.UUID, role_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        await self.get_role(role_id, organization_id)
        await self._repository.revoke_role(membership_id=membership_id, role_id=role_id)

    async def role_names_for_membership(self, membership_id: uuid.UUID) -> list[str]:
        roles = await self._repository.list_roles_for_membership(membership_id)
        return [role.name for role in roles]

    async def get_system_role(self, name: str) -> Role:
        """Fetch a seeded system role template by name."""
        if name not in SYSTEM_ROLES:
            raise NotFoundError(f"'{name}' is not a system role.")
        role = await self._repository.get_system_role_by_name(name)
        if role is None:  # pragma: no cover - seeded by migration
            raise NotFoundError(
                f"System role '{name}' is missing. Run `alembic upgrade head` to seed it."
            )
        return role

    async def system_role_permission_codes(self, name: str) -> tuple[str, ...]:
        return permissions_for_system_role(name)


__all__ = ["Action", "AuthorizationService", "PermissionDeniedError"]
