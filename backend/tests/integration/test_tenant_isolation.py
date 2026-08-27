"""Tenant isolation proven against real PostgreSQL RLS (P0-W02-QA-02).

This is the mandatory Phase 0 gate from ``13-SECURITY-AND-TENANT-ISOLATION.md``:
organization A must not be able to read organization B's rows. It is
deliberately **not** mocked — the guarantee lives in the database, so only the
database can demonstrate it.

Superusers and ``BYPASSRLS`` roles ignore every policy, and the local
development role is a superuser. These tests therefore provision their own
ordinary role and connect as it; running them as the owner would pass
vacuously while proving nothing.

Requires ``docker compose up -d`` and ``alembic upgrade head``.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.config import ConfigurationError, Settings, get_settings
from app.core.models import TENANT_SETTING

pytestmark = pytest.mark.integration

PROBE = 'platform."tenant_isolation_probe"'
TEST_ROLE = "s3k_rls_probe_role"

ORG_A = uuid.UUID("aaaaaaaa-0000-7000-8000-000000000001")
ORG_B = uuid.UUID("bbbbbbbb-0000-7000-8000-000000000002")


@pytest.fixture(scope="module")
def settings() -> Settings:
    try:
        return get_settings()
    except ConfigurationError:  # pragma: no cover - environment dependent
        pytest.skip("backend/.env is not configured; see .env.example")


@pytest_asyncio.fixture
async def admin_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Owner connection used to seed data and manage the test role."""
    engine = create_async_engine(settings.database_url, poolclass=None)
    try:
        async with engine.connect() as connection:
            try:
                await connection.execute(text(f"SELECT 1 FROM {PROBE} LIMIT 1"))
            except ProgrammingError:  # pragma: no cover - migration not applied
                pytest.skip("probe table missing; run `uv run alembic upgrade head`")
        yield engine
    finally:
        await engine.dispose()


#: Statements that strip every privilege this file grants the probe role, in
#: the order that lets the role finally be dropped.
#:
#: ``DROP OWNED BY`` is the obvious tool and the one this used to reach for,
#: but PostgreSQL 16+ requires *membership* in the target role to run it, and
#: CREATEROLE alone does not confer that. It therefore failed in teardown,
#: leaving a role that still held grants -- and ``DROP ROLE IF EXISTS`` is a
#: no-op only when the role is *absent*, so the next run's setup died on a
#: dependency error and every subsequent run failed identically until someone
#: cleaned up by hand. Revoking exactly what was granted needs no privilege the
#: grantor lacks.
def _role_reset_statements() -> tuple[str, ...]:
    statements: list[str] = []
    statements.append(f"REVOKE ALL ON {PROBE} FROM {TEST_ROLE}")
    statements.append(f"REVOKE USAGE ON SCHEMA platform FROM {TEST_ROLE}")

    statements.append(f"DROP ROLE {TEST_ROLE}")
    return tuple(statements)


async def _drop_probe_role_if_present(connection: AsyncConnection) -> None:
    """Remove the probe role and its grants, whether or not it exists."""
    for statement in _role_reset_statements():
        await connection.execute(
            text(
                "DO $$ BEGIN "
                f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{TEST_ROLE}') "
                f"THEN EXECUTE '{statement}'; END IF; END $$"
            )
        )

@pytest_asyncio.fixture
async def tenant_engine(
    admin_engine: AsyncEngine, settings: Settings
) -> AsyncIterator[AsyncEngine]:
    """An engine connected as an ordinary (RLS-subject) role.

    Created per test with a fresh password so nothing durable is left behind
    and no credential is ever written to disk.
    """
    # token_hex is [0-9a-f] only, so inlining it into DDL is injection-safe.
    # CREATE ROLE is DDL and cannot accept bind parameters.
    password = secrets.token_hex(24)

    async with admin_engine.begin() as connection:
        # An interrupted run leaves the role behind, still holding grants.
        await _drop_probe_role_if_present(connection)
        await connection.execute(
            text(f"CREATE ROLE {TEST_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'")
        )
        await connection.execute(text(f"GRANT USAGE ON SCHEMA platform TO {TEST_ROLE}"))
        await connection.execute(
            text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {PROBE} TO {TEST_ROLE}")
        )

    url = make_url(settings.database_url).set(username=TEST_ROLE, password=password)
    engine = create_async_engine(url)
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin_engine.begin() as connection:
            await _drop_probe_role_if_present(connection)


@pytest_asyncio.fixture
async def seeded(admin_engine: AsyncEngine) -> AsyncIterator[None]:
    """Two rows for organization A, one for organization B.

    Seeded one organization at a time, each under its own tenant scope. The
    probe table is RLS-FORCEd, and the policy's ``WITH CHECK`` admits only rows
    matching the *current* setting -- so a single statement inserting rows for
    two organizations is refused outright, and an unscoped one is refused for
    every row. This used to run as a superuser, for which no policy applies at
    all; against an ordinary role the seeding has to obey the same rule the
    tests then go on to verify.
    """
    rows = {
        ORG_A: ("org-a-first", "org-a-second"),
        ORG_B: ("org-b-secret",),
    }

    async with admin_engine.begin() as connection:
        for organization_id, payloads in rows.items():
            await connection.execute(
                text("SELECT set_config(:setting, :value, true)"),
                {"setting": TENANT_SETTING, "value": str(organization_id)},
            )
            for payload in payloads:
                await connection.execute(
                    text(
                        f"INSERT INTO {PROBE} (organization_id, payload) "
                        "VALUES (:org, :payload)"
                    ),
                    {"org": organization_id, "payload": payload},
                )
    yield
    async with admin_engine.begin() as connection:
        for organization_id in rows:
            await connection.execute(
                text("SELECT set_config(:setting, :value, true)"),
                {"setting": TENANT_SETTING, "value": str(organization_id)},
            )
            await connection.execute(
                text(f"DELETE FROM {PROBE} WHERE organization_id = :org"),
                {"org": organization_id},
            )


