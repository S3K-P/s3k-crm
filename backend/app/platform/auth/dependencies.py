"""FastAPI dependencies for authentication and tenant-scoped principals.

Three layers, deliberately separate so failures map to the right status code:

``CurrentUser``       authenticated identity only. Missing or bad token → 401.
``CurrentPrincipal``  identity **plus** a verified organization membership.
                      Authenticated but no usable tenant context → 403.
``require_permission``  a specific capability within that organization → 403.

Products import from this module (never from ``auth.repository`` or
``auth.models``) — see ARCHITECTURE-BOUNDARIES.md.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from typing import Annotated

import structlog
from fastapi import Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import DbSession
from app.core.exceptions import AppError
from app.core.tenant import TenantContext, require_tenant_context
from app.platform.auth.models import User
from app.platform.auth.repository import AuthRepository
from app.platform.auth.security import InvalidTokenError, TokenIssuer
from app.platform.authorization.catalog import permission_code
from app.platform.authorization.models import PermissionAction
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import (
    AuthorizationService,
    PermissionDeniedError,
)
from app.platform.organizations.repository import OrganizationRepository

logger = structlog.get_logger(__name__)

BEARER_PREFIX = "Bearer "


class NotAuthenticatedError(AppError):
    """No usable credentials were presented."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "not_authenticated"
    message = "Authentication is required to access this resource."


