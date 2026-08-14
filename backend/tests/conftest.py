"""Shared pytest fixtures.

The unit suite runs with no PostgreSQL or Redis available: settings are built
explicitly here rather than read from the developer's ``.env``, and both
datastore clients are lazy, so the lifespan never opens a socket.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import Settings

TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/s3k_test"
TEST_REDIS_URL = "redis://localhost:6379/15"


def _generate_test_keypair() -> tuple[str, str]:
    """An Ed25519 keypair for tests.

    Generated at import time rather than checked in: a PEM private key in the
    repository would be indistinguishable from a leaked credential, and tests
    have no need for a stable key.
    """
    private = ed25519.Ed25519PrivateKey.generate()
    return (
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode(),
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode(),
    )


TEST_JWT_PRIVATE_KEY, TEST_JWT_PUBLIC_KEY = _generate_test_keypair()


@pytest.fixture
def settings() -> Settings:
    """Deterministic settings independent of the local environment."""
    return Settings(
        app_name="s3k-crm-backend",
        environment="test",
        debug=False,
        api_prefix="/api/v1",
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
        log_level="WARNING",
        log_json=False,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """A freshly built application instance."""
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Test client that runs the real lifespan (engine and Redis client setup)."""
    with TestClient(app) as test_client:
        yield test_client
