"""Organization and membership routes.

Every path here is scoped to the caller: ``/organizations`` lists only the
organizations they are a member of, and the member-management endpoints operate
on the *active* organization from the tenant context rather than on an id taken
from the URL — so there is no id to tamper with.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import DbSession
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.platform.audit.service import audit_for_session
from app.platform.auth.dependencies import (
    CurrentUser,
    Principal,
    get_settings_from_request,
    get_token_issuer,
    require_permission,
)
from app.platform.auth.models import User
from app.platform.auth.repository import AuthRepository
from app.platform.auth.security import PasswordHasher, TokenIssuer
from app.platform.auth.service import AuthService
from app.platform.authorization.models import PermissionAction
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService
from app.platform.organizations.models import (
    MembershipStatus,
    OrganizationMembership,
    OrganizationStatus,
)
from app.platform.organizations.repository import OrganizationRepository
from app.platform.organizations.service import (
    OrganizationService,
    ensure_administrator_remains,
)

router = APIRouter()

MODULE = "organizations"
USERS_MODULE = "users"


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: OrganizationStatus


class MemberRole(BaseModel):
    """A role a member holds, with the id needed to revoke it again.

    ``MemberResponse.roles`` carries only names, which is enough to render a
    badge but not enough to call ``POST /roles/assignments/revoke`` — so the
    admin UI could grant a role and then never take it back. This is the
    missing half.
    """

    id: uuid.UUID
    name: str
    is_system: bool


class MemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None
    status: MembershipStatus
    is_default: bool
    #: Role names, kept for existing consumers.
    roles: list[str]
    #: The same roles with their ids, for assignment and revocation.
    role_details: list[MemberRole]
    #: Display attributes, so the admin screen can edit them in place.
    first_name: str | None
    last_name: str | None
    phone: str | None
    timezone: str | None
    last_login_at: dt.datetime | None
    #: Whether the platform identity itself is usable, separate from whether
    #: this organization currently grants it access.
    user_status: str


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


class CreateUserRequest(BaseModel):
    """Provision a brand-new identity and put it in this organization."""

    email: EmailStr
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    #: Validated against the configured policy by ``AuthService``.
    password: SecretStr
    role_id: uuid.UUID | None = Field(
        default=None, description="Role to grant on joining. Must be visible to this organization."
    )
    phone: str | None = Field(default=None, max_length=32)


class UpdateMemberRequest(BaseModel):
    """Edit a member's display attributes. Omitted fields are left alone."""

    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)


class ResetPasswordRequest(BaseModel):
    new_password: SecretStr


def _display_name(user: User | None) -> str | None:
    """"First Last" from the profile, or ``None`` when there is no profile."""
    if user is None or user.profile is None:
        return None
    return f"{user.profile.first_name} {user.profile.last_name}".strip() or None


async def _describe_members(
    memberships: Sequence[OrganizationMembership],
    *,
    session: AsyncSession,
) -> list[MemberResponse]:
    """Turn membership rows into the wire shape, with identity filled in.

    ``email`` and the profile fields live on ``platform.users`` /
    ``platform.user_profiles``, which memberships do not join to — they are
    looked up here in a single batched directory read rather than one query
    per row.
    """
    authorization = AuthorizationService(AuthorizationRepository(session))
    users = await AuthRepository(session).list_users([m.user_id for m in memberships])
    by_id = {user.id: user for user in users}

    described: list[MemberResponse] = []
    for membership in memberships:
        user = by_id.get(membership.user_id)
        profile = user.profile if user is not None else None
        roles = await authorization.roles_for_membership(membership.id)
        described.append(
            MemberResponse(
                id=membership.id,
                user_id=membership.user_id,
                email=user.email if user is not None else "",
                full_name=_display_name(user),
                status=membership.status,
                is_default=membership.is_default,
                roles=[role.name for role in roles],
                role_details=[
                    MemberRole(id=role.id, name=role.name, is_system=role.is_system)
                    for role in roles
                ],
                first_name=profile.first_name if profile is not None else None,
                last_name=profile.last_name if profile is not None else None,
                phone=profile.phone if profile is not None else None,
                timezone=profile.timezone if profile is not None else None,
                last_login_at=user.last_login_at if user is not None else None,
                user_status=user.status.value if user is not None else "UNKNOWN",
            )
        )
    return described