def get_settings_from_request(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_token_issuer(request: Request) -> TokenIssuer:
    """The process-wide issuer, built once during application startup."""
    issuer: TokenIssuer = request.app.state.token_issuer
    return issuer


def extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if not header or not header.startswith(BEARER_PREFIX):
        return None
    token = header[len(BEARER_PREFIX) :].strip()
    return token or None


async def get_current_user(
    request: Request,
    session: DbSession,
    issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
) -> User:
    """Resolve the authenticated user from the bearer token.

    Raises:
        NotAuthenticatedError: no token supplied.
        InvalidTokenError: token failed verification, or names a user who no
            longer exists or has been disabled since it was issued.
    """
    token = extract_bearer_token(request)
    if token is None:
        raise NotAuthenticatedError

    claims = issuer.verify(token)

    repository = AuthRepository(session)
    user = await repository.get_user(claims.user_id)
    if user is None or not user.is_active:
        logger.info("token_subject_unusable", user_id=str(claims.user_id))
        raise InvalidTokenError

    # A token minted before the user's revocation cutoff is dead even though
    # its signature and expiry are still valid (password change, admin revoke).
    #
    # The cutoff is truncated to whole seconds because a JWT ``iat`` has
    # one-second resolution: without this, a token issued in the same second
    # the cutoff was written looks older than it and is wrongly rejected.
    cutoff = user.tokens_valid_from.replace(microsecond=0)
    if claims.issued_at < cutoff:
        logger.info("token_issued_before_revocation_cutoff", user_id=str(user.id))
        raise InvalidTokenError

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


class PermissionDeniedForOrganizationError(AppError):
    """Authenticated, but not an active member of the requested organization."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "organization_access_denied"
    message = "You do not have access to this organization."


@dataclass(frozen=True, slots=True)
class Principal:
    """An authenticated user acting inside a verified organization.

    Every tenant-scoped handler receives one of these. ``membership_id`` is the
    key permission checks are resolved against, because roles are granted per
    organization rather than per user.
    """

    user: User
    organization_id: uuid.UUID
    membership_id: uuid.UUID
    #: Effective ``module.ACTION`` codes in this organization, resolved once
    #: per request by :func:`require_permission`. Empty when the principal was
    #: built without an authorization check (``CurrentPrincipal``), so callers
    #: must use :meth:`has_permission` rather than reading it as truth.
    permissions: frozenset[str] = frozenset()

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    def has_permission(self, module: str, action: PermissionAction) -> bool:
        """Whether the resolved permission set contains ``module.action``.

        This is a **read of an already-made decision**, not a new check: the
        set was loaded by ``require_permission`` while authorizing the route.
        It exists so a handler can ask a secondary question — "may they also
        see other people's records?" — without a second database round trip.
        """
        return f"{module}.{action.value}" in self.permissions


async def get_current_principal(user: CurrentUser, session: DbSession) -> Principal:
    """Bind the authenticated user to the request's tenant context.

    The organization comes from :func:`require_tenant_context`, which the ASGI
    middleware only populates after verifying membership — so by the time this
    runs, the organization has already been proven to belong to the caller.
    Membership is re-read here to obtain its id and to fail closed if it was
    revoked between the middleware and the handler.

    Raises:
        TenantContextError: 403, no organization could be established.
        NotAuthenticatedError: 403 via tenant context if membership vanished.
    """
    context: TenantContext = require_tenant_context()

    organizations = OrganizationRepository(session)
    membership = await organizations.get_membership(
        organization_id=context.organization_id, user_id=user.id
    )
    if membership is None or not membership.grants_access:
        logger.warning(
            "principal_membership_missing",
            user_id=str(user.id),
            organization_id=str(context.organization_id),
        )
        raise PermissionDeniedForOrganizationError

    return Principal(
        user=user,
        organization_id=context.organization_id,
        membership_id=membership.id,
    )


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def get_authorization_service(session: DbSession) -> AuthorizationService:
    return AuthorizationService(AuthorizationRepository(session))


AuthorizationServiceDep = Annotated[AuthorizationService, Depends(get_authorization_service)]


def require_permission(
    module: str, action: PermissionAction
) -> Callable[..., Awaitable[Principal]]:
    """Build a dependency enforcing ``module.action`` for the caller.

    Used as::

        @router.post("", dependencies=[Depends(require_permission("leads", CREATE))])

    or, when the handler needs the principal anyway::

        principal: Annotated[Principal, Depends(require_permission("leads", CREATE))]

    Authorization is evaluated on every request against the database. Nothing
    is trusted from the client, and the frontend's own permission state has no
    bearing on the outcome.
    """

    async def dependency(
        principal: CurrentPrincipal,
        authorization: AuthorizationServiceDep,
    ) -> Principal:
        # Resolved once and attached, rather than checked and thrown away.
        # The route's own check and any record-level question the handler asks
        # afterwards then run off the same snapshot — one query, and no window
        # in which the two could disagree.
        granted = await authorization.effective_permissions(principal.membership_id)
        if permission_code(module, action) not in granted:
            logger.info(
                "permission_denied",
                membership_id=str(principal.membership_id),
                required=permission_code(module, action),
            )
            raise PermissionDeniedError
        return replace(principal, permissions=frozenset(granted))

    return dependency


class JwtPrincipalResolver:
    """Implements ``app.core.tenant.PrincipalResolver`` for the ASGI middleware.

    The middleware runs before FastAPI's dependency system, so this opens its
    own short-lived session to look nothing up beyond token verification —
    membership is checked separately by the membership verifier.

    Never raises: an unauthenticated request is normal at this layer, and the
    401 is produced later by :func:`get_current_user`.
    """

    def __init__(self, issuer: TokenIssuer) -> None:
        self._issuer = issuer

    async def resolve(
        self, *, authorization: str | None, organization_header: uuid.UUID | None
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        if not authorization or not authorization.startswith(BEARER_PREFIX):
            return None, None
        token = authorization[len(BEARER_PREFIX) :].strip()
        if not token:
            return None, None
        try:
            claims = self._issuer.verify(token)
        except InvalidTokenError:
            return None, None
        return claims.user_id, claims.organization_id


class DatabaseMembershipVerifier:
    """Implements ``app.core.tenant.MembershipVerifier`` against PostgreSQL.

    Opens its own session because the middleware runs outside the request's
    dependency graph. The query is a single indexed count on
    ``organization_memberships``.

    The session factory is resolved lazily through a provider: middleware is
    constructed in the application factory, but the factory itself is only
    created during the lifespan startup.

    This deliberately runs **outside** any tenant scope. ``organization_
    memberships`` carries no RLS policy precisely because it must be readable
    while deciding what the caller's tenant scope should be.
    """

    def __init__(
        self, session_factory_provider: Callable[[], async_sessionmaker[AsyncSession]]
    ) -> None:
        self._session_factory_provider = session_factory_provider

    async def verify(self, *, organization_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
        if user_id is None:
            return False
        session_factory = self._session_factory_provider()
        async with session_factory() as session:
            repository = OrganizationRepository(session)
            return await repository.has_active_membership(
                organization_id=organization_id, user_id=user_id
            )


__all__ = [
    "AuthorizationServiceDep",
    "CurrentPrincipal",
    "CurrentUser",
    "DatabaseMembershipVerifier",
    "JwtPrincipalResolver",
    "NotAuthenticatedError",
    "PermissionDeniedForOrganizationError",
    "Principal",
    "get_current_principal",
    "get_current_user",
    "require_permission",
]
