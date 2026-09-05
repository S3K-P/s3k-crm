"""Fixtures for the Phase 1 integration suite.

These tests run against the **real** PostgreSQL from ``docker compose``, because
the guarantees under test — tenant isolation, RBAC, refresh-token rotation —
live in the database and in SQL, not in Python objects that a mock could stand
in for.

Requires ``docker compose up -d`` and ``uv run alembic upgrade head``.

Two organizations are seeded for every test, each with its own Admin, Manager
and read-only User, so a cross-tenant attempt always has a real target to try
to reach.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application import create_app
from app.core.config import ConfigurationError, Settings, get_settings
from app.core.models import TENANT_SETTING
from app.platform.audit.models import APPEND_ONLY_TRIGGER
from app.platform.auth.repository import AuthRepository
from app.platform.auth.security import PasswordHasher
from app.platform.auth.service import AuthService
from app.platform.authorization.catalog import ADMIN_ROLE, MANAGER_ROLE, USER_ROLE
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService
from app.platform.organizations.repository import OrganizationRepository
from app.platform.organizations.service import OrganizationService
from app.products.crm.opportunities.service import OpportunityService

pytestmark = pytest.mark.integration

#: Meets the default policy: 12+ chars, mixed case, digit.
TEST_PASSWORD = "Str0ngPassphrase!"

#: Cleared between tests, dependants first.
#:
#: Split by whether the tenant policy applies, because the two halves have to
#: be deleted differently. RLS is enforced on ``DELETE`` exactly as on
#: ``SELECT``: a statement with no ``app.current_org_id`` matches nothing and
#: commits without complaint, so these ran between every test and removed
#: nothing at all. The fixture below therefore repeats this list once per
#: organization, with that organization in scope.
#:
#: ``DELETE`` rather than ``TRUNCATE ... CASCADE``: ``platform.roles`` has a
#: foreign key to ``platform.organizations``, so a cascading truncate would take
#: the migration-seeded **system** roles with it and break every later test.
_TENANT_SCOPED_STATEMENTS_TO_CLEAN = (
    # Market Insights first: sources and messages cascade from sessions, but
    # deleting the parent explicitly keeps the order readable rather than
    # relying on the cascade to imply it.
    "DELETE FROM crm.market_insight_sources",
    "DELETE FROM crm.market_insight_messages",
    "DELETE FROM crm.market_insight_sessions",
    # Prompt versions are tenant data, not migration-seeded reference data, so
    # they are cleaned like everything else a test creates. They belong in the
    # tenant-scoped half because the migration RLS-enables the table: an
    # unscoped DELETE would match nothing and pass in silence.
    "DELETE FROM platform.ai_prompt_versions",
    # Dashboard tiles before the reports they RESTRICT, and before the
    # dashboards they cascade from: the foreign keys make the order load-
    # bearing rather than cosmetic here.
    "DELETE FROM crm.dashboard_components",
    "DELETE FROM crm.dashboards",
    "DELETE FROM crm.saved_reports",
    "DELETE FROM crm.report_folders",
    "DELETE FROM crm.opportunity_stage_history",
    "DELETE FROM crm.opportunities",
    "DELETE FROM crm.campaign_members",
    "DELETE FROM crm.campaigns",
    "DELETE FROM crm.notes",
    "DELETE FROM crm.tasks",
    "DELETE FROM crm.activities",
    "DELETE FROM crm.contacts",
    "DELETE FROM crm.leads",
    "DELETE FROM crm.lead_sources",
    "DELETE FROM crm.pipeline_stages",
    "DELETE FROM crm.pipelines",
    "DELETE FROM crm.accounts",
    "DELETE FROM platform.audit_logs",
    "DELETE FROM platform.attachments",
)

#: Tables the tenant policy does *not* cover, so one unscoped pass clears them.
#:
#: ``crm.meetings`` is a one-to-one extension of ``crm.activities`` and carries
#: no tenant column of its own; the rest are the identity and authorization
#: tables read while tenant context is still being established, which is
#: exactly why they are RLS-exempt (see the Phase 1 migration).
_UNSCOPED_STATEMENTS_TO_CLEAN = (
    "DELETE FROM crm.meetings",
    # Cleared explicitly rather than left to the ON DELETE CASCADE from
    # ``platform.organizations`` below: the cascade would do it today, but a
    # test that leaks a PENDING invitation collides with the next one through
    # the partial unique index on (organization_id, email), and that failure
    # would point at the invitation code rather than at the fixture.
    "DELETE FROM platform.organization_invitations",
    "DELETE FROM platform.membership_roles",
    "DELETE FROM platform.organization_memberships",
    "DELETE FROM platform.sessions",
    "DELETE FROM platform.user_profiles",
    "DELETE FROM platform.users",
    # Tenant-defined roles only; system templates (organization_id IS NULL) stay.
    "DELETE FROM platform.role_permissions WHERE role_id IN "
    "(SELECT id FROM platform.roles WHERE organization_id IS NOT NULL)",
    "DELETE FROM platform.roles WHERE organization_id IS NOT NULL",
    "DELETE FROM platform.organizations",
)

#: ``platform.audit_logs`` is append-only: a trigger rejects DELETE for every
#: role, superusers included. Emptying it between tests therefore requires
#: disabling that trigger, which is DDL and needs table ownership -- exactly
#: the privileged, deliberate act the migration describes retention as being.
#: The runtime role has no such privilege, which is the point: if the DELETE
#: above ever starts working on its own, the guarantee is gone and
#: ``test_audit_immutability`` will say so.
_AUDIT_TRIGGER_OFF = f"ALTER TABLE platform.audit_logs DISABLE TRIGGER {APPEND_ONLY_TRIGGER}"
_AUDIT_TRIGGER_ON = f"ALTER TABLE platform.audit_logs ENABLE TRIGGER {APPEND_ONLY_TRIGGER}"


@dataclass(frozen=True, slots=True)
class SeededUser:
    """A user plus the organization they were seeded into."""

    user_id: uuid.UUID
    email: str
    organization_id: uuid.UUID
    role: str


@dataclass(frozen=True, slots=True)
class Tenant:
    """One seeded organization and its three users."""

    organization_id: uuid.UUID
    slug: str
    admin: SeededUser
    manager: SeededUser
    member: SeededUser


@pytest.fixture(scope="session")
def integration_settings() -> Settings:
    try:
        return get_settings()
    except ConfigurationError:  # pragma: no cover - environment dependent
        pytest.skip("backend/.env is not configured; see .env.example")


@pytest_asyncio.fixture
async def session_factory(
    integration_settings: Settings,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory for seeding, independent of the application's."""
    engine = create_async_engine(integration_settings.database_url)
    try:
        async with engine.connect() as connection:
            try:
                await connection.execute(text("SELECT 1 FROM platform.users LIMIT 1"))
            except Exception:  # pragma: no cover - migration not applied
                pytest.skip("schema missing; run `uv run alembic upgrade head`")
        yield async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Empty the business tables before and after each test.

    Seeded reference data (permissions, system roles) is left alone: it is
    owned by the migration, not by any test.

    **Why the tenant loop.** Most of these tables are RLS-FORCEd, and the
    policy applies to ``DELETE`` exactly as it applies to ``SELECT`` — a
    statement issued with no ``app.current_org_id`` matches zero rows and
    commits happily. So this fixture ran to completion between every test
    while deleting nothing, and the isolation it exists to provide was not
    happening: rows accumulated for the whole session and tests passed or
    failed depending on what had run before them.

    That was invisible while ``DATABASE_URL`` named a superuser, for whom no
    policy applies. Against an ordinary role the cleanup has to name each
    tenant in turn. ``platform.organizations`` is deliberately RLS-exempt (it
    is read while *establishing* tenant context), so it can be enumerated
    without a scope — which is what makes the loop possible at all.
    """
    async def _organization_ids(session: AsyncSession) -> list[str]:
        result = await session.execute(text("SELECT id FROM platform.organizations"))
        return [str(row[0]) for row in result]

    async def _clear() -> None:
        async with session_factory() as session:
            # DDL, so it runs once rather than per tenant.
            await session.execute(text(_AUDIT_TRIGGER_OFF))

            for organization_id in await _organization_ids(session):
                await session.execute(
                    text(f"SELECT set_config('{TENANT_SETTING}', :value, false)"),
                    {"value": organization_id},
                )
                for statement in _TENANT_SCOPED_STATEMENTS_TO_CLEAN:
                    await session.execute(text(statement))

            await session.execute(text(_AUDIT_TRIGGER_ON))

            # Rows that belong to no tenant, and the organizations themselves.
            # Run unscoped because none of these tables carries a policy.
            await session.execute(
                text(f"SELECT set_config('{TENANT_SETTING}', '', false)")
            )
            for statement in _UNSCOPED_STATEMENTS_TO_CLEAN:
                await session.execute(text(statement))
            await session.commit()

    await _clear()
    yield
    await _clear()


async def _seed_tenant(
    session: AsyncSession, *, slug: str, seed_pipeline: bool = True
) -> Tenant:
    """Create one organization with an Admin, a Manager and a plain User."""
    organizations = OrganizationService(OrganizationRepository(session))
    authorization = AuthorizationService(AuthorizationRepository(session))
    auth = AuthService(
        repository=AuthRepository(session),
        organizations=OrganizationRepository(session),
        hasher=PasswordHasher(),
        issuer=None,  # type: ignore[arg-type]  # not used by register_user
        settings=get_settings(),
    )

    organization = await organizations.create_organization(name=slug.title(), slug=slug)

    seeded: dict[str, SeededUser] = {}
    for role_name in (ADMIN_ROLE, MANAGER_ROLE, USER_ROLE):
        email = f"{role_name.lower()}@{slug}.example"
        user = await auth.register_user(
            email=email,
            password=TEST_PASSWORD,
            first_name=role_name,
            last_name=slug.title(),
        )
        membership = await organizations.add_member(
            organization_id=organization.id, user_id=user.id, is_default=True
        )
        role = await authorization.get_system_role(role_name)
        await authorization.assign_role_to_membership(
            membership_id=membership.id,
            role_id=role.id,
            organization_id=organization.id,
        )
        seeded[role_name] = SeededUser(
            user_id=user.id,
            email=email,
            organization_id=organization.id,
            role=role_name,
        )

    if seed_pipeline:
        await OpportunityService(session).ensure_default_pipeline(organization.id)

    return Tenant(
        organization_id=organization.id,
        slug=slug,
        admin=seeded[ADMIN_ROLE],
        manager=seeded[MANAGER_ROLE],
        member=seeded[USER_ROLE],
    )


@pytest_asyncio.fixture
async def tenants(
    session_factory: async_sessionmaker[AsyncSession],
    clean_database: None,
) -> tuple[Tenant, Tenant]:
    """Two fully independent organizations: ``alpha`` and ``beta``.

    Depends on ``clean_database`` explicitly: autouse fixtures have no
    guaranteed ordering against non-autouse ones, and a cleanup that ran after
    the seed would silently delete it.
    """
    async with session_factory() as session:
        alpha = await _seed_tenant(session, slug="alpha")
        beta = await _seed_tenant(session, slug="beta")
        await session.commit()
    return alpha, beta


@pytest.fixture
def alpha(tenants: tuple[Tenant, Tenant]) -> Tenant:
    return tenants[0]


@pytest.fixture
def beta(tenants: tuple[Tenant, Tenant]) -> Tenant:
    return tenants[1]


@dataclass(frozen=True, slots=True)
class DualMember:
    """One user holding an ACTIVE membership in *both* organizations.

    Legitimate multi-organization membership is the case that separates real
    tenant scoping from "one user, one tenant, therefore nothing to prove":
    the same credentials must return strictly different data depending only on
    the organization the request is scoped to.
    """

    user_id: uuid.UUID
    email: str
    alpha_organization_id: uuid.UUID
    beta_organization_id: uuid.UUID


@pytest_asyncio.fixture
async def dual_member(
    session_factory: async_sessionmaker[AsyncSession],
    tenants: tuple[Tenant, Tenant],
) -> DualMember:
    """A user who belongs to both alpha and beta, as Admin in each."""
    alpha, beta = tenants
    email = "consultant@both.example"

    async with session_factory() as session, session.begin():
        organizations = OrganizationService(OrganizationRepository(session))
        authorization = AuthorizationService(AuthorizationRepository(session))
        auth = AuthService(
            repository=AuthRepository(session),
            organizations=OrganizationRepository(session),
            hasher=PasswordHasher(),
            issuer=None,  # type: ignore[arg-type]  # unused by register_user
            settings=get_settings(),
        )

        user = await auth.register_user(
            email=email, password=TEST_PASSWORD, first_name="Dual", last_name="Member"
        )
        admin_role = await authorization.get_system_role(ADMIN_ROLE)

        for index, tenant in enumerate((alpha, beta)):
            membership = await organizations.add_member(
                organization_id=tenant.organization_id,
                user_id=user.id,
                # Exactly one default, so login without an explicit organization
                # is deterministic.
                is_default=index == 0,
            )
            await authorization.assign_role_to_membership(
                membership_id=membership.id,
                role_id=admin_role.id,
                organization_id=tenant.organization_id,
            )

    return DualMember(
        user_id=user.id,
        email=email,
        alpha_organization_id=alpha.organization_id,
        beta_organization_id=beta.organization_id,
    )


@pytest.fixture
def api_app(integration_settings: Settings) -> FastAPI:
    """The real application, with real membership verification and JWTs."""
    return create_app(integration_settings)


@pytest.fixture
def client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as test_client:
        yield test_client


class ApiSession:
    """A signed-in client bound to one user and organization.

    Wraps :class:`TestClient` so every request carries the bearer token and the
    ``X-Organization-Id`` header, which is what the tenant middleware reads.
    """

    def __init__(self, client: TestClient, prefix: str) -> None:
        self._client = client
        self._prefix = prefix
        self.access_token: str = ""
        self.organization_id: uuid.UUID | None = None

    def login(self, email: str, *, organization_id: uuid.UUID | None = None) -> None:
        payload: dict[str, object] = {"email": email, "password": TEST_PASSWORD}
        if organization_id is not None:
            payload["organization_id"] = str(organization_id)
        response = self._client.post(f"{self._prefix}/auth/login", json=payload)
        response.raise_for_status()
        body = response.json()
        self.access_token = body["access_token"]
        self.organization_id = uuid.UUID(body["organization_id"])

    def headers(self, *, organization_id: uuid.UUID | None = None) -> dict[str, str]:
        target = organization_id or self.organization_id
        headers = {"Authorization": f"Bearer {self.access_token}"}
        if target is not None:
            headers["X-Organization-Id"] = str(target)
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        organization_id: uuid.UUID | None = None,
        **kwargs: object,
    ) -> Response:
        return self._client.request(
            method,
            f"{self._prefix}{path}",
            headers=self.headers(organization_id=organization_id),
            **kwargs,  # type: ignore[arg-type]
        )

    def get(self, path: str, **kwargs: object) -> Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: object) -> Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: object) -> Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: object) -> Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: object) -> Response:
        return self.request("DELETE", path, **kwargs)


@pytest.fixture
def api(client: TestClient, integration_settings: Settings) -> ApiSession:
    """An un-authenticated API session; call ``login`` to sign in."""
    return ApiSession(client, integration_settings.api_prefix)


@pytest.fixture
def as_alpha_admin(api: ApiSession, alpha: Tenant) -> ApiSession:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    return api


@pytest.fixture
def as_alpha_member(api: ApiSession, alpha: Tenant) -> ApiSession:
    api.login(alpha.member.email, organization_id=alpha.organization_id)
    return api


async def scope_session_to(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Scope a seeding session to one organization, as a real request would.

    Tests that seed rows by adding ORM objects to a bare session are writing
    into RLS-FORCEd tables with no ``app.current_org_id`` set. The tenant
    policy's ``WITH CHECK`` refuses every one of those INSERTs — and reads
    return nothing — unless the session says which organization it is acting
    for. The application does this per request in
    :func:`app.core.database.get_db_session`; a seeding session has no request
    to do it for, so it must say so itself.

    This went unnoticed for as long as it did because ``DATABASE_URL`` named a
    superuser, and a superuser is exempt from every policy: the seeds landed,
    the reads returned, and the suite was green while proving nothing about
    isolation. Run as an ordinary role, the omission is loud.

    ``is_local => false`` so the setting survives the helper's own statement
    and applies to whatever the caller does next in this session.
    """
    await session.execute(
        text(f"SELECT set_config('{TENANT_SETTING}', :value, false)"),
        {"value": str(organization_id)},
    )


