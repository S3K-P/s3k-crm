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
from app.platform.authorization.catalog import ADMIN_ROLE
from app.platform.authorization.models import PermissionAction
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService
from app.platform.organizations.invitations import invitations_for_session
from app.platform.organizations.models import (
    MembershipStatus,
    OrganizationInvitation,
    OrganizationMembership,
    OrganizationStatus,
)
from app.platform.organizations.provisioning import run_provisioning_hooks
from app.platform.organizations.repository import OrganizationRepository
from app.platform.organizations.service import (
    OrganizationService,
    ensure_administrator_remains,
)
from app.platform.products.service import products_for_session

router = APIRouter()

MODULE = "organizations"
USERS_MODULE = "users"


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: OrganizationStatus


class CreateOrganizationRequest(BaseModel):
    """The onboarding wizard's second and third steps, posted together.

    ``app_codes`` is a *request*, not a grant. It is filtered against the
    self-serve, shipped half of the catalogue on the server, so a payload
    naming ``s3k-finance`` produces no finance entitlement — see
    :meth:`ProductService.grant_self_serve_products`. Sending the two steps in
    one request keeps organization creation atomic: there is no window in which
    a tenant exists with no apps and no administrator.
    """

    name: str = Field(min_length=1, max_length=255)
    #: Descriptive only. Nothing authorizes on these; they land in
    #: ``Organization.settings`` under ``profile``.
    industry: str | None = Field(default=None, max_length=120)
    company_size: str | None = Field(default=None, max_length=60)
    country: str | None = Field(default=None, max_length=120)
    app_codes: list[str] = Field(default_factory=list, max_length=50)


class OrganizationCreatedResponse(BaseModel):
    """The new tenant, plus what it actually ended up entitled to."""

    organization: OrganizationResponse
    #: The codes genuinely granted — never an echo of the request. A client
    #: that asked for an app it may not have is told so by its absence here.
    granted_app_codes: list[str]


class InviteMemberRequest(BaseModel):
    """Ask somebody to join the caller's organization."""

    email: EmailStr
    role_id: uuid.UUID | None = Field(
        default=None, description="Role granted on joining. Must be visible to this organization."
    )


class InvitationResponse(BaseModel):
    """A pending or historical invitation, as an administrator sees it.

    Carries no token: the plaintext is returned once, by the create route, and
    is not recoverable afterwards.
    """

    id: uuid.UUID
    email: str
    role_id: uuid.UUID | None
    status: str
    expires_at: dt.datetime
    created_at: dt.datetime
    accepted_at: dt.datetime | None


class InvitationCreatedResponse(BaseModel):
    """The new invitation **and its one-time token**.

    The token appears here and nowhere else, ever. The frontend composes the
    accept link from it against its own origin; there is no email backend in
    this codebase to send it for us.
    """

    invitation: InvitationResponse
    token: str


class InvitationPreviewResponse(BaseModel):
    """What the accept screen may show before anyone has signed in.

    Deliberately minimal: the organization the holder was already given a link
    to, and the address it was issued to. Enough to say "sign in as ada@acme.com
    to join Acme", and nothing about the tenant beyond its name.
    """

    organization_name: str
    email: str
    expires_at: dt.datetime


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)


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


@router.post("", response_model=OrganizationCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: CreateOrganizationRequest,
    user: CurrentUser,
    service: ServiceDep,
    session: DbSession,
) -> OrganizationCreatedResponse:
    """Found a new organization, with the caller as its administrator.

    Authenticated but **not** tenant-scoped, and it cannot be: the caller has
    no organization yet, which is the whole point. That is also why it takes no
    permission — there is no organization to hold a permission in. The tenant
    it creates is bound to ``user`` from the verified token, never to an id
    from the payload, so this cannot be used to attach a member to somebody
    else's organization.

    Everything happens in one transaction — tenant, membership, Admin role,
    entitlements and each product's first-run setup. A failure anywhere leaves
    no organization behind rather than a half-built one the customer would meet
    as a broken product.

    Raises:
        ConflictError: the caller already belongs to an organization by that
            name, or the slug raced another signup.
    """
    organization = await service.create_organization(
        name=payload.name,
        slug=await service.available_slug(payload.name),
        created_by_id=user.id,
        profile={
            "industry": payload.industry,
            "company_size": payload.company_size,
            "country": payload.country,
        },
    )

    # The founder is an administrator of what they just founded, and is made
    # its default organization so the next login lands here without a picker.
    membership = await service.add_member(
        organization_id=organization.id,
        user_id=user.id,
        is_default=True,
        actor_id=user.id,
    )
    admin_role = await get_authorization(session).get_system_role(ADMIN_ROLE)
    await get_authorization(session).assign_role_to_membership(
        membership_id=membership.id,
        role_id=admin_role.id,
        organization_id=organization.id,
        actor_id=user.id,
    )

    # ``create_organization`` has already granted the default products; this
    # adds anything else the wizard selected that self-service permits. Both
    # go through the products service, so neither can grant what was not sold.
    granted = await products_for_session(session).grant_self_serve_products(
        organization_id=organization.id, codes=payload.app_codes
    )

    # Each product's first-run setup — the CRM's default pipeline, today.
    # Registered by the composition root, because Platform may not import a
    # product (ARCHITECTURE-BOUNDARIES.md rule 1).
    await run_provisioning_hooks(session, organization.id, user.id)

    entitled = {
        product.code
        for _entitlement, product in await products_for_session(session).entitlements_for(
            organization.id
        )
    }
    return OrganizationCreatedResponse(
        organization=OrganizationResponse.model_validate(organization),
        granted_app_codes=sorted(entitled | set(granted)),
    )


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


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------
#
# Issuing and listing hang off ``/organizations/current``, because they are
# administration of a tenant the caller already belongs to. Redemption cannot:
# the person accepting is, by definition, not a member yet and has no tenant
# context, so those two routes live on their own prefix and take
# ``CurrentUser`` rather than a principal. See ``invitations.py`` for why the
# token alone is not sufficient to redeem.


