"""Async SQLAlchemy 2.0 engine, session factory and FastAPI session dependency.

ADR-005 (PostgreSQL 18) and ADR-006 (SQLAlchemy 2.0 async + Alembic).

The engine and session factory are created during application startup and
disposed on shutdown, so no connection is opened at import time.

**Tenant scoping.** ``get_db_session`` opens a transaction and applies the
current :class:`~app.core.tenant.TenantContext` to it with ``set_config(...,
true)`` — the function form of ``SET LOCAL``, so the setting is scoped to the
transaction and cannot leak to the next request that borrows the same pooled
connection. RLS policies read that setting (:mod:`app.core.rls`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings
from app.core.models import METADATA, TENANT_SETTING
from app.core.tenant import TenantContext, get_tenant_context

logger = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    """Declarative base shared by every Platform and CRM model.

    A single ``MetaData`` for the whole modular monolith is intentional: one
    database, one migration history (ADR-001, ADR-007). ``migrations/env.py``
    targets this exact metadata via :mod:`app.core.metadata`.
    """

    metadata = METADATA


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine with pooling driven by configuration."""
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=settings.db_pool_pre_ping,
        future=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the async session factory bound to ``engine``."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def dispose_engine(engine: AsyncEngine) -> None:
    """Close all pooled connections during shutdown."""
    await engine.dispose()
    logger.info("database_engine_disposed")


async def check_database_connection(engine: AsyncEngine) -> None:
    """Probe PostgreSQL connectivity.

    Raises:
        Exception: any driver or connection error, surfaced to the readiness
            endpoint which converts it into a safe 503 response.
    """
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def apply_tenant_context(
    connection: AsyncConnection | AsyncSession, context: TenantContext
) -> None:
    """Scope the current transaction to ``context``'s organization.

    ``set_config(..., is_local => true)`` is the callable form of ``SET
    LOCAL``: PostgreSQL discards it at transaction end, so a pooled connection
    can never carry one tenant's scope into another tenant's request.
    """
    await connection.execute(
        text("SELECT set_config(:setting, :value, true)"),
        {"setting": TENANT_SETTING, "value": str(context.organization_id)},
    )


async def warn_if_rls_is_bypassed(engine: AsyncEngine) -> None:
    """Log loudly when the runtime role ignores RLS.

    Superusers and ``BYPASSRLS`` roles are exempt from every policy, so tenant
    isolation silently does not apply to them. That is acceptable for local
    development but is a serious misconfiguration anywhere else.
    """
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
            bypasses = bool(result.scalar())
    except Exception as exc:  # database not up yet; readiness reports it
        logger.info("rls_privilege_check_skipped", error=str(exc))
        return

    if bypasses:
        logger.warning(
            "rls_bypassed_by_database_role",
            detail=(
                "The database role is a superuser or has BYPASSRLS, so row-level "
                "tenant isolation is NOT enforced on this connection. Use an "
                "ordinary role outside local development."
            ),
        )


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a tenant-scoped, transactional session.

    The session runs inside a transaction so ``SET LOCAL``-style tenant scoping
    applies. It commits on success and rolls back on any exception. Requests
    without a tenant context still get a session, but with no organization
    setting applied — RLS then matches zero rows, which is the intended
    fail-closed behaviour.
    """
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    context = get_tenant_context()

    async with session_factory() as session, session.begin():
        if context is not None:
            await apply_tenant_context(session, context)
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
