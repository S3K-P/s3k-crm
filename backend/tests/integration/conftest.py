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
from collections.abc import AsyncIterator, Iterator
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
#: ``DELETE`` rather than ``TRUNCATE ... CASCADE``: ``platform.roles`` has a
#: foreign key to ``platform.organizations``, so a cascading truncate would take
#: the migration-seeded **system** roles with it and break every later test.
_STATEMENTS_TO_CLEAN = (
    "DELETE FROM crm.opportunity_stage_history",
    "DELETE FROM crm.opportunities",
    "DELETE FROM crm.campaign_members",
    "DELETE FROM crm.campaigns",
    "DELETE FROM crm.notes",
    "DELETE FROM crm.tasks",
    "DELETE FROM crm.meetings",
    "DELETE FROM crm.activities",
    "DELETE FROM crm.contacts",
    "DELETE FROM crm.leads",
    "DELETE FROM crm.lead_sources",
    "DELETE FROM crm.pipeline_stages",
    "DELETE FROM crm.pipelines",
    "DELETE FROM crm.accounts",
    # ``platform.audit_logs`` is append-only: a trigger rejects DELETE for
    # every role, superusers included. Emptying it between tests therefore
    # requires disabling that trigger, which is DDL and needs table ownership —
    # exactly the privileged, deliberate act the migration describes retention
    # as being. The runtime role has no such privilege, which is the point: if
    # this DELETE ever starts working on its own, the guarantee is gone and
    # ``test_audit_immutability`` will say so.
    f"ALTER TABLE platform.audit_logs DISABLE TRIGGER {APPEND_ONLY_TRIGGER}",
    "DELETE FROM platform.audit_logs",
    f"ALTER TABLE platform.audit_logs ENABLE TRIGGER {APPEND_ONLY_TRIGGER}",
    "DELETE FROM platform.attachments",
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
    """
    async def _clear() -> None:
        async with session_factory() as session:
            for statement in _STATEMENTS_TO_CLEAN:
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
