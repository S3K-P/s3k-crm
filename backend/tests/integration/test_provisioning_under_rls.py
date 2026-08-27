"""Provisioning a tenant works under a role that RLS actually applies to.

**The blind spot this closes.** ``test_crm_rls.py`` and ``test_tenant_isolation.py``
prove the policies work — but they prove it by provisioning their *own*
``NOSUPERUSER NOBYPASSRLS`` role and connecting as it directly. Everything
else, including every test that drives the application through ``TestClient``,
runs on ``DATABASE_URL``. Locally and in CI that named the container's
``POSTGRES_USER``, which the official PostgreSQL image creates as a superuser,
and a superuser is exempt from every policy.

So the application's own code path had never once run with tenant isolation
switched on, and a defect that made it impossible to create an organization sat
green in the suite: creating one INSERTs into ``platform.product_entitlements``
and ``crm.pipelines`` inside the transaction that creates the organization —
before that organization can have a tenant context — and both tables are
RLS-FORCEd, so ``WITH CHECK`` refused the rows. Under a correctly privileged
role 359 tests failed at once. The fix is
:func:`app.core.database.provisioning_scope`.

The first test here is the guard: if ``DATABASE_URL`` ever names an RLS-exempt
role again, it says so instead of letting the rest of the suite pass for the
wrong reason.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.organizations.repository import OrganizationRepository
from app.platform.organizations.service import OrganizationService
from app.platform.products.models import CRM_PRODUCT_CODE
from app.platform.products.service import products_for_session
from app.products.crm.opportunities.service import OpportunityService
from tests.integration.conftest import Tenant

pytestmark = pytest.mark.integration


async def _scope_to(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Read as ``organization_id`` would.

    Verifying a provisioning write means reading a row the tenant policy hides
    from everyone else — including a caller with no tenant context, which is
    what these tests otherwise have. Reading unscoped returns nothing and says
    nothing about whether the write landed.
    """
    await session.execute(
        text("SELECT set_config('app.current_org_id', :value, true)"),
        {"value": str(organization_id)},
    )


async def test_the_application_role_is_subject_to_rls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``DATABASE_URL`` must not name a superuser or a ``BYPASSRLS`` role.

    Not a style preference. Every policy in the schema is inert for such a
    role, so an integration suite running as one cannot distinguish "isolation
    works" from "isolation is switched off" — and the application must never
    hold that privilege in production either.
    """
    async with session_factory() as session:
        exempt = await session.scalar(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        )
        role = await session.scalar(text("SELECT current_user"))

    assert exempt is False, (
        f"DATABASE_URL connects as {role!r}, which bypasses row-level security. "
        "Tenant isolation is not being exercised. Point DATABASE_URL at a "
        "NOSUPERUSER NOBYPASSRLS role owning its own database."
    )


async def test_an_organization_can_be_created_with_no_tenant_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The bootstrap path: no tenant context exists at all.

    This is what ``app.bootstrap`` does against a fresh database. Before
    ``provisioning_scope`` it raised ``InsufficientPrivilegeError`` on the
    entitlement INSERT, which made a first-run deployment impossible.
    """
    async with session_factory() as session, session.begin():
        # No `set_config('app.current_org_id', ...)` — deliberately.
        assert not await session.scalar(
            text("SELECT current_setting('app.current_org_id', true)")
        )

        organizations = OrganizationService(OrganizationRepository(session))
        organization = await organizations.create_organization(name="Provisioning Probe")

        # Read as the new tenant: this is the scope every later request carries.
        await _scope_to(session, organization.id)
        entitled = await products_for_session(session).is_entitled(
            organization_id=organization.id, code=CRM_PRODUCT_CODE
        )

    assert entitled, "a newly created organization must be able to open the CRM"


async def test_the_default_pipeline_is_provisioned_with_no_tenant_context(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``crm.pipelines`` and ``crm.pipeline_stages`` are RLS-FORCEd too.

    Seeding them is the second half of creating a tenant, and it failed for
    exactly the same reason the entitlement did.
    """
    async with session_factory() as session, session.begin():
        organizations = OrganizationService(OrganizationRepository(session))
        organization = await organizations.create_organization(name="Pipeline Probe")

        pipeline = await OpportunityService(session).ensure_default_pipeline(organization.id)

        await _scope_to(session, organization.id)
        stages = await OpportunityService(session).list_stages(organization.id)

    assert pipeline.organization_id == organization.id
    assert stages, "the standard pipeline must arrive with its stages"


async def test_provisioning_restores_the_callers_tenant_scope(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant
) -> None:
    """An administrator creating a second organization keeps their own scope.

    ``provisioning_scope`` moves ``app.current_org_id`` onto the organization
    being created. If it failed to put the caller's own back, every statement
    after the call in that request would silently read and write the *new*
    tenant's rows — a far worse bug than the one it fixes.
    """
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_org_id', :value, true)"),
            {"value": str(alpha.organization_id)},
        )

        organizations = OrganizationService(OrganizationRepository(session))
        created = await organizations.create_organization(name="Second Tenant")

        scope_after = await session.scalar(
            text("SELECT current_setting('app.current_org_id', true)")
        )

    assert created.id != alpha.organization_id
    assert scope_after == str(alpha.organization_id), (
        "the caller's tenant scope must survive provisioning another organization"
    )


async def test_re_provisioning_an_existing_organization_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-running provisioning repairs rather than collides.

    Under RLS the existing entitlement is invisible to a caller scoped
    elsewhere, so a lookup outside the scope would miss it and the INSERT that
    followed would hit the unique constraint. The lookup runs inside the scope
    for that reason.
    """
    async with session_factory() as session, session.begin():
        organizations = OrganizationService(OrganizationRepository(session))
        organization = await organizations.create_organization(name="Repeat Probe")
        products = products_for_session(session)

        # Simulate a repaired grant: suspend it, then re-provision. Scoped,
        # because the policy would otherwise hide the row and the UPDATE would
        # silently touch nothing.
        await _scope_to(session, organization.id)
        suspended = await session.execute(
            text(
                "UPDATE platform.product_entitlements SET status = 'SUSPENDED' "
                "WHERE organization_id = :org"
            ),
            {"org": organization.id},
        )
        assert suspended.rowcount == 1, "the grant to be repaired was not found"

        await products.grant_default_products(organization.id)

        entitled = await products.is_entitled(
            organization_id=organization.id, code=CRM_PRODUCT_CODE
        )
        count = await session.scalar(
            text(
                "SELECT count(*) FROM platform.product_entitlements "
                "WHERE organization_id = :org"
            ),
            {"org": organization.id},
        )

    assert entitled, "re-provisioning must reactivate a suspended entitlement"
    assert count == 1, "re-provisioning must not duplicate the grant"


async def test_a_provisioned_tenants_rows_are_still_isolated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The scope is a narrow exception, not a hole.

    Having written the entitlement, the policy must still hide it from anyone
    else — otherwise ``provisioning_scope`` would have bought correctness at
    the cost of the guarantee it was protecting.
    """
    async with session_factory() as session, session.begin():
        organizations = OrganizationService(OrganizationRepository(session))
        organization = await organizations.create_organization(name="Isolation Probe")

    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_org_id', :value, true)"),
            {"value": str(uuid.uuid4())},  # some other tenant
        )
        visible = await session.scalar(
            text(
                "SELECT count(*) FROM platform.product_entitlements "
                "WHERE organization_id = :org"
            ),
            {"org": organization.id},
        )

    assert visible == 0, "another tenant must not see this organization's entitlement"
