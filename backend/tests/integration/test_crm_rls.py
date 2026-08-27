"""Row-Level Security on real CRM tables, not just the Phase 0 probe.

``test_tenant_isolation.py`` proves the policy shape works on a throwaway
table. This proves the policies were actually applied to the business tables
this phase created, and that they still deny cross-tenant access when the
application layer is removed from the picture entirely — the queries here are
raw SQL, with no repository filters involved.

Two halves, and both are needed:

**Coverage** (the GATE 2 schema audit) asks PostgreSQL which tables exist and
requires every one of them to be tenant-scoped-and-protected or documented as
exempt. It replaces a hand-maintained roster of table names, which could only
ever vouch for the tables someone remembered to add to it — the table added
next week would be missing from the list, and the audit would stay green.
:mod:`app.core.schema_audit` carries the reasoning.

**Behaviour** proves the policies actually isolate, by reading and writing
across organizations. A policy can be present and still be wrong; a catalogue
query cannot tell.

The local development role is a superuser and ignores every policy, so the
behavioural tests provision an ordinary ``NOBYPASSRLS`` role and connect as it.
Running them as the owner would pass while proving nothing.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.config import Settings
from app.core.models import TENANT_SETTING
from app.core.rls import enable_rls
from app.core.schema_audit import (
    TABLE_POLICY_SQL,
    TABLE_SECURITY_SQL,
    TENANT_COLUMN,
    TableSecurity,
    audit_tenant_isolation,
    build_table_security,
    format_findings,
)
from app.products.crm.common import CRM_SCHEMA, PLATFORM_SCHEMA, RLS_EXEMPT_TABLES
from app.schema import metadata

pytestmark = pytest.mark.integration

TEST_ROLE = "s3k_crm_rls_probe_role"

ORG_A = uuid.UUID("aaaaaaaa-1111-7000-8000-000000000001")
ORG_B = uuid.UUID("bbbbbbbb-2222-7000-8000-000000000002")

#: Name for the throwaway tables the audit-regression tests create. Dropped in
#: a ``finally`` — a leftover would fail every later run of the audit, which is
#: noisy but at least fails loudly rather than silently passing.
PROBE_TABLE = "rls_audit_probe"


async def _discover(engine: AsyncEngine, schema: str) -> tuple[TableSecurity, ...]:
    """Read one schema's tables and policies straight out of the catalogues."""
    async with engine.connect() as connection:
        tables = (
            await connection.execute(
                TABLE_SECURITY_SQL, {"schema": schema, "column": TENANT_COLUMN}
            )
        ).mappings().all()
        policies = (
            await connection.execute(TABLE_POLICY_SQL, {"schema": schema})
        ).mappings().all()
    return build_table_security(schema, tables, policies)


@asynccontextmanager
async def _probe_table(engine: AsyncEngine, *, columns: str) -> AsyncIterator[str]:
    """Create a table in ``crm`` for the duration of the block, then drop it.

    Stands in for "someone adds a CRM table next sprint". Nothing inserts into
    it; it exists only to be discovered.
    """
    async with engine.begin() as connection:
        await connection.execute(text(f'DROP TABLE IF EXISTS crm."{PROBE_TABLE}"'))
        await connection.execute(text(f'CREATE TABLE crm."{PROBE_TABLE}" ({columns})'))
    try:
        yield PROBE_TABLE
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(f'DROP TABLE IF EXISTS crm."{PROBE_TABLE}"'))


@pytest_asyncio.fixture
async def owner_engine(integration_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(integration_settings.database_url)
    try:
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
    for schema in ("crm", "platform"):
        statements.append(
            f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM {TEST_ROLE}"
        )
        statements.append(f"REVOKE USAGE ON SCHEMA {schema} FROM {TEST_ROLE}")

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
    owner_engine: AsyncEngine, integration_settings: Settings
) -> AsyncIterator[AsyncEngine]:
    """An engine connected as an ordinary, RLS-subject role."""
    # token_hex is [0-9a-f] only, so inlining it into DDL is injection-safe.
    # CREATE ROLE is DDL and cannot take bind parameters.
    password = secrets.token_hex(24)

    async with owner_engine.begin() as connection:
        # An interrupted run leaves the role behind, still holding grants.
        await _drop_probe_role_if_present(connection)
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
            await _drop_probe_role_if_present(connection)


