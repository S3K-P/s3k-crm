"""Readiness against real PostgreSQL and Redis.

Requires the local infrastructure:

    docker compose up -d

Skipped automatically when ``backend/.env`` has not been configured. Run with
``uv run pytest -m integration``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import ConfigurationError, Settings, get_settings

pytestmark = pytest.mark.integration


@pytest.fixture
def live_settings() -> Settings:
    try:
        return get_settings()
    except ConfigurationError:  # pragma: no cover - environment dependent
        pytest.skip("backend/.env is not configured; see .env.example")


@pytest.fixture
def live_client(live_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(live_settings)) as client:
        yield client


def test_readiness_reports_both_dependencies_up(live_client: TestClient) -> None:
    response = live_client.get("/health/ready")

    assert response.status_code == 200, (
        f"dependencies not reachable: {response.json().get('dependencies')}. "
        "Is `docker compose up -d` running?"
    )
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["dependencies"] == {"database": "up", "redis": "up"}


def test_database_round_trip(live_client: TestClient) -> None:
    """Proves the asyncpg driver and pool actually execute a statement."""
    import asyncio

    from sqlalchemy import text

    from app.core.database import create_engine

    settings = live_client.app.state.settings  # type: ignore[attr-defined]

    async def _query() -> int:
        engine = create_engine(settings)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text("SELECT 1"))
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    assert asyncio.run(_query()) == 1
