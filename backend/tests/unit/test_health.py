"""Tests for the liveness and readiness endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core import database
from app.core import redis as redis_module


def test_health_returns_200_and_structured_body(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "s3k-crm-backend",
        "status": "healthy",
        "environment": "test",
    }


def test_health_does_not_touch_dependencies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liveness must answer even when PostgreSQL and Redis are both down."""

    async def _fail(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("liveness must not probe dependencies")

    monkeypatch.setattr(database, "check_database_connection", _fail)
    monkeypatch.setattr(redis_module, "check_redis_connection", _fail)

    assert client.get("/health").status_code == 200


def test_health_body_exposes_no_infrastructure_detail(client: TestClient) -> None:
    body = client.get("/health").text.lower()
    assert "postgresql" not in body
    assert "redis" not in body
    assert "password" not in body


def test_readiness_returns_200_when_both_dependencies_are_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _ok(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(database, "check_database_connection", _ok)
    monkeypatch.setattr(redis_module, "check_redis_connection", _ok)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "service": "s3k-crm-backend",
        "status": "ready",
        "environment": "test",
        "dependencies": {"database": "up", "redis": "up"},
    }


def test_readiness_returns_503_when_database_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _ok(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def _down(*_args: Any, **_kwargs: Any) -> None:
        raise ConnectionRefusedError(
            "connection to server at 10.0.0.5 port 5432 failed: password authentication failed"
        )

    monkeypatch.setattr(database, "check_database_connection", _down)
    monkeypatch.setattr(redis_module, "check_redis_connection", _ok)

    response = client.get("/health/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["dependencies"] == {"database": "down", "redis": "up"}

    # The driver error must never reach the client.
    body = response.text
    assert "password" not in body
    assert "10.0.0.5" not in body
    assert "5432" not in body


def test_readiness_returns_503_when_redis_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _ok(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def _down(*_args: Any, **_kwargs: Any) -> None:
        raise ConnectionError("Error 111 connecting to redis:6379. Connection refused.")

    monkeypatch.setattr(database, "check_database_connection", _ok)
    monkeypatch.setattr(redis_module, "check_redis_connection", _down)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"] == {"database": "up", "redis": "down"}


def test_readiness_returns_503_when_both_dependencies_are_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _down(*_args: Any, **_kwargs: Any) -> None:
        raise ConnectionError("unavailable")

    monkeypatch.setattr(database, "check_database_connection", _down)
    monkeypatch.setattr(redis_module, "check_redis_connection", _down)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"] == {"database": "down", "redis": "down"}
