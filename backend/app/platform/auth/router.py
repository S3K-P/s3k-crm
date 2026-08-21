"""Authentication routes. HTTP concerns only — all rules live in the service.

The refresh token is written to an httpOnly, SameSite=Lax cookie and is never
placed in a response body (SEC01): JavaScript cannot read it, so an XSS flaw
cannot exfiltrate a long-lived credential.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import Settings
from app.core.database import DbSession
from app.platform.audit.service import audit_for_session
from app.platform.auth.dependencies import (
    CurrentUser,
    get_settings_from_request,
    get_token_issuer,
)
from app.platform.auth.repository import AuthRepository
from app.platform.auth.schemas import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    MembershipSummary,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from app.platform.auth.security import PasswordHasher, TokenIssuer
from app.platform.auth.service import AuthenticationError, AuthService, IssuedTokens
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService
from app.platform.organizations.repository import OrganizationRepository

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings_from_request)]
IssuerDep = Annotated[TokenIssuer, Depends(get_token_issuer)]


def get_auth_service(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    issuer: IssuerDep,
) -> AuthService:
    return AuthService(
        repository=AuthRepository(session),
        organizations=OrganizationRepository(session),
        hasher=PasswordHasher(),
        issuer=issuer,
        settings=settings,
        # Lets failed-login bookkeeping survive the rollback that follows a
        # rejected sign-in.
        session_factory=request.app.state.session_factory,
        # The same factory reaches the audit service, so a *rejected* sign-in
        # is still recorded: it commits its record independently of the
        # transaction the rejection is about to roll back.
        audit=audit_for_session(
            session, session_factory=request.app.state.session_factory
        ),
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def _set_refresh_cookie(response: Response, tokens: IssuedTokens, settings: Settings) -> None:
    """Store the refresh token where script cannot reach it."""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=tokens.refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_ttl_seconds,
        domain=settings.cookie_domain,
        path="/",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        domain=settings.cookie_domain,
        path="/",
    )


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Exchange credentials for an access token and a refresh cookie."""
    tokens = await service.authenticate(
        email=payload.email,
        password=payload.password.get_secret_value(),
        organization_id=payload.organization_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    _set_refresh_cookie(response, tokens, settings)
    return TokenResponse(
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        organization_id=tokens.organization_id,
    )


@router.post("/refresh", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> TokenResponse:
    """Rotate the refresh token and mint a new access token.

    The cookie is preferred; the body is accepted only for clients that cannot
    use cookies at all.
    """
    supplied = request.cookies.get(settings.refresh_cookie_name) or (
        payload.refresh_token.get_secret_value() if payload.refresh_token else None
    )
    if not supplied:
        raise AuthenticationError

    tokens = await service.refresh(
        refresh_token=supplied,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    _set_refresh_cookie(response, tokens, settings)
    return TokenResponse(
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        organization_id=tokens.organization_id,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> Response:
    """Revoke the session family and clear the cookie. Always succeeds."""
    await service.logout(refresh_token=request.cookies.get(settings.refresh_cookie_name))
    _clear_refresh_cookie(response, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=CurrentUserResponse)
async def read_current_user(
    user: CurrentUser,
    session: DbSession,
    request: Request,
) -> CurrentUserResponse:
    """Identity, organization memberships and effective permissions.

    Permissions are resolved for the *active* organization only, because the
    same user can hold different roles in each one.
    """
    organizations = OrganizationRepository(session)
    authorization = AuthorizationService(AuthorizationRepository(session))

    memberships = await organizations.list_memberships_for_user(user.id)

    active_organization_id = None
    raw_header = request.headers.get("X-Organization-Id")
    if raw_header:
        try:
            candidate: uuid.UUID | None = uuid.UUID(raw_header)
        except ValueError:
            candidate = None
        if candidate and any(
            m.organization_id == candidate and m.grants_access for m in memberships
        ):
            active_organization_id = candidate
    if active_organization_id is None:
        active_organization_id = await organizations.default_organization_id(user.id)

    summaries: list[MembershipSummary] = []
    permissions: list[str] = []
    for membership in memberships:
        role_names = await authorization.role_names_for_membership(membership.id)
        summaries.append(
            MembershipSummary(
                organization_id=membership.organization_id,
                organization_name=membership.organization.name,
                organization_slug=membership.organization.slug,
                status=membership.status.value,
                is_default=membership.is_default,
                roles=role_names,
            )
        )
        if membership.organization_id == active_organization_id:
            permissions = sorted(await authorization.effective_permissions(membership.id))

    return CurrentUserResponse(
        user=UserResponse.model_validate(user),
        memberships=summaries,
        active_organization_id=active_organization_id,
        permissions=permissions,
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> Response:
    """Rotate the password and sign every session out, including this one."""
    await service.change_password(
        user=user,
        current_password=payload.current_password.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
    )
    _clear_refresh_cookie(response, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
