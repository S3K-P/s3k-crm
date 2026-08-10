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

from app.api.router import api_router, root_router
from app.core.config import Settings, get_settings
from app.core.database import (
    create_engine,
    create_session_factory,
    dispose_engine,
    warn_if_rls_is_bypassed,
)
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.redis import close_redis_client, create_redis_client
from app.core.tenant import MembershipVerifier, TenantContextMiddleware

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage datastore client lifecycles across application startup/shutdown."""
    settings: Settings = app.state.settings

    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = create_redis_client(settings)

    logger.info(
        "application_started",
        service=settings.app_name,
        environment=settings.environment,
        api_prefix=settings.api_prefix,
    )

    # Surfaces a misconfigured deployment where RLS would silently not apply.
    await warn_if_rls_is_bypassed(engine)

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
) -> FastAPI:
    """Build and configure the FastAPI application.

    Args:
        settings: optional override, primarily for tests. Defaults to the
            validated process-wide settings singleton.
        membership_verifier: resolves whether a caller may act within the
            requested organization. Defaults to the deny-all implementation
            until Phase 1 delivers authentication and memberships.
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

    register_exception_handlers(app)

    # Establishes the tenant scope for every non-exempt request. Added as raw
    # ASGI middleware so the context variable is visible to the endpoint task.
    app.add_middleware(TenantContextMiddleware, membership_verifier=membership_verifier)

    app.include_router(root_router)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app