async def membership_id_for(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> uuid.UUID:
    """The membership row that carries a user's roles in the seeded tenant."""
    async with session_factory() as session:
        value = await session.scalar(
            text("SELECT id FROM platform.organization_memberships WHERE user_id = :user"),
            {"user": user_id},
        )
    assert value is not None, "the seeded user has no membership"
    return uuid.UUID(str(value))


async def grant_custom_role(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    codes: Sequence[str],
    name: str | None = None,
) -> uuid.UUID:
    """Give one membership a tenant-defined role holding exactly ``codes``.

    Written in SQL because roles are seeded by the migration and the API
    exposes no role-authoring endpoint -- only assignment. The permission
    combinations worth testing are the ones the three system roles do *not*
    offer: ``EXPORT`` without ``VIEW_ALL``, or ``VIEW`` without ``CREATE``.
    Those are exactly what a real tenant's custom role would express, and the
    rules under test read the permission catalogue rather than a role name.

    ``platform.roles``, ``role_permissions`` and ``membership_roles`` are
    RLS-exempt by design -- they are read while tenant context is still being
    established -- so no tenant scope is set here.

    Returns the new role's id, for a test that needs to revoke it again.
    """
    async with session_factory() as session:
        role_id = await session.scalar(
            text(
                "INSERT INTO platform.roles (organization_id, name, description, is_system) "
                "VALUES (:org, :name, 'Created by a test', false) RETURNING id"
            ),
            {"org": organization_id, "name": name or f"Custom {uuid.uuid4().hex[:8]}"},
        )
        for code in codes:
            module, action = code.split(".", 1)
            await session.execute(
                text(
                    "INSERT INTO platform.role_permissions (role_id, permission_id) "
                    "SELECT :role, p.id FROM platform.permissions p "
                    "WHERE p.module = :module AND p.action = CAST(:action AS "
                    "platform.permission_action)"
                ),
                {"role": role_id, "module": module, "action": action},
            )
        await session.execute(
            text(
                "INSERT INTO platform.membership_roles (membership_id, role_id) "
                "VALUES (:membership, :role)"
            ),
            {"membership": membership_id, "role": role_id},
        )
        await session.commit()
    return uuid.UUID(str(role_id))


async def revoke_all_roles(
    session_factory: async_sessionmaker[AsyncSession], membership_id: uuid.UUID
) -> None:
    """Strip every role from a membership.

    For the tests that need a principal holding *less* than any seeded role
    does -- proving a refusal needs an absence, and the seeded User already
    holds CREATE on all three importable modules.
    """
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM platform.membership_roles WHERE membership_id = :membership"),
            {"membership": membership_id},
        )
        await session.commit()
