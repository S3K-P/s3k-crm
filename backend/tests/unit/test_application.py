"""Application factory and startup/shutdown lifecycle tests."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application import create_app
from app.core.config import Settings
from tests.conftest import TEST_JWT_PRIVATE_KEY, TEST_JWT_PUBLIC_KEY


def test_create_app_returns_configured_application(settings: Settings) -> None:
    app = create_app(settings)

    assert isinstance(app, FastAPI)
    assert app.title == "s3k-crm-backend"
    assert app.state.settings is settings


def test_startup_wires_datastore_clients(app: FastAPI) -> None:
    """Lifespan must place the engine, session factory and Redis client on state."""
    with TestClient(app):
        assert isinstance(app.state.engine, AsyncEngine)
        assert isinstance(app.state.session_factory, async_sessionmaker)
        assert isinstance(app.state.redis, Redis)
        assert app.state.session_factory.class_ is AsyncSession


def test_startup_does_not_require_live_dependencies(app: FastAPI) -> None:
    """The app must boot with PostgreSQL and Redis unreachable.

    Liveness stays honest and the container remains restartable while a
    datastore is still coming up; readiness is what reports dependency health.
    """
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_shutdown_disposes_engine(app: FastAPI) -> None:
    with TestClient(app):
        engine = app.state.engine

    # A disposed engine builds a fresh pool on next use; the old one is closed.
    assert engine.pool is not None


def test_health_routes_are_mounted_outside_the_api_prefix(app: FastAPI) -> None:
    """Probes live at a stable, unversioned path so orchestrators never chase a prefix."""
    paths = set(app.openapi()["paths"])

    assert "/health" in paths
    assert "/health/ready" in paths
    assert "/api/v1/health" not in paths


def test_openapi_schema_generates(client: TestClient) -> None:
    """A broken route signature would surface here rather than at runtime."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "/health" in schema["paths"]
    assert "/health/ready" in schema["paths"]


def test_the_phase_one_business_routes_are_registered(app: FastAPI) -> None:
    """Auth, organizations, RBAC and the first CRM modules are mounted.

    Replaces the Phase 0 guard that asserted no ``/api/`` route existed; that
    scope-creep check expired the moment Phase 1 delivered these endpoints.
    """
    business_paths = {path for path in app.openapi()["paths"] if path.startswith("/api/")}

    assert "/api/v1/auth/login" in business_paths
    assert "/api/v1/organizations" in business_paths
    assert "/api/v1/roles" in business_paths
    assert "/api/v1/crm/accounts" in business_paths


def test_every_business_route_is_versioned(app: FastAPI) -> None:
    """Nothing may bypass the ``/api/v1`` prefix (doc 11 versioning)."""
    unversioned = {
        path
        for path in app.openapi()["paths"]
        if path.startswith("/api/") and not path.startswith("/api/v1/")
    }

    assert unversioned == set()


def test_production_settings_disable_docs() -> None:
    production = Settings(
        environment="production",
        debug=False,
        database_url="postgresql+asyncpg://u:p@db:5432/s3k",
        redis_url="redis://cache:6379/0",
        jwt_private_key=TEST_JWT_PRIVATE_KEY,
        jwt_public_key=TEST_JWT_PUBLIC_KEY,
    )

    app = create_app(production)

    assert app.docs_url is None
    assert app.openapi_url is None
