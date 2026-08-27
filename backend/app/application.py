"""FastAPI application factory.

All wiring lives here rather than in ``main.py`` so tests can build isolated
application instances with overridden settings.

Startup deliberately does **not** connect to PostgreSQL or Redis: both clients
are lazy, and dependency availability is reported by ``GET /health/ready``
rather than by refusing to boot. That keeps the container restartable while a
datastore is still coming up, and keeps ``/health`` honest about liveness.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router, root_router
from app.core.config import Settings, get_settings
from app.core.database import (
    create_engine,
    create_session_factory,
    dispose_engine,
    enforce_rls_is_not_bypassed,
)
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.redis import close_redis_client, create_redis_client
from app.core.request_context import REQUEST_ID_HEADER, RequestContextMiddleware
from app.core.tenant import (
    ORGANIZATION_HEADER,
    MembershipVerifier,
    PrincipalResolver,
    TenantContextMiddleware,
)
from app.platform.auth.dependencies import DatabaseMembershipVerifier, JwtPrincipalResolver
from app.platform.auth.security import TokenIssuer
from app.platform.documents.storage import build_storage

# Registers every models module on the shared metadata. Needed at runtime, not
# only for migrations: SQLAlchemy resolves a foreign key's target table lazily
# by name, so a model nothing else imports leaves any mapper that references it
# unable to configure — ``leads.campaign_id`` -> ``crm.campaigns`` being the
# case that first exposed this.
from app.schema import target_metadata as _registered_metadata  # noqa: F401

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage datastore client lifecycles across application startup/shutdown."""
    settings: Settings = app.state.settings

    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = create_redis_client(settings)
    # Built once: constructing a boto3 client parses configuration and
    # builds a signer, and the client is thread-safe for the metadata calls
    # the documents module makes. ``None`` when no bucket is configured,
    # which the attachment routes surface as 503 rather than a 500.
    app.state.object_storage = build_storage(settings)

    logger.info(
        "application_started",
        service=settings.app_name,
        environment=settings.environment,
        api_prefix=settings.api_prefix,
    )

    # A deployment whose role bypasses RLS has no tenant isolation at all.
    # Fatal outside development, where it is only a warning.
    await enforce_rls_is_not_bypassed(engine, settings)

    try:
        yield
    finally:
        await close_redis_client(app.state.redis)
        await dispose_engine(engine)
        logger.info("application_stopped", service=settings.app_name)


def create_app(
    settings: Settings | None = None,
    *,
    membership_verifier: MembershipVerifier | None = None,
    principal_resolver: PrincipalResolver | None = None,
) -> FastAPI:
    """Build and configure the FastAPI application.

    Args:
        settings: optional override, primarily for tests. Defaults to the
            validated process-wide settings singleton.
        membership_verifier: resolves whether a caller may act within the
            requested organization. Defaults to a database-backed verifier
            bound to the application's own session factory.
        principal_resolver: extracts the authenticated user from the request's
            credentials. Defaults to JWT verification.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        summary="S3K Enterprise Platform — Shared Platform + S3K CRM modular monolith",
        debug=settings.debug,
        docs_url=settings.docs_url,
        redoc_url=None,
        openapi_url=settings.openapi_url,
        lifespan=lifespan,
    )

    app.state.settings = settings

    # Built once: Ed25519 signing is cheap, but key parsing is not, and the
    # development fallback must generate exactly one ephemeral keypair.
    token_issuer = TokenIssuer(settings)
    app.state.token_issuer = token_issuer

    register_exception_handlers(app)

    # Establishes the tenant scope for every non-exempt request. Added as raw
    # ASGI middleware so the context variable is visible to the endpoint task.
    # The session factory is reached through a lambda because it does not exist
    # until the lifespan runs.
    app.add_middleware(
        TenantContextMiddleware,
        membership_verifier=membership_verifier
        or DatabaseMembershipVerifier(lambda: app.state.session_factory),
        principal_resolver=principal_resolver or JwtPrincipalResolver(token_issuer),
    )

    # Added *after* the tenant middleware, so it wraps it: the correlation id
    # must already be bound while tenant resolution runs, or its warnings — a
    # forged organization header being the one that matters — cannot be traced
    # back to the request that produced them. It is also what stamps
    # ``request_id`` on every audit record.
    app.add_middleware(RequestContextMiddleware)

    # CORS must be the outermost middleware (added last) so preflight OPTIONS
    # is answered with Access-Control-* headers before any other layer runs.
    # ``allow_credentials`` is required so the refresh cookie travels, which is
    # exactly why the origins must be enumerated: the CORS specification
    # forbids credentials alongside a wildcard origin (doc 13 "API Security").
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                ORGANIZATION_HEADER,
                REQUEST_ID_HEADER,
            ],
            # So a browser client can read the correlation id back off a failed
            # response and quote it in a bug report.
            expose_headers=[REQUEST_ID_HEADER],
        )

    app.include_router(root_router)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app