def get_auth_service(
    request: Request,
    session: DbSession,
    settings: Annotated[Settings, Depends(get_settings_from_request)],
    issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
) -> AuthService:
    """The auth module's service, for the identity half of user management.

    Provisioning and password reset are auth concerns; membership is an
    organizations concern. This screen needs both, so the router composes the
    two services rather than either module reaching into the other's tables.
    """
    return AuthService(
        repository=AuthRepository(session),
        organizations=OrganizationRepository(session),
        hasher=PasswordHasher(),
        issuer=issuer,
        settings=settings,
        session_factory=request.app.state.session_factory,
        audit=audit_for_session(session),
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_service(session: DbSession) -> OrganizationService:
    return OrganizationService(
        OrganizationRepository(session), audit=audit_for_session(session)
    )


ServiceDep = Annotated[OrganizationService, Depends(get_service)]


def get_authorization(session: DbSession) -> AuthorizationService:
    """Audit-aware authorization service for the role grants this screen makes.

    Built through one helper rather than constructed inline at each call site,
    so a route cannot end up granting a role through a service that records
    nothing.
    """
    return AuthorizationService(
        AuthorizationRepository(session), audit=audit_for_session(session)
    )


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
    memberships, total = await service.list_members(
        principal.organization_id, limit=limit, offset=offset
    )
    members = await _describe_members(memberships, session=session)
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
        organization_id=principal.organization_id,
        user_id=payload.user_id,
        actor_id=principal.user_id,
    )

    if payload.role_id is not None:
        await get_authorization(session).assign_role_to_membership(
            membership_id=membership.id,
            role_id=payload.role_id,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
        )

    described = await _describe_members([membership], session=session)
    return described[0]


@router.post("/current/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.CREATE))
    ],
    service: ServiceDep,
    auth: AuthServiceDep,
    session: DbSession,
) -> MemberResponse:
    """Create a new S3K identity and add it to the active organization.

    Closes the gap that made the admin screen add-only against ids the
    administrator had to obtain some other way: there was no route that could
    bring a new person into the system at all.

    Identity, profile, membership and the optional role grant all happen in
    the request's single transaction, so a rejected role never leaves a
    half-provisioned user behind.

    Raises:
        ConflictError: the address is already registered.
        WeakPasswordError: the password fails the configured policy.
    """
    user = await auth.register_user(
        email=str(payload.email),
        password=payload.password.get_secret_value(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
    )
    if payload.phone:
        await auth.update_profile(
            user=user,
            phone=payload.phone,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
        )

    membership = await service.add_member(
        organization_id=principal.organization_id,
        user_id=user.id,
        actor_id=principal.user_id,
    )

    if payload.role_id is not None:
        await get_authorization(session).assign_role_to_membership(
            membership_id=membership.id,
            role_id=payload.role_id,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
        )

    described = await _describe_members([membership], session=session)
    return described[0]


@router.patch("/current/members/{user_id}", response_model=MemberResponse)
async def update_member(
    user_id: uuid.UUID,
    payload: UpdateMemberRequest,
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.EDIT))
    ],
    service: ServiceDep,
    auth: AuthServiceDep,
    session: DbSession,
) -> MemberResponse:
    """Update a member's display details.

    Membership is resolved first and inside the tenant context, so this can
    only ever edit somebody who is already in the caller's organization — a
    user id from another tenant is "not found", not an edit.
    """
    membership = await service.get_membership(
        organization_id=principal.organization_id, user_id=user_id
    )
    user = await AuthRepository(session).get_user(user_id)
    if user is None:
        raise NotFoundError("User not found.")

    await auth.update_profile(
        user=user,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        timezone=payload.timezone,
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
    )

    described = await _describe_members([membership], session=session)
    return described[0]


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

    Two refusals guard against an administrator locking the organization —
    or themselves — out:

    * suspending your own membership, which would end your access on the very
      next request with no way back through the UI;
    * suspending the last active administrator.

    Suspension takes effect immediately: the membership verifier reads status
    on every request, so a suspended member's existing access token stops
    resolving a tenant context at once rather than at expiry.
    """
    if user_id == principal.user_id and payload.status is not MembershipStatus.ACTIVE:
        raise ValidationFailedError(
            "You cannot deactivate your own membership.",
            details={"hint": "Ask another administrator to do it."},
        )

    if payload.status is not MembershipStatus.ACTIVE:
        membership = await service.get_membership(
            organization_id=principal.organization_id, user_id=user_id
        )
        await ensure_administrator_remains(
            organizations=service,
            authorization=AuthorizationService(AuthorizationRepository(session)),
            organization_id=principal.organization_id,
            losing_admin_membership_id=membership.id,
        )

    membership = await service.set_member_status(
        organization_id=principal.organization_id,
        user_id=user_id,
        status=payload.status,
        actor_id=principal.user_id,
    )
    described = await _describe_members([membership], session=session)
    return described[0]


@router.post(
    "/current/members/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT
)
async def reset_member_password(
    user_id: uuid.UUID,
    payload: ResetPasswordRequest,
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.ADMIN))
    ],
    service: ServiceDep,
    auth: AuthServiceDep,
    session: DbSession,
) -> Response:
    """Set a member's password administratively and sign them out everywhere.

    Requires ``users.ADMIN`` rather than ``users.EDIT``: taking over an
    account's credentials is a strictly stronger act than editing its name,
    and Manager holds EDIT on most modules.

    The response is deliberately empty. The new password came from the caller,
    so echoing it back would only put a live credential into another log.
    """
    await service.get_membership(
        organization_id=principal.organization_id, user_id=user_id
    )
    user = await AuthRepository(session).get_user(user_id)
    if user is None:
        raise NotFoundError("User not found.")

    await auth.set_password(
        user=user,
        new_password=payload.new_password.get_secret_value(),
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