@pytest_asyncio.fixture
async def seeded_accounts(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    """Two accounts for organization A, one for organization B.

    Seeded one organization at a time, each under its own tenant scope.
    ``crm.accounts`` is RLS-FORCEd and the policy's ``WITH CHECK`` admits only
    rows matching the *current* setting, so a single statement inserting for
    two organizations is refused outright and an unscoped one is refused for
    every row. Written against a superuser connection this fixture worked
    because no policy applied to it at all; against an ordinary role the
    seeding has to obey the rule these tests exist to verify.
    """
    rows = {
        ORG_A: ("A-first", "A-second"),
        ORG_B: ("B-secret",),
    }

    async with owner_engine.begin() as connection:
        for organization_id, names in rows.items():
            await connection.execute(
                text("SELECT set_config(:setting, :value, true)"),
                {"setting": TENANT_SETTING, "value": str(organization_id)},
            )
            for name in names:
                await connection.execute(
                    text(
                        "INSERT INTO crm.accounts (organization_id, name) "
                        "VALUES (:org, :name)"
                    ),
                    {"org": organization_id, "name": name},
                )
    yield
    async with owner_engine.begin() as connection:
        for organization_id in rows:
            await connection.execute(
                text("SELECT set_config(:setting, :value, true)"),
                {"setting": TENANT_SETTING, "value": str(organization_id)},
            )
            await connection.execute(
                text("DELETE FROM crm.accounts WHERE organization_id = :org"),
                {"org": organization_id},
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


# --- Policy coverage: the GATE 2 schema audit -------------------------------


@pytest_asyncio.fixture
async def crm_schema(owner_engine: AsyncEngine) -> tuple[TableSecurity, ...]:
    """Every table in the ``crm`` schema, as PostgreSQL currently reports it."""
    return await _discover(owner_engine, CRM_SCHEMA)


async def test_the_audit_sees_every_crm_table_the_models_declare(
    crm_schema: tuple[TableSecurity, ...],
) -> None:
    """Guards the guard: a discovery query returning nothing would make the
    audit below pass while inspecting an empty schema.

    Cross-checked against the ORM metadata rather than a list written here, so
    it also catches a model added without a migration, or the reverse.
    """
    discovered = {table.name for table in crm_schema}
    declared = {
        table.name for table in metadata.tables.values() if table.schema == CRM_SCHEMA
    }

    assert discovered == declared, (
        f"only in the database: {sorted(discovered - declared)}; "
        f"only in the models: {sorted(declared - discovered)}"
    )


async def test_the_crm_schema_passes_the_rls_audit(
    crm_schema: tuple[TableSecurity, ...],
) -> None:
    """The GATE 2 criterion: RLS on **every** ``crm`` table, discovered not listed."""
    findings = audit_tenant_isolation(crm_schema, exemptions=RLS_EXEMPT_TABLES)

    assert not findings, "the crm schema fails tenant-isolation audit:\n" + format_findings(
        findings
    )


async def test_every_tenant_scoped_crm_table_has_rls_enabled_and_forced(
    crm_schema: tuple[TableSecurity, ...],
) -> None:
    """FORCE is what makes the policy apply to the owning role as well.

    Stated separately from the audit because it is the single property most
    likely to be silently lost: ``ENABLE`` without ``FORCE`` looks correct in
    ``\\d`` output and leaves the application — which owns these tables —
    reading every tenant's rows.
    """
    tenant_tables = [table for table in crm_schema if table.has_tenant_column]

    assert tenant_tables, "no tenant-scoped crm tables were discovered"

    unprotected = [t.qualified_name for t in tenant_tables if not t.rls_enabled]
    unforced = [t.qualified_name for t in tenant_tables if not t.rls_forced]

    assert not unprotected, f"RLS is not enabled on {unprotected}"
    assert not unforced, f"RLS is not FORCEd on {unforced}"


async def test_meetings_is_the_only_crm_table_without_a_tenant_column(
    crm_schema: tuple[TableSecurity, ...],
) -> None:
    """The documented 1:1 extension exemption, and nothing else.

    Widening this set is meant to be a deliberate act with a written reason —
    see ``RLS_EXEMPT_TABLES``.
    """
    unscoped = {table.name for table in crm_schema if not table.has_tenant_column}

    assert unscoped == {"meetings"}
    assert set(RLS_EXEMPT_TABLES) == {"meetings"}


async def test_the_meetings_exemption_still_rests_on_a_one_to_one_link(
    owner_engine: AsyncEngine,
) -> None:
    """``crm.meetings`` is exempt *because* it hangs off a policy-filtered parent.

    The exemption is only sound while that structure holds: a NOT NULL, UNIQUE
    foreign key to ``crm.activities`` that cascades on delete. Check the reason,
    not just the entry in the list.
    """
    async with owner_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT a.attnotnull                       AS not_null,
                           c.confdeltype::text                AS on_delete,
                           EXISTS (
                               SELECT 1 FROM pg_constraint u
                                WHERE u.conrelid = c.conrelid
                                  AND u.contype IN ('u', 'p')
                                  AND u.conkey = c.conkey
                           )                                  AS is_unique
                      FROM pg_constraint c
                      JOIN pg_attribute a
                        ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
                     WHERE c.conrelid = 'crm.meetings'::regclass
                       AND c.contype = 'f'
                       AND a.attname = 'activity_id'
                    """
                )
            )
        ).one_or_none()

    assert row is not None, "crm.meetings has no foreign key on activity_id"
    not_null, on_delete, is_unique = row
    assert not_null is True, "a meeting could exist with no tenant-scoped parent"
    assert is_unique is True, "activity_id is not 1:1 with crm.activities"
    assert on_delete == "c", "deleting an activity must cascade to its meeting"


async def test_platform_attachments_is_tenant_isolated(owner_engine: AsyncEngine) -> None:
    """CRM stores file metadata through Platform, so its table is in scope too.

    The rest of ``platform`` is audited by module (Phase 1): several of its
    tables carry a nullable ``organization_id`` on purpose — a NULL row in
    ``platform.roles`` is a system template shared by every tenant — so the
    blanket rule this file applies to ``crm`` does not transfer there.
    """
    tables = {table.name: table for table in await _discover(owner_engine, PLATFORM_SCHEMA)}
    attachments = tables.get("attachments")

    assert attachments is not None, "platform.attachments does not exist"

    findings = audit_tenant_isolation((attachments,), exemptions={})

    assert not findings, format_findings(findings)


async def test_platform_teams_are_tenant_isolated(owner_engine: AsyncEngine) -> None:
    """Team membership feeds record-level visibility, so its tables are in scope.

    ``departments`` and ``teams`` carry a non-null ``organization_id`` and take
    the standard policy. ``team_memberships`` is checked separately below: it
    has no tenant column at all, by design.
    """
    tables = {table.name: table for table in await _discover(owner_engine, PLATFORM_SCHEMA)}

    for name in ("departments", "teams"):
        table = tables.get(name)
        assert table is not None, f"platform.{name} does not exist"
        findings = audit_tenant_isolation((table,), exemptions={})
        assert not findings, format_findings(findings)


async def test_team_memberships_is_isolated_through_its_team(
    owner_engine: AsyncEngine,
) -> None:
    """The join has no ``organization_id``, so the blanket rule cannot apply.

    Its isolation comes from an ``EXISTS`` policy over ``platform.teams``,
    which is itself tenant-scoped. This asserts the policy is present *and*
    forced, because a membership readable across tenants would leak who works
    with whom — and, through ``VIEW_TEAM``, widen what they can read.
    """
    async with owner_engine.connect() as connection:
        enabled, forced = (
            await connection.execute(
                text(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE oid = 'platform.team_memberships'::regclass"
                )
            )
        ).one()
        predicate = (
            await connection.execute(
                text(
                    "SELECT pg_get_expr(polqual, polrelid) FROM pg_policy "
                    "WHERE polrelid = 'platform.team_memberships'::regclass"
                )
            )
        ).scalar_one_or_none()

    assert enabled is True, "RLS is not enabled on platform.team_memberships"
    assert forced is True, "RLS is not FORCEd on platform.team_memberships"
    assert predicate is not None, "platform.team_memberships has no policy"
    # The policy must reach the tenant through teams, not trust a local column.
    assert "teams" in predicate
    assert "current_setting" in predicate


# --- Policy coverage: the audit's own failure modes -------------------------


async def test_a_new_organization_scoped_table_without_rls_fails_the_audit(
    owner_engine: AsyncEngine,
) -> None:
    """The regression this whole audit exists to catch.

    A hardcoded table list passes right through this case, because the new
    table is not on the list.
    """
    async with _probe_table(
        owner_engine, columns="id uuid PRIMARY KEY, organization_id uuid NOT NULL"
    ):
        findings = audit_tenant_isolation(
            await _discover(owner_engine, CRM_SCHEMA), exemptions=RLS_EXEMPT_TABLES
        )

    problems = {f.problem for f in findings if f.table == f"crm.{PROBE_TABLE}"}

    assert "rls_disabled" in problems, f"audit reported {problems or 'nothing'}"


async def test_the_same_table_passes_once_its_migration_enables_rls(
    owner_engine: AsyncEngine,
) -> None:
    """...and the failure above is about the missing policy, not the new name.

    Without this, an audit that simply rejected anything unfamiliar would look
    identical to one that checks the thing we care about.
    """
    async with _probe_table(
        owner_engine, columns="id uuid PRIMARY KEY, organization_id uuid NOT NULL"
    ) as table:
        async with owner_engine.begin() as connection:
            await connection.run_sync(enable_rls, table, schema=CRM_SCHEMA)

        findings = audit_tenant_isolation(
            await _discover(owner_engine, CRM_SCHEMA), exemptions=RLS_EXEMPT_TABLES
        )

    assert not findings, format_findings(findings)


async def test_rls_enabled_without_force_still_fails_the_audit(
    owner_engine: AsyncEngine,
) -> None:
    """``ENABLE`` alone leaves the owning role — the application — unfiltered."""
    async with _probe_table(
        owner_engine, columns="id uuid PRIMARY KEY, organization_id uuid NOT NULL"
    ) as table:
        async with owner_engine.begin() as connection:
            await connection.run_sync(enable_rls, table, schema=CRM_SCHEMA)
            await connection.execute(
                text(f'ALTER TABLE crm."{table}" NO FORCE ROW LEVEL SECURITY')
            )

        findings = audit_tenant_isolation(
            await _discover(owner_engine, CRM_SCHEMA), exemptions=RLS_EXEMPT_TABLES
        )

    problems = {f.problem for f in findings if f.table == f"crm.{PROBE_TABLE}"}

    assert problems == {"rls_not_forced"}


async def test_a_new_crm_table_with_no_tenant_column_must_be_classified(
    owner_engine: AsyncEngine,
) -> None:
    """The subtler failure: nothing to protect, so RLS coverage looks complete.

    A CRM table that forgot ``TenantMixin`` holds customer data with no tenant
    discriminator at all. It must be given one, or documented like
    ``crm.meetings`` — silence is not an option the audit allows.
    """
    async with _probe_table(owner_engine, columns="id uuid PRIMARY KEY, subject text NOT NULL"):
        findings = audit_tenant_isolation(
            await _discover(owner_engine, CRM_SCHEMA), exemptions=RLS_EXEMPT_TABLES
        )

    problems = {f.problem for f in findings if f.table == f"crm.{PROBE_TABLE}"}

    assert "unclassified_table" in problems, f"audit reported {problems or 'nothing'}"


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
