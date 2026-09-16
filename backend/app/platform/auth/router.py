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
    ConfirmEmailVerificationRequest,
    CurrentUserResponse,
    EmailVerificationRequestResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MembershipSummary,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.platform.auth.security import PasswordHasher, TokenIssuer
from app.platform.auth.service import AuthenticationError, AuthService, IssuedTokens
from app.platform.auth.throttle import AuthThrottle
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService
from app.platform.organizations.repository import OrganizationRepository

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings_from_request)]
IssuerDep = Annotated[TokenIssuer, Depends(get_token_issuer)]

#: Per-address throttling for the two routes that take credentials from an
#: unauthenticated caller. Built per request because it resolves the client
#: address from that request's proxy headers.
ThrottleDep = Annotated[AuthThrottle, Depends(AuthThrottle)]


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


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    throttle: ThrottleDep,
) -> TokenResponse:
    """Create an S3K identity and start a session for it.

    **No organization is created here**, and the returned token names none. A
    brand-new account is a person, not yet a tenant; they become one at
    ``POST /organizations``, or they join an existing tenant by redeeming an
    invitation. Keeping the two steps apart is what stops an invited user from
    accidentally founding a second organization — the case Phase 11 warns
    about — because signing up simply does not create one.

    Tokens are issued immediately rather than bouncing the user to the login
    form: they have just proven the password by choosing it, and a redirect to
    ``/login`` mid-wizard is the step most likely to lose them.

    Raises:
        TooManyAttemptsError: 429, the address is over its attempt budget.
        ConflictError: 409, the address is already registered.
        WeakPasswordError: 422, the password fails the configured policy.
    """
    await throttle.check()
    user = await service.register_user(
        email=payload.email,
        password=payload.password.get_secret_value(),
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    # In the signup transaction, so an account that fails to commit leaves no
    # verification mail behind. Verification is not a gate on signing in: the
    # person can use the product at once and confirm the address when the
    # message arrives.
    await service.request_email_verification(user)

    # Not ``authenticate``: that refuses a user who belongs to no organization,
    # which is exactly what this user is until the next screen. See
    # ``begin_onboarding_session`` for why the exception gets its own door
    # rather than being carved out of login.
    tokens = await service.begin_onboarding_session(
        user=user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    _set_refresh_cookie(response, tokens, settings)
    return TokenResponse(
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        organization_id=tokens.organization_id,
    )


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    throttle: ThrottleDep,
) -> TokenResponse:
    """Exchange credentials for an access token and a refresh cookie.

    Two brute-force controls apply, and they cover different attacks. The
    account lockout in the service stops one account being guessed repeatedly.
    The throttle here stops one *address* working through many accounts, which
    the lockout cannot see because no single account ever reaches its
    threshold.

    The throttle runs before the credentials are checked, so a rejected caller
    learns nothing about whether the account exists.

    Raises:
        TooManyAttemptsError: 429, the address is over its attempt budget.
        AuthenticationError: 401, wrong credentials or a locked account.
    """
    await throttle.check()
    tokens = await service.authenticate(
        email=payload.email,
        password=payload.password.get_secret_value(),
        organization_id=payload.organization_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    # Only on success: a wrong password leaves the counter standing.
    await throttle.clear()
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


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    service: AuthServiceDep,
    throttle: ThrottleDep,
) -> Response:
    """Send a reset link, if that address has a usable account.

    **202 with an empty body, always.** Not "202 on success, 404 otherwise":
    the two answers together would let anyone with a list of addresses find out
    which of them are registered here, which is the enumeration the login
    endpoint is careful to prevent and would be pointless to prevent in one
    place and hand over in another. The service returns ``None`` for every
    outcome so this route has nothing to branch on even by accident.

    Throttled on the same bucket as login and signup. Without it the endpoint
    is a free outbound-mail generator pointed at any address an attacker
    chooses — cheap for them, expensive for our sending reputation, and
    unpleasant for the person whose inbox fills up.

    Raises:
        TooManyAttemptsError: 429, the address is over its attempt budget.
    """
    await throttle.check()
    await service.request_password_reset(
        email=payload.email,
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: ResetPasswordRequest,
    response: Response,
    service: AuthServiceDep,
    settings: SettingsDep,
    throttle: ThrottleDep,
) -> Response:
    """Redeem a reset link and set a new password.

    Throttled, because the token is the only credential this route asks for
    and an unthrottled endpoint that accepts a guessable-in-principle secret is
    an invitation to guess. The token is 48 bytes of entropy, so the limit is
    not what makes brute force infeasible — it is what stops somebody trying
    anyway from costing us an argon2 hash per attempt.

    The refresh cookie is cleared even though the caller was probably never
    signed in here: if they *were* — resetting from a session that is still
    open — the reset revoked it server-side, and leaving the cookie in the
    browser would produce one confusing 401 on their next navigation.

    No tokens come back. The next screen is the sign-in form, which is what
    proves the new password actually works.

    Raises:
        TooManyAttemptsError: 429, the address is over its attempt budget.
        InvalidResetTokenError: 400, the link is unknown, spent or expired.
        WeakPasswordError: 422, the new password fails the policy.
    """
    await throttle.check()
    await service.redeem_password_reset(
        token=payload.token.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
    )
    _clear_refresh_cookie(response, settings)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/verify-email/request",
    response_model=EmailVerificationRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_email_verification(
    user: CurrentUser,
    service: AuthServiceDep,
    throttle: ThrottleDep,
) -> EmailVerificationRequestResponse:
    """Email the signed-in user a fresh verification link.

    Authenticated, so it can only ever mail the caller's own address — the
    route cannot be pointed at anybody else's inbox. Throttled all the same:
    each call is an outbound message, and "resend" is a button people press
    repeatedly.

    Raises:
        TooManyAttemptsError: 429, over the attempt budget.
    """
    await throttle.check()
    sent = await service.request_email_verification(user)
    return EmailVerificationRequestResponse(sent=sent, email_verified=not sent)


@router.post("/verify-email/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_email_verification(
    payload: ConfirmEmailVerificationRequest,
    service: AuthServiceDep,
    throttle: ThrottleDep,
) -> Response:
    """Redeem a verification link.

    Unauthenticated on purpose: the link is opened from an inbox, frequently on
    a phone that is not signed in. The token is the proof, it is single-use and
    it expires; confirming it grants no session and no access.

    Raises:
        TooManyAttemptsError: 429, over the attempt budget.
        InvalidVerificationTokenError: 400, unknown, spent, expired or issued
            for an address the account no longer has.
    """
    await throttle.check()
    await service.confirm_email_verification(token=payload.token.get_secret_value())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
