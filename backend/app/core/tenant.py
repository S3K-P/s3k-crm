"""Per-request tenant context (ADR-007, doc 13 "Tenant Isolation Enforcement").

The context carries the organization every query in a request is scoped to. It
is stored in a :mod:`contextvars` variable so the database session, the logger
and background code can all read it without threading it through every call.

**The security rule this module exists to enforce:** a browser-supplied
organization id is an *assertion*, never an authorization. It is only accepted
after a :class:`MembershipVerifier` confirms the authenticated principal
belongs to that organization. Until Phase 1 delivers authentication and
memberships, the default verifier is :class:`DenyAllMembershipVerifier`, which
refuses every request — the system fails **closed**, not open.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import structlog
from fastapi import status
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)

#: Header the frontend uses to select the active organization (doc 13).
ORGANIZATION_HEADER = "X-Organization-Id"


@dataclass(frozen=True, slots=True)
class TenantContext:
    """The validated tenant scope of the current request."""

    organization_id: uuid.UUID
    user_id: uuid.UUID | None = None

    def __str__(self) -> str:  # pragma: no cover - debugging aid
        return f"TenantContext(org={self.organization_id}, user={self.user_id})"


_tenant_context: ContextVar[TenantContext | None] = ContextVar("tenant_context", default=None)


class TenantContextError(AppError):
    """The request could not be scoped to an organization."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "tenant_context_required"
    message = "The request could not be attributed to an organization you belong to."


def get_tenant_context() -> TenantContext | None:
    """Return the current tenant context, or ``None`` outside a scoped request."""
    return _tenant_context.get()


def require_tenant_context() -> TenantContext:
    """Return the current tenant context or fail.

    Raises:
        TenantContextError: when no organization has been established. Callers
            that reach the database must never fall back to "no filter".
    """
    context = _tenant_context.get()
    if context is None:
        raise TenantContextError
    return context


def set_tenant_context(context: TenantContext | None) -> Token[TenantContext | None]:
    """Bind ``context`` for the current task. Returns a token for :func:`reset`."""
    return _tenant_context.set(context)


def reset_tenant_context(token: Token[TenantContext | None]) -> None:
    """Restore whatever context was bound before :func:`set_tenant_context`."""
    _tenant_context.reset(token)


@runtime_checkable
class MembershipVerifier(Protocol):
    """Confirms that a principal may act within an organization.

    Implemented in Phase 1 by the Platform ``organizations`` module. The
    protocol lives here so the tenant middleware never imports a Platform
    module directly.
    """

    async def verify(self, *, organization_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
        """Return ``True`` only if ``user_id`` is a member of ``organization_id``."""
        ...


@runtime_checkable
class PrincipalResolver(Protocol):
    """Extracts the authenticated user id from a request's credentials.

    Kept behind a protocol for the same reason as :class:`MembershipVerifier`:
    ``app.core`` may not import ``app.platform``, and token verification is a
    Platform concern. The application factory injects the real implementation.
    """

    async def resolve(
        self, *, authorization: str | None, organization_header: uuid.UUID | None
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        """Return ``(user_id, organization_id_from_token)``.

        Both are ``None`` when the request carries no usable credentials.
        Returning ``None`` must never raise — an unauthenticated request is a
        normal condition here, and the 401 is raised later by the endpoint's
        authentication dependency.
        """
        ...


class DenyAllMembershipVerifier:
    """Fallback verifier: rejects everything.

    Used when no real verifier is injected — for example in a unit test that
    builds an application without a database. Accepting the organization header
    on trust would let any caller read any tenant's data, so the safe default
    is to deny.
    """

    async def verify(self, *, organization_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
        return False


class AnonymousPrincipalResolver:
    """Fallback resolver: every request is unauthenticated."""

    async def resolve(
        self, *, authorization: str | None, organization_header: uuid.UUID | None
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        return None, None


class TenantContextMiddleware:
    """Establish the tenant context for each request.

    Pure ASGI rather than ``BaseHTTPMiddleware`` so the context variable is set
    in the same task that runs the endpoint — ``BaseHTTPMiddleware`` runs the
    handler in a separate task and the contextvar would not propagate.

    Paths in ``exempt_paths`` bypass tenant resolution entirely: health probes
    must answer before any tenant exists.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        membership_verifier: MembershipVerifier | None = None,
        principal_resolver: PrincipalResolver | None = None,
        exempt_paths: frozenset[str] = frozenset({"/health", "/health/ready"}),
    ) -> None:
        self.app = app
        self.membership_verifier: MembershipVerifier = (
            membership_verifier or DenyAllMembershipVerifier()
        )
        self.principal_resolver: PrincipalResolver = (
            principal_resolver or AnonymousPrincipalResolver()
        )
        self.exempt_paths = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        context = await self._resolve(scope)
        token = set_tenant_context(context)
        structlog.contextvars.bind_contextvars(
            tenant_id=str(context.organization_id) if context else None,
            user_id=str(context.user_id) if context and context.user_id else None,
        )
        try:
            await self.app(scope, receive, send)
        finally:
            reset_tenant_context(token)
            structlog.contextvars.unbind_contextvars("tenant_id", "user_id")

    async def _resolve(self, scope: Scope) -> TenantContext | None:
        """Resolve and validate the organization for this request.

        Returns ``None`` when no trustworthy organization can be established.
        Endpoints that need one call :func:`require_tenant_context`, which
        raises 403 — resolution failure is never silently treated as "all
        tenants".

        The header is only ever an *assertion* of which organization the caller
        wants. It is honoured solely after the membership verifier confirms the
        authenticated user actually belongs to it, so forging the header gains
        an attacker nothing.
        """
        requested: uuid.UUID | None = None
        raw = _header_value(scope, ORGANIZATION_HEADER)
        if raw is not None:
            try:
                requested = uuid.UUID(raw)
            except ValueError:
                logger.warning("tenant_header_malformed", header=ORGANIZATION_HEADER)
                return None

        user_id, token_organization_id = await self.principal_resolver.resolve(
            authorization=_header_value(scope, "Authorization"),
            organization_header=requested,
        )
        if user_id is None:
            return None

        # Fall back to the organization the session was issued for when the
        # client does not assert one.
        organization_id = requested or token_organization_id
        if organization_id is None:
            return None

        permitted = await self.membership_verifier.verify(
            organization_id=organization_id, user_id=user_id
        )
        if not permitted:
            logger.warning(
                "tenant_membership_denied",
                organization_id=str(organization_id),
                user_id=str(user_id),
                reason="no active membership for the requested organization",
            )
            return None

        return TenantContext(organization_id=organization_id, user_id=user_id)


def _header_value(scope: Scope, name: str) -> str | None:
    """Case-insensitive header lookup against the raw ASGI scope."""
    wanted = name.lower().encode("latin-1")
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for key, value in headers:
        if key.lower() == wanted:
            return str(value.decode("latin-1"))
    return None
