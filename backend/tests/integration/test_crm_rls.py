"""Row-Level Security on real CRM tables, not just the Phase 0 probe.

``test_tenant_isolation.py`` proves the policy shape works on a throwaway
table. This proves the policies were actually applied to the business tables
this phase created, and that they still deny cross-tenant access when the
application layer is removed from the picture entirely — the queries here are
raw SQL, with no repository filters involved.

The local development role is a superuser and ignores every policy, so these
tests provision an ordinary ``NOBYPASSRLS`` role and connect as it. Running
them as the owner would pass while proving nothing.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.core.models import TENANT_SETTING

pytestmark = pytest.mark.integration

TEST_ROLE = "s3k_crm_rls_probe_role"

ORG_A = uuid.UUID("aaaaaaaa-1111-7000-8000-000000000001")
ORG_B = uuid.UUID("bbbbbbbb-2222-7000-8000-000000000002")

#: Tenant-scoped tables this phase added, sampled across both schemas.
RLS_TABLES = (
    ("crm", "accounts"),
    ("crm", "contacts"),
    ("crm", "leads"),
    ("crm", "opportunities"),
    ("crm", "tasks"),
    ("crm", "notes"),
    ("crm", "activities"),
    ("crm", "campaigns"),
    ("crm", "pipelines"),
    ("crm", "pipeline_stages"),
    ("crm", "lead_sources"),
    ("crm", "campaign_members"),
    ("crm", "opportunity_stage_history"),
    ("platform", "attachments"),
)


@pytest_asyncio.fixture
async def owner_engine(integration_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(integration_settings.database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def tenant_engine(
    owner_engine: AsyncEngine, integration_settings: Settings
) -> AsyncIterator[AsyncEngine]:
    """An engine connected as an ordinary, RLS-subject role."""
    # token_hex is [0-9a-f] only, so inlining it into DDL is injection-safe.
    # CREATE ROLE is DDL and cannot take bind parameters.
    password = secrets.token_hex(24)

    async with owner_engine.begin() as connection:
        await connection.execute(text(f"DROP ROLE IF EXISTS {TEST_ROLE}"))
        await connection.execute(
            text(f"CREATE ROLE {TEST_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'")
        )
        for schema in ("crm", "platform"):
            await connection.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO {TEST_ROLE}"))
            await connection.execute(
                text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                    f"IN SCHEMA {schema} TO {TEST_ROLE}"
                )
            )

    url = make_url(integration_settings.database_url).set(
        username=TEST_ROLE, password=password
    )
    engine = create_async_engine(url)
    try:
        yield engine
    finally:
        await engine.dispose()
        async with owner_engine.begin() as connection:
            await connection.execute(text(f"DROP OWNED BY {TEST_ROLE}"))
            await connection.execute(text(f"DROP ROLE IF EXISTS {TEST_ROLE}"))


@pytest_asyncio.fixture
async def seeded_accounts(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    """Two accounts for organization A, one for organization B."""
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO crm.accounts (organization_id, name) VALUES "
                "(:a, 'A-first'), (:a, 'A-second'), (:b, 'B-secret')"
            ),
            {"a": ORG_A, "b": ORG_B},
        )
    yield
    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM crm.accounts WHERE organization_id IN (:a, :b)"),
            {"a": ORG_A, "b": ORG_B},
        )


async def _scoped_names(engine: AsyncEngine, organization_id: uuid.UUID | None) -> list[str]:
    async with engine.connect() as connection:
        transaction = await connection.begin()
        if organization_id is not None:
            await connection.execute(
                text("SELECT set_config(:setting, :value, true)"),
                {"setting": TENANT_SETTING, "value": str(organization_id)},
            )
        result = await connection.execute(
            text("SELECT name FROM crm.accounts ORDER BY name")
        )
        names = [row[0] for row in result]
        await transaction.rollback()
    return names


# --- Policy coverage --------------------------------------------------------


@pytest.mark.parametrize(("schema", "table"), RLS_TABLES, ids=lambda value: str(value))
async def test_every_tenant_table_has_rls_enabled_and_forced(
    owner_engine: AsyncEngine, schema: str, table: str
) -> None:
    """FORCE is what makes the policy apply to the owning role as well."""
    async with owner_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relname = :table"
            ),
            {"schema": schema, "table": table},
        )
        row = result.one_or_none()

    assert row is not None, f"{schema}.{table} does not exist"
    enabled, forced = row
    assert enabled is True, f"RLS is not enabled on {schema}.{table}"
    assert forced is True, f"RLS is not FORCEd on {schema}.{table}"


# --- Behaviour --------------------------------------------------------------


async def test_the_probe_role_is_actually_subject_to_rls(
    tenant_engine: AsyncEngine,
) -> None:
    """Guards the guard: a bypassing role would make every test below vacuous."""
    async with tenant_engine.connect() as connection:
        result = await connection.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
        assert result.scalar() is False


async def test_an_organization_sees_only_its_own_accounts(
    tenant_engine: AsyncEngine, seeded_accounts: None
) -> None:
    assert await _scoped_names(tenant_engine, ORG_A) == ["A-first", "A-second"]


async def test_cross_organization_reads_return_nothing(
    tenant_engine: AsyncEngine, seeded_accounts: None
) -> None:
    assert "B-secret" not in await _scoped_names(tenant_engine, ORG_A)


async def test_a_query_with_no_tenant_context_returns_zero_rows(
    tenant_engine: AsyncEngine, seeded_accounts: None
) -> None:
    """Fail closed: an unscoped query must not fall back to "every tenant"."""
    assert await _scoped_names(tenant_engine, None) == []


async def test_writing_into_another_organization_is_rejected(
    tenant_engine: AsyncEngine, seeded_accounts: None
) -> None:
    """WITH CHECK stops a tenant planting rows in someone else's scope."""
    with pytest.raises(DBAPIError):
        async with tenant_engine.begin() as connection:
            await connection.execute(
                text("SELECT set_config(:setting, :value, true)"),
                {"setting": TENANT_SETTING, "value": str(ORG_A)},
            )
            await connection.execute(
                text(
                    "INSERT INTO crm.accounts (organization_id, name) "
                    "VALUES (:b, 'smuggled')"
                ),
                {"b": ORG_B},
            )


async def test_deleting_another_organizations_row_affects_nothing(
    tenant_engine: AsyncEngine, seeded_accounts: None
) -> None:
    async with tenant_engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": str(ORG_A)},
        )
        result = await connection.execute(
            text("DELETE FROM crm.accounts WHERE name = 'B-secret'")
        )
        assert result.rowcount == 0

    assert await _scoped_names(tenant_engine, ORG_B) == ["B-secret"]


async def test_tenant_scope_does_not_leak_between_transactions(
    tenant_engine: AsyncEngine, seeded_accounts: None
) -> None:
    """``set_config(..., true)`` is transaction-local, so a pooled connection
    cannot carry one request's organization into the next."""
    async with tenant_engine.connect() as connection:
        transaction = await connection.begin()
        await connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": str(ORG_A)},
        )
        scoped = (
            await connection.execute(text("SELECT count(*) FROM crm.accounts"))
        ).scalar()
        await transaction.rollback()

        transaction = await connection.begin()
        unscoped = (
            await connection.execute(text("SELECT count(*) FROM crm.accounts"))
        ).scalar()
        await transaction.rollback()

    assert scoped == 2
    assert unscoped == 0
