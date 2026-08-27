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

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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

    ``eager_defaults`` makes SQLAlchemy fetch server-generated values (the
    ``created_at``/``updated_at`` defaults, and ``onupdate`` in particular) with
    a RETURNING clause on the INSERT or UPDATE itself. Without it those columns
    are left expired and are loaded lazily on first access — which raises
    ``MissingGreenlet`` under asyncio the moment a response schema reads them.
    PostgreSQL supports RETURNING, so this costs no extra round trip.
    """

    metadata = METADATA
    # SQLAlchemy declares __mapper_args__ as an instance attribute, so
    # ClassVar is rejected by the type checker. The dict is read once at
    # class definition and never mutated.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012


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


@asynccontextmanager
async def provisioning_scope(
    session: AsyncSession, organization_id: uuid.UUID
) -> AsyncIterator[None]:
    """Scope the open transaction to ``organization_id`` for provisioning writes.

    There is a narrow class of writes that name a tenant but happen *before*
    that tenant can have a request context: the rows created in the same
    transaction as the organization itself. Granting the new organization its
    product entitlements is the case that exists today.

    Such a write is rejected by the tenant policy — ``WITH CHECK`` compares
    ``organization_id`` against ``app.current_org_id``, which is either unset
    (bootstrap, registration) or still naming the *creating* organization. The
    row is legitimate; the setting simply has not caught up with it.

    The alternative would be to exempt the table from RLS, as
    ``platform.organizations`` and ``organization_memberships`` are. That is
    the right call for tables read while *establishing* context, but an
    entitlement is ordinary tenant data everywhere except this one moment, and
    dropping the policy would cost defence-in-depth for every later read.

    So the setting is moved to the organization being provisioned for the
    duration of the write and then put back. ``set_config(..., true)`` is
    transaction-local, so the previous value returns at the ``finally`` and
    could not outlive the transaction in any case.

    Only ever call this with an organization id the caller has just created or
    already proven it may act for: it is, by construction, a way to write a row
    the current context would otherwise be refused.
    """
    previous = await session.scalar(
        text("SELECT current_setting(:setting, true)"), {"setting": TENANT_SETTING}
    )
    await session.execute(
        text("SELECT set_config(:setting, :value, true)"),
        {"setting": TENANT_SETTING, "value": str(organization_id)},
    )
    try:
        yield
    finally:
        # A never-assigned setting reads as NULL; the policy maps '' to NULL
        # via NULLIF, so restoring the empty string reinstates "no tenant".
        await session.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": previous or ""},
        )


class RlsBypassedError(RuntimeError):
    """The runtime database role is exempt from row-level security."""


async def enforce_rls_is_not_bypassed(engine: AsyncEngine, settings: Settings) -> None:
    """Refuse to serve a deployed environment whose role ignores RLS.

    Superusers and ``BYPASSRLS`` roles are exempt from every policy, so tenant
    isolation silently does not apply to them: every query returns every
    organization's rows and the application layer is the only thing standing
    between one customer and another's data. In a multi-tenant product that is
    not a degraded mode, it is the whole guarantee gone, and nothing about the
    running system looks wrong.

    In development this stays a warning — the docker-compose role is the
    database owner and making a fresh clone refuse to boot would be hostile.
    Anywhere else it is fatal, because the failure is silent by nature: the
    only signal it ever produced was one line in a startup log, and a line in
    a log is not a control.

    That this needed to become an error is not theoretical. The same privilege
    hid a defect that made organization provisioning impossible under any
    correctly configured role, through an entire test suite and a CI pipeline
    (see ``tests/integration/test_provisioning_under_rls.py``).

    Raises:
        RlsBypassedError: outside development/test, when the role bypasses RLS.
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

    if not bypasses:
        return

    detail = (
        "The database role is a superuser or has BYPASSRLS, so row-level "
        "tenant isolation is NOT enforced on this connection. Connect as an "
        "ordinary role: CREATE ROLE <app> LOGIN NOSUPERUSER NOBYPASSRLS, "
        "owning its own database."
    )

    if settings.environment in ("development", "test"):
        logger.warning("rls_bypassed_by_database_role", detail=detail)
        return

    logger.error("rls_bypassed_by_database_role", environment=settings.environment, detail=detail)
    raise RlsBypassedError(
        f"Refusing to start with ENVIRONMENT={settings.environment}: {detail}"
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