def _invitation_response(invitation: OrganizationInvitation) -> InvitationResponse:
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role_id=invitation.role_id,
        status=invitation.status.value,
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
    )


@router.get("/current/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.VIEW))
    ],
    session: DbSession,
) -> list[InvitationResponse]:
    """Invitations issued by the active organization."""
    invitations = await invitations_for_session(session).list_invitations(
        principal.organization_id
    )
    return [_invitation_response(item) for item in invitations]


@router.post(
    "/current/invitations",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    payload: InviteMemberRequest,
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.CREATE))
    ],
    session: DbSession,
) -> InvitationCreatedResponse:
    """Invite an address to join the active organization.

    The organization comes from the caller's verified tenant context, never
    from the payload, so this cannot be used to add somebody to a tenant the
    caller does not administer.

    Raises:
        ConflictError: that address already has a live invitation.
        NotFoundError: ``role_id`` is not a role this organization can grant.
    """
    if payload.role_id is not None:
        # Resolved through the authorization service so an id naming another
        # organization's private role is refused here, rather than being stored
        # and applied at redemption when nobody is watching.
        await get_authorization(session).get_role(
            payload.role_id, principal.organization_id
        )

    invitation, token = await invitations_for_session(session).invite(
        organization_id=principal.organization_id,
        email=payload.email,
        role_id=payload.role_id,
        invited_by_id=principal.user_id,
    )
    return InvitationCreatedResponse(
        invitation=_invitation_response(invitation), token=token
    )


@router.post("/current/invitations/{invitation_id}/revoke", response_model=InvitationResponse)
async def revoke_invitation(
    invitation_id: uuid.UUID,
    principal: Annotated[
        Principal, Depends(require_permission(USERS_MODULE, PermissionAction.CREATE))
    ],
    session: DbSession,
) -> InvitationResponse:
    """Withdraw a pending invitation.

    Raises:
        NotFoundError: no such invitation *in this organization* — the same
            answer a caller guessing another tenant's id receives.
    """
    invitation = await invitations_for_session(session).revoke(
        invitation_id=invitation_id, organization_id=principal.organization_id
    )
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    return _invitation_response(invitation)


invitation_router = APIRouter()


@invitation_router.get("/preview", response_model=InvitationPreviewResponse)
async def preview_invitation(
    token: Annotated[str, Query(min_length=1, max_length=512)],
    service: ServiceDep,
    session: DbSession,
) -> InvitationPreviewResponse:
    """Name the organization behind a token, for the accept screen.

    Unauthenticated on purpose: the whole point is to tell somebody who is not
    signed in *which* account they need to sign in as. It discloses only what
    the holder of the link was already told, and it does not redeem anything.
    """
    invitation = await invitations_for_session(session).peek(token)
    organization = await service.get_organization(invitation.organization_id)
    return InvitationPreviewResponse(
        organization_name=organization.name,
        email=invitation.email,
        expires_at=invitation.expires_at,
    )


@invitation_router.post("/accept", response_model=OrganizationResponse)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    user: CurrentUser,
    service: ServiceDep,
    session: DbSession,
) -> OrganizationResponse:
    """Join the organization the token names.

    Authenticated, and the signed-in address must be the invited one — a
    forwarded link is useless to anyone else. Redemption, membership and the
    role grant happen in one transaction, so a failure cannot leave the
    invitation spent with no membership to show for it.

    The caller keeps their existing session; the new organization is reachable
    immediately by naming it, with no second sign-in.

    Raises:
        InvitationNotRedeemableError: unknown, used, revoked or expired.
        InvitationAddressMismatchError: signed in as somebody else.
    """
    invitations = invitations_for_session(session)
    invitation = await invitations.redeem(
        token=payload.token, user_id=user.id, user_email=user.email
    )

    existing = await service.get_membership_or_none(
        organization_id=invitation.organization_id, user_id=user.id
    )
    if existing is None:
        # First organization becomes the default, so the next sign-in lands
        # somewhere rather than on an empty picker.
        has_other = bool(await service.list_memberships_for_user(user.id))
        membership = await service.add_member(
            organization_id=invitation.organization_id,
            user_id=user.id,
            is_default=not has_other,
            actor_id=invitation.invited_by_id,
        )
    else:
        membership = existing

    if invitation.role_id is not None:
        await get_authorization(session).assign_role_to_membership(
            membership_id=membership.id,
            role_id=invitation.role_id,
            organization_id=invitation.organization_id,
            actor_id=invitation.invited_by_id,
        )

    organization = await service.get_organization(invitation.organization_id)
    return OrganizationResponse.model_validate(organization)


__all__ = ["invitation_router", "router"]
