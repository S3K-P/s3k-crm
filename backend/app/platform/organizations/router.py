"""Organization and membership routes.

Every path here is scoped to the caller: ``/organizations`` lists only the
organizations they are a member of, and the member-management endpoints operate
on the *active* organization from the tenant context rather than on an id taken
from the URL — so there is no id to tamper with.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.database import DbSession
from app.platform.auth.dependencies import CurrentUser, Principal, require_permission
from app.platform.authorization.models import PermissionAction
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService
from app.platform.organizations.models import MembershipStatus, OrganizationStatus
from app.platform.organizations.repository import OrganizationRepository
from app.platform.organizations.service import OrganizationService

router = APIRouter()

MODULE = "organizations"
USERS_MODULE = "users"


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: OrganizationStatus


class MemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None
    status: MembershipStatus
    is_default: bool
    roles: list[str]


class MemberListResponse(BaseModel):
    data: list[MemberResponse]
    total: int


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID | None = Field(
        default=None, description="Role to grant on joining. Must be visible to this organization."
    )


class MemberStatusRequest(BaseModel):
    status: MembershipStatus


def get_service(session: DbSession) -> OrganizationService:
    return OrganizationService(OrganizationRepository(session))


ServiceDep = Annotated[OrganizationService, Depends(get_service)]


@router.get("", response_model=list[OrganizationResponse])
async def list_my_organizations(
    user: CurrentUser,
    service: ServiceDep,
) -> list[OrganizationResponse]:
    """Organizations the authenticated user belongs to.

    Requires authentication only — a user must be able to see their own
    organizations before a tenant context exists, in order to pick one.
    """
    organizations = await service.list_for_user(user.id)
    return [OrganizationResponse.model_validate(item) for item in organizations]


@router.get("/current", response_model=OrganizationResponse)
async def get_current_organization(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> OrganizationResponse:
    """The organization the current request is scoped to."""
    organization = await service.get_organization(principal.organization_id)
    return OrganizationResponse.model_validate(organization)


@router.get("/current/members", response_model=MemberListResponse)
async def list_members(
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.VIEW))
    ],
    service: ServiceDep,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemberListResponse:
    """Members of the active organization."""
    authorization = AuthorizationService(AuthorizationRepository(session))
    memberships, total = await service.list_members(
        principal.organization_id, limit=limit, offset=offset
    )

    members: list[MemberResponse] = []
    for membership in memberships:
        # Loaded through the auth module's own tables via the ORM relationship
        # that the membership already carries.
        roles = await authorization.role_names_for_membership(membership.id)
        members.append(
            MemberResponse(
                id=membership.id,
                user_id=membership.user_id,
                email="",
                full_name=None,
                status=membership.status,
                is_default=membership.is_default,
                roles=roles,
            )
        )
    return MemberListResponse(data=members, total=total)


@router.post("/current/members", status_code=status.HTTP_201_CREATED)
async def add_member(
    payload: AddMemberRequest,
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.CREATE))
    ],
    service: ServiceDep,
    session: DbSession,
) -> MemberResponse:
    """Add a user to the active organization and optionally grant a role."""
    membership = await service.add_member(
        organization_id=principal.organization_id, user_id=payload.user_id
    )

    roles: list[str] = []
    if payload.role_id is not None:
        authorization = AuthorizationService(AuthorizationRepository(session))
        await authorization.assign_role_to_membership(
            membership_id=membership.id,
            role_id=payload.role_id,
            organization_id=principal.organization_id,
        )
        roles = await authorization.role_names_for_membership(membership.id)

    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        email="",
        full_name=None,
        status=membership.status,
        is_default=membership.is_default,
        roles=roles,
    )


@router.post("/current/members/{user_id}/status", response_model=MemberResponse)
async def set_member_status(
    user_id: uuid.UUID,
    payload: MemberStatusRequest,
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.EDIT))
    ],
    service: ServiceDep,
    session: DbSession,
) -> MemberResponse:
    """Activate or suspend a member of the active organization.

    Scoped to the tenant context, so a member id from another organization
    resolves to "not found" rather than being modified.
    """
    membership = await service.set_member_status(
        organization_id=principal.organization_id, user_id=user_id, status=payload.status
    )
    authorization = AuthorizationService(AuthorizationRepository(session))
    roles = await authorization.role_names_for_membership(membership.id)
    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        email="",
        full_name=None,
        status=membership.status,
        is_default=membership.is_default,
        roles=roles,
    )


__all__ = ["router"]
