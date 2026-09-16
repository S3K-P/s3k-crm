"""Authorization use cases: effective permissions and role management.

This module is the **only** place that answers "may this principal do X?".
Route handlers ask through :func:`require_permission`; they never inspect roles
themselves, and the frontend's own permission checks are treated as UX, never
as enforcement (doc 13, "Frontend vs Backend").

Granting and revoking roles is audited here rather than in the router, because
there are four call sites — two on ``/roles/assignments*`` and two more where
the organizations router grants a role while adding or provisioning a member —
and an audit that only covers three of them is worse than useless. Recording
it at the one point they all pass through is what makes "who gave this person
Admin?" answerable (doc 09; `P1-W08-BE-03`).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from fastapi import status

from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationFailedError
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import AuditService
from app.platform.authorization.catalog import (
    SYSTEM_ROLES,
    permission_code,
    permissions_for_system_role,
)
from app.platform.authorization.models import PermissionAction, Role
from app.platform.authorization.repository import AuthorizationRepository

#: Matches the `roles.name` column (`String(64)`).
MAX_ROLE_NAME_LENGTH = 64

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


#: The permission module role changes are recorded under.
ROLES_MODULE = "roles"


class AuthorizationService:
    """Resolves effective permissions and manages role assignments."""

    def __init__(
        self, repository: AuthorizationRepository, *, audit: AuditService | None = None
    ) -> None:
        self._repository = repository
        # Optional so provisioning callers (``app.bootstrap``, test fixtures)
        # can assign the seeded Admin role before any request context exists.
        # Every HTTP path supplies one.
        self._audit = audit

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

    async def create_role(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        permission_codes: Sequence[str],
        actor_id: uuid.UUID | None = None,
    ) -> Role:
        """Create a tenant's own role, scoped to its organization.

        System templates (``organization_id IS NULL``) are seeded by
        migration only — this always creates a tenant-owned, non-system row.
        """
        name = self._validate_role_name(name)
        await self._ensure_name_available(organization_id, name)
        permission_ids = await self._resolve_permission_ids(permission_codes)

        role = await self._repository.add_role(
            Role(
                organization_id=organization_id,
                name=name,
                description=description,
                is_system=False,
            )
        )
        await self._repository.set_role_permissions(role.id, permission_ids)
        role = await self._repository.refresh_role_permissions(role)
        await self._audit_role_lifecycle(
            action=AuditAction.CREATED,
            role=role,
            organization_id=organization_id,
            actor_id=actor_id,
        )
        return role

    async def update_role(
        self,
        role: Role,
        *,
        organization_id: uuid.UUID,
        values: Mapping[str, Any],
        actor_id: uuid.UUID | None = None,
    ) -> Role:
        """Patch a role the caller has already resolved and is allowed to see.

        Refuses a system template outright — editing "Admin" out from under
        every tenant that inherits it is not a per-organization decision to
        make through this endpoint.
        """
        if role.is_system or role.organization_id is None:
            raise ConflictError("System role templates cannot be edited.")

        if "name" in values:
            name = self._validate_role_name(values["name"])
            if name != role.name:
                await self._ensure_name_available(organization_id, name, excluding_role_id=role.id)
            role.name = name

        if "description" in values:
            role.description = values["description"]

        if "permissions" in values:
            permission_ids = await self._resolve_permission_ids(values["permissions"] or [])
            await self._repository.set_role_permissions(role.id, permission_ids)
            role = await self._repository.refresh_role_permissions(role)

        await self._repository.add_role(role)
        await self._audit_role_lifecycle(
            action=AuditAction.UPDATED,
            role=role,
            organization_id=organization_id,
            actor_id=actor_id,
        )
        return role

    async def delete_role(
        self,
        role: Role,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Delete a tenant's own role.

        Refused while any membership still holds it — deleting it out from
        under an assigned member would silently strip their access rather
        than making the administrator reassign them first, and refused for a
        system template for the same reason ``update_role`` refuses one.
        """
        if role.is_system or role.organization_id is None:
            raise ConflictError("System role templates cannot be deleted.")

        assignment_count = await self._repository.count_role_assignments(role.id)
        if assignment_count:
            member_word = "member" if assignment_count == 1 else "members"
            raise ConflictError(
                f"'{role.name}' is still assigned to {assignment_count} {member_word}. "
                "Reassign them before deleting this role."
            )

        await self._audit_role_lifecycle(
            action=AuditAction.DELETED,
            role=role,
            organization_id=organization_id,
            actor_id=actor_id,
        )
        await self._repository.delete_role(role.id)

    def _validate_role_name(self, name: str) -> str:
        name = name.strip()
        if not name:
            raise ValidationFailedError("A role needs a name.")
        if len(name) > MAX_ROLE_NAME_LENGTH:
            raise ValidationFailedError(
                f"A role name cannot exceed {MAX_ROLE_NAME_LENGTH} characters."
            )
        return name

    async def _ensure_name_available(
        self,
        organization_id: uuid.UUID,
        name: str,
        *,
        excluding_role_id: uuid.UUID | None = None,
    ) -> None:
        """Refuse a name already used by a system template or a sibling role.

        Checked against every role the organization can *see* (system
        templates included), not just its own custom ones: a custom role
        named "Admin" alongside the real system "Admin" would make
        ``membership_ids_with_role_name`` (matched by name) and every admin
        screen ambiguous about which one a person actually holds.
        """
        siblings = await self._repository.list_roles_visible_to(organization_id)
        if any(
            sibling.name == name and sibling.id != excluding_role_id for sibling in siblings
        ):
            raise ConflictError(f"A role called '{name}' already exists in your organization.")

    async def _resolve_permission_ids(self, codes: Sequence[str]) -> list[uuid.UUID]:
        """Resolve permission codes to ids, rejecting anything not in the catalogue.

        Checked against the ``permissions`` table itself rather than the
        theoretical module x action cross product: not every module has a
        row for every action (a module adopts only the actions it needs when
        its migration seeds them), so the table is the only ground truth for
        which codes are real.
        """
        unique_codes = sorted(set(codes))
        if not unique_codes:
            return []
        catalogue = await self._repository.list_permissions()
        by_code = {permission.code: permission.id for permission in catalogue}
        invalid = [code for code in unique_codes if code not in by_code]
        if invalid:
            raise ValidationFailedError(
                f"Unknown permission code(s): {', '.join(invalid)}.",
                details={"invalid_codes": invalid},
            )
        return [by_code[code] for code in unique_codes]

    async def _audit_role_lifecycle(
        self,
        *,
        action: AuditAction,
        role: Role,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            organization_id=organization_id,
            action=action,
            module=ROLES_MODULE,
            actor_id=actor_id,
            entity_type="ROLE",
            entity_id=role.id,
            entity_label=role.name,
            details={"permissions": sorted(permission.code for permission in role.permissions)},
        )

    async def assign_role_to_membership(
        self,
        *,
        membership_id: uuid.UUID,
        role_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Assign a role, refusing any role the organization cannot see.

        The audit record names the **role**, not the membership, as its
        subject: "Admin was granted" is the fact a reviewer scans for, and
        ``entity_label`` keeps the role's name even if the role is later
        renamed or deleted. The membership is in ``details``.
        """
        role = await self.get_role(role_id, organization_id)
        await self._repository.assign_role(membership_id=membership_id, role_id=role_id)
        await self._audit_role_change(
            action=AuditAction.ROLE_ASSIGNED,
            role=role,
            membership_id=membership_id,
            organization_id=organization_id,
            actor_id=actor_id,
        )

    async def revoke_role_from_membership(
        self,
        *,
        membership_id: uuid.UUID,
        role_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        role = await self.get_role(role_id, organization_id)
        await self._repository.revoke_role(membership_id=membership_id, role_id=role_id)
        await self._audit_role_change(
            action=AuditAction.ROLE_REVOKED,
            role=role,
            membership_id=membership_id,
            organization_id=organization_id,
            actor_id=actor_id,
        )

    async def _audit_role_change(
        self,
        *,
        action: AuditAction,
        role: Role,
        membership_id: uuid.UUID,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
    ) -> None:
        if self._audit is None:
            return
        await self._audit.record(
            organization_id=organization_id,
            action=action,
            module=ROLES_MODULE,
            actor_id=actor_id,
            entity_type="ROLE",
            entity_id=role.id,
            entity_label=role.name,
            details={
                "membership_id": membership_id,
                "role_is_system": role.is_system,
                # What the change actually grants, resolved now rather than
                # left for a reader to look up against a role that may have
                # been edited since.
                "permissions": sorted(
                    permission.code for permission in role.permissions
                ),
            },
        )

    async def roles_for_membership(self, membership_id: uuid.UUID) -> Sequence[Role]:
        return await self._repository.list_roles_for_membership(membership_id)

    async def role_names_for_membership(self, membership_id: uuid.UUID) -> list[str]:
        roles = await self._repository.list_roles_for_membership(membership_id)
        return [role.name for role in roles]

    async def membership_ids_with_role(
        self, *, organization_id: uuid.UUID, role_name: str
    ) -> set[uuid.UUID]:
        """Memberships holding ``role_name`` in this organization.

        Exposed so the organizations module can enforce "an organization must
        keep at least one active administrator" without querying RBAC tables
        itself (ARCHITECTURE-BOUNDARIES rule 6).
        """
        return await self._repository.membership_ids_with_role_name(
            organization_id=organization_id, role_name=role_name
        )

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


__all__ = ["ROLES_MODULE", "Action", "AuthorizationService", "PermissionDeniedError"]
