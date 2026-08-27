"""Startup refuses a deployed environment whose database role bypasses RLS.

A superuser (or any ``BYPASSRLS`` role) is exempt from every tenant policy, so
running as one removes multi-tenant isolation entirely while leaving nothing
visibly wrong. This used to be a single warning line at startup, which is not a
control — it produced no failure, blocked no deploy, and in practice hid a
defect that made organization provisioning impossible under a correct role
through an entire test suite and CI pipeline.

Development keeps the warning: the docker-compose role is the database owner,
and a fresh clone that refuses to boot would be hostile for no security gain
on a laptop with one tenant in it.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.database import RlsBypassedError, enforce_rls_is_not_bypassed
from tests.conftest import TEST_JWT_PRIVATE_KEY, TEST_JWT_PUBLIC_KEY

DEPLOYED = ("staging", "production")
LOCAL = ("development", "test")


class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar(self) -> object:
        return self._value


class _FakeConnection:
    def __init__(self, bypasses: bool | None) -> None:
        self._bypasses = bypasses

    async def __aenter__(self) -> _FakeConnection:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, *_: object, **__: object) -> _FakeResult:
        if self._bypasses is None:
            msg = "database is not accepting connections"
            raise ConnectionRefusedError(msg)
        return _FakeResult(self._bypasses)


class _FakeEngine:
    """Stands in for an ``AsyncEngine``; only ``connect()`` is exercised."""

    def __init__(self, bypasses: bool | None) -> None:
        self._bypasses = bypasses

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self._bypasses)


def _settings(environment: str) -> Settings:
    return Settings(
        environment=environment,  # type: ignore[arg-type]
        # Explicit rather than inherited from the developer's .env, which sets
        # DEBUG=true and would fail the production validator.
        debug=False,
        db_echo=False,
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        jwt_private_key=TEST_JWT_PRIVATE_KEY,
        jwt_public_key=TEST_JWT_PUBLIC_KEY,
        storage_bucket="bucket",
        storage_access_key_id="key",
        storage_secret_access_key="secret",
    )


@pytest.mark.parametrize("environment", DEPLOYED)
async def test_a_bypassing_role_aborts_startup_in_a_deployed_environment(
    environment: str,
) -> None:
    with pytest.raises(RlsBypassedError) as raised:
        await enforce_rls_is_not_bypassed(
            _FakeEngine(bypasses=True),  # type: ignore[arg-type]
            _settings(environment),
        )

    message = str(raised.value)
    assert environment in message
    # The message must say what to do about it, not merely that it happened.
    assert "NOBYPASSRLS" in message


@pytest.mark.parametrize("environment", LOCAL)
async def test_a_bypassing_role_is_only_a_warning_locally(environment: str) -> None:
    await enforce_rls_is_not_bypassed(
        _FakeEngine(bypasses=True),  # type: ignore[arg-type]
        _settings(environment),
    )


@pytest.mark.parametrize("environment", (*DEPLOYED, *LOCAL))
async def test_an_ordinary_role_starts_everywhere(environment: str) -> None:
    await enforce_rls_is_not_bypassed(
        _FakeEngine(bypasses=False),  # type: ignore[arg-type]
        _settings(environment),
    )


@pytest.mark.parametrize("environment", (*DEPLOYED, *LOCAL))
async def test_an_unreachable_database_does_not_abort_startup(environment: str) -> None:
    """Liveness must stay honest while PostgreSQL is still coming up.

    The check cannot distinguish "misconfigured" from "not up yet", and the
    application deliberately boots without its datastores so the container
    stays restartable. Readiness reports the outage; this must not pre-empt it.
    """
    await enforce_rls_is_not_bypassed(
        _FakeEngine(bypasses=None),  # type: ignore[arg-type]
        _settings(environment),
    )
