"""Role and permission routes (read + assignment).

Roles are only ever listed for the caller's own organization plus the shared
system templates; a role id belonging to another tenant resolves to 404.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.catalog import PERMISSION_MODULES, all_permission_codes
from app.platform.authorization.models import PermissionAction
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService

router = APIRouter()

MODULE = "roles"


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    name: str
    description: str | None
    is_system: bool


class RoleDetailResponse(RoleResponse):
    permissions: list[str]


class PermissionCatalogResponse(BaseModel):
    """The full vocabulary, for building an admin permission matrix."""

    modules: list[str]
    actions: list[str]
    codes: list[str]


class RoleAssignmentRequest(BaseModel):
    membership_id: uuid.UUID
    role_id: uuid.UUID


def get_service(session: DbSession) -> AuthorizationService:
    return AuthorizationService(AuthorizationRepository(session))


ServiceDep = Annotated[AuthorizationService, Depends(get_service)]


@router.get("/permissions", response_model=PermissionCatalogResponse)
async def get_permission_catalog(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
) -> PermissionCatalogResponse:
    """Every permission the system defines."""
    return PermissionCatalogResponse(
        modules=list(PERMISSION_MODULES),
        actions=[action.value for action in PermissionAction],
        codes=list(all_permission_codes()),
    )


@router.get("", response_model=list[RoleResponse])
async def list_roles(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> list[RoleResponse]:
    """System templates plus this organization's own roles."""
    roles = await service.list_roles(principal.organization_id)
    return [RoleResponse.model_validate(role) for role in roles]


@router.get("/{role_id}", response_model=RoleDetailResponse)
async def get_role(
    role_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> RoleDetailResponse:
    """One role and the permissions it grants."""
    role = await service.get_role(role_id, principal.organization_id)
    return RoleDetailResponse(
        id=role.id,
        organization_id=role.organization_id,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        permissions=sorted(permission.code for permission in role.permissions),
    )


@router.post("/assignments", status_code=status.HTTP_204_NO_CONTENT)
async def assign_role(
    payload: RoleAssignmentRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))],
    service: ServiceDep,
) -> Response:
    """Grant a role to a membership in the active organization."""
    await service.assign_role_to_membership(
        membership_id=payload.membership_id,
        role_id=payload.role_id,
        organization_id=principal.organization_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# POST rather than DELETE: the target is identified by a (membership, role)
# pair in the body, which DELETE cannot carry portably.
@router.post("/assignments/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_role(
    payload: RoleAssignmentRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))],
    service: ServiceDep,
) -> Response:
    """Revoke a role from a membership in the active organization."""
    await service.revoke_role_from_membership(
        membership_id=payload.membership_id,
        role_id=payload.role_id,
        organization_id=principal.organization_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