async def _scoped_payloads(engine: AsyncEngine, organization_id: uuid.UUID | None) -> list[str]:
    """Read the probe table with the tenant setting applied, as RLS sees it."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        if organization_id is not None:
            await connection.execute(
                text("SELECT set_config(:setting, :value, true)"),
                {"setting": TENANT_SETTING, "value": str(organization_id)},
            )
        result = await connection.execute(text(f"SELECT payload FROM {PROBE} ORDER BY payload"))
        payloads = [row[0] for row in result]
        await transaction.rollback()
    return payloads


# --- the gate ---------------------------------------------------------------


async def test_the_test_role_is_actually_subject_to_rls(
    tenant_engine: AsyncEngine,
) -> None:
    """Guards the guard: if this role could bypass RLS, every test below lies."""
    async with tenant_engine.connect() as connection:
        result = await connection.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
        assert result.scalar() is False


async def test_organization_a_sees_only_its_own_rows(
    tenant_engine: AsyncEngine, seeded: None
) -> None:
    payloads = await _scoped_payloads(tenant_engine, ORG_A)

    assert payloads == ["org-a-first", "org-a-second"]


async def test_organization_a_cannot_read_organization_b_rows(
    tenant_engine: AsyncEngine, seeded: None
) -> None:
    """The headline guarantee: cross-organization reads return nothing."""
    payloads = await _scoped_payloads(tenant_engine, ORG_A)

    assert "org-b-secret" not in payloads


def _assert_disjoint(a: list[str], b: list[str]) -> None:
    assert set(a).isdisjoint(set(b))


async def test_each_organization_sees_a_disjoint_row_set(
    tenant_engine: AsyncEngine, seeded: None
) -> None:
    from_a = await _scoped_payloads(tenant_engine, ORG_A)
    from_b = await _scoped_payloads(tenant_engine, ORG_B)

    assert from_b == ["org-b-secret"]
    _assert_disjoint(from_a, from_b)


async def test_no_tenant_context_returns_zero_rows(
    tenant_engine: AsyncEngine, seeded: None
) -> None:
    """Fail closed: an unscoped query must not fall back to "all tenants"."""
    payloads = await _scoped_payloads(tenant_engine, None)

    assert payloads == []


async def test_tenant_scope_does_not_leak_across_transactions(
    tenant_engine: AsyncEngine, seeded: None
) -> None:
    """``set_config(..., true)`` is transaction-local, so a reused pooled
    connection must not inherit the previous request's organization."""
    async with tenant_engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": str(ORG_A)},
        )
        scoped = (await connection.execute(text(f"SELECT count(*) FROM {PROBE}"))).scalar()
        await transaction.rollback()

        # Same physical connection, new transaction, no scope applied.
        transaction = await connection.begin()
        unscoped = (await connection.execute(text(f"SELECT count(*) FROM {PROBE}"))).scalar()
        await transaction.rollback()

    assert scoped == 2
    assert unscoped == 0


async def test_writing_into_another_organization_is_rejected(
    tenant_engine: AsyncEngine, seeded: None
) -> None:
    """WITH CHECK stops a tenant planting rows in someone else's scope."""
    with pytest.raises(DBAPIError):
        async with tenant_engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config(:setting, :value, true)"),
                {"setting": TENANT_SETTING, "value": str(ORG_A)},
            )
            await connection.execute(
                text(f"INSERT INTO {PROBE} (organization_id, payload) VALUES (:b, 'smuggled')"),
                {"b": ORG_B},
            )


async def test_writing_into_own_organization_is_allowed(
    tenant_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    async with tenant_engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": str(ORG_A)},
        )
        await connection.execute(
            text(f"INSERT INTO {PROBE} (organization_id, payload) VALUES (:a, 'mine')"),
            {"a": ORG_A},
        )

    payloads = await _scoped_payloads(tenant_engine, ORG_A)
    assert "mine" in payloads

    async with admin_engine.begin() as connection:
        await connection.execute(
            text(f"DELETE FROM {PROBE} WHERE organization_id = :a"), {"a": ORG_A}
        )


async def test_deleting_another_organizations_row_affects_nothing(
    tenant_engine: AsyncEngine, seeded: None
) -> None:
    async with tenant_engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": str(ORG_A)},
        )
        result = await connection.execute(
            text(f"DELETE FROM {PROBE} WHERE payload = 'org-b-secret'")
        )
        assert result.rowcount == 0

    # Organization B's row is still there.
    assert await _scoped_payloads(tenant_engine, ORG_B) == ["org-b-secret"]


async def test_probe_table_has_rls_enabled_and_forced(
    admin_engine: AsyncEngine,
) -> None:
    """FORCE is what makes the policy apply to the owning role too."""
    async with admin_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'platform' AND c.relname = 'tenant_isolation_probe'"
            )
        )
        enabled, forced = result.one()

    assert enabled is True
    assert forced is True
