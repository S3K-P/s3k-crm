"""Product access control (ADR-011, `P1-W08-BE-02`, `P1-W08-QA-01`, risk R10).

The gate answers a question that sits *in front of* every permission check:
may this organization open this product at all? An administrator with the
entire CRM permission catalogue is refused when their organization holds no
usable entitlement, and no role grant can change that — which is the point,
because otherwise a tenant could license itself.

Every positive is paired with its negative. A test suite that only proves the
gate lets entitled callers in would pass just as happily against no gate at
all, and this control's whole value is what it refuses.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration

#: A representative route from each CRM module, so the gate is shown to cover
#: the whole product rather than one endpoint that happened to be wired.
CRM_ROUTES = [
    "/crm/dashboard/summary",
    "/crm/accounts",
    "/crm/contacts",
    "/crm/leads",
    "/crm/opportunities",
    "/crm/tasks",
    "/crm/notes",
    "/crm/campaigns",
    "/crm/activities",
    "/crm/lead-sources",
    "/crm/search?q=anything",
]


async def _set_entitlement(
    factory: async_sessionmaker[AsyncSession],
    organization_id: object,
    *,
    status: str | None = None,
    expires_at: dt.datetime | None = None,
    delete: bool = False,
) -> None:
    """Rewrite one organization's CRM grant directly.

    Through SQL because there is deliberately no API that grants or revokes —
    entitlements are provisioned, not self-served (ADR-011). This is the test
    standing in for the billing integration that will eventually do it.

    The tenant scope is set first, and it is not optional.
    ``platform.product_entitlements`` is RLS-FORCEd, so a statement issued with
    no ``app.current_org_id`` matches **zero rows** — silently. Written against
    a superuser connection this helper appeared to work; under a role the
    policies actually apply to it changed nothing, every "refused" test got a
    perfectly correct 200, and the gate looked broken when it was the helper
    that had quietly stopped doing anything.

    Hence the rowcount assertion: a fixture that no-ops must fail loudly rather
    than hand the test a false premise.
    """
    async with factory() as session:
        await session.execute(
            text("SELECT set_config('app.current_org_id', :value, false)"),
            {"value": str(organization_id)},
        )
        if delete:
            result = await session.execute(
                text(
                    "DELETE FROM platform.product_entitlements e "
                    "USING platform.products p "
                    "WHERE e.product_id = p.id AND p.code = 's3k-crm' "
                    "  AND e.organization_id = :org"
                ),
                {"org": organization_id},
            )
        else:
            result = await session.execute(
                text(
                    "UPDATE platform.product_entitlements e "
                    "SET status = COALESCE("
                    "  CAST(:status AS platform.entitlement_status), e.status), "
                    "    expires_at = :expires "
                    "FROM platform.products p "
                    "WHERE e.product_id = p.id AND p.code = 's3k-crm' "
                    "  AND e.organization_id = :org"
                ),
                {"org": organization_id, "status": status, "expires": expires_at},
            )
        assert result.rowcount == 1, (
            "the CRM entitlement was not modified — the tenant scope is wrong, "
            "or RLS hid the row"
        )
        await session.commit()


# --- The entitled path ------------------------------------------------------


def test_an_entitled_organization_reaches_the_crm(as_alpha_admin: ApiSession) -> None:
    """Positive control. Without this the refusals below prove nothing."""
    assert as_alpha_admin.get("/crm/accounts").status_code == 200


def test_a_new_organization_is_entitled_on_creation(as_alpha_admin: ApiSession) -> None:
    """Provisioning happens in the same transaction as the tenant.

    A tenant that exists but can open nothing is a half-provisioned state
    somebody would have to notice and repair by hand, and the gate would
    refuse them with a 403 that looks like a bug.
    """
    entitlements = as_alpha_admin.get("/products/entitlements").json()

    crm = next(e for e in entitlements if e["product_code"] == "s3k-crm")
    assert crm["status"] == "ACTIVE"
    assert crm["active"] is True


# --- The refusals -----------------------------------------------------------


@pytest.mark.parametrize("route", CRM_ROUTES)
async def test_every_crm_route_is_refused_without_an_entitlement(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    route: str,
) -> None:
    """The gate covers the product, not one endpoint.

    Parameterised over a route from each module because the guarantee being
    claimed is "before any ``/crm/*`` handler runs" — a gate wired to nine
    routers out of ten is a gate somebody will walk around.
    """
    await _set_entitlement(session_factory, alpha.organization_id, delete=True)

    response = as_alpha_admin.get(route)

    assert response.status_code == 403, route
    assert response.json()["error"]["code"] == "product_not_licensed"


async def test_a_suspended_entitlement_is_refused(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Withheld without being revoked — non-payment, say — still closes the door."""
    await _set_entitlement(session_factory, alpha.organization_id, status="SUSPENDED")

    assert as_alpha_admin.get("/crm/accounts").status_code == 403


async def test_a_revoked_entitlement_is_refused(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _set_entitlement(session_factory, alpha.organization_id, status="REVOKED")

    assert as_alpha_admin.get("/crm/accounts").status_code == 403


async def test_an_expired_entitlement_is_refused(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Expiry is read from the clock, not from a status somebody must update.

    The row stays ACTIVE; only ``expires_at`` has passed. A check that trusted
    the status alone would keep letting this organization in indefinitely.
    """
    past = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    await _set_entitlement(session_factory, alpha.organization_id, expires_at=past)

    assert as_alpha_admin.get("/crm/accounts").status_code == 403


async def test_an_unexpired_entitlement_is_allowed(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Paired with the test above, so the expiry branch is not simply always false."""
    future = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    await _set_entitlement(session_factory, alpha.organization_id, expires_at=future)

    assert as_alpha_admin.get("/crm/accounts").status_code == 200


# --- What the gate is not ---------------------------------------------------


async def test_full_crm_permissions_do_not_substitute_for_an_entitlement(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The distinction ADR-011 exists to draw.

    ``as_alpha_admin`` holds the entire permission catalogue by wildcard. That
    is authorization *within* a product and says nothing about whether the
    organization may open it. If a permission could stand in for a licence,
    any administrator could grant their own tenant a product nobody sold them.
    """
    await _set_entitlement(session_factory, alpha.organization_id, delete=True)

    assert as_alpha_admin.get("/crm/accounts").status_code == 403


async def test_one_tenants_entitlement_does_not_admit_another(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    beta: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Entitlements are per organization, and beta keeping its grant is what
    proves alpha's refusal came from alpha's own row rather than from the
    catalogue being empty."""
    await _set_entitlement(session_factory, alpha.organization_id, delete=True)

    assert as_alpha_admin.get("/crm/accounts").status_code == 403

    beta_entitlement = None
    async with session_factory() as session:
        # Scoped to beta: the entitlements table is RLS-FORCEd, so an unscoped
        # read returns no rows and this assertion would fail for the one reason
        # it is not testing.
        await session.execute(
            text("SELECT set_config('app.current_org_id', :value, false)"),
            {"value": str(beta.organization_id)},
        )
        result = await session.execute(
            text(
                "SELECT e.status FROM platform.product_entitlements e "
                "JOIN platform.products p ON p.id = e.product_id "
                "WHERE p.code = 's3k-crm' AND e.organization_id = :org"
            ),
            {"org": beta.organization_id},
        )
        beta_entitlement = result.scalar_one_or_none()

    assert beta_entitlement == "ACTIVE"


# --- The gate must not preempt authentication -------------------------------


def test_an_unauthenticated_request_is_401_not_403(
    client: TestClient, integration_settings: Settings
) -> None:
    """The regression this gate introduced on its first attempt.

    A router-level dependency resolves *before* the route's own, so a gate
    that reads tenant context directly runs ahead of authentication and turns
    every anonymous request into ``403 product_not_licensed``. That tells a
    merely logged-out caller to contact sales, and it hides a missing token
    behind a commercial error.

    Depending on ``CurrentPrincipal`` puts the auth chain inside the gate, so
    401 wins. Pinned here — rather than relying on the per-module auth tests
    that caught it — because those tests are about their own modules and would
    not explain *why* they broke if this happened again.
    """
    response = client.get(f"{integration_settings.api_prefix}/crm/accounts")

    assert response.status_code == 401


def test_a_forged_token_is_401_not_403(
    client: TestClient, integration_settings: Settings
) -> None:
    """Same ordering, the other way in: a bad token is an auth failure."""
    response = client.get(
        f"{integration_settings.api_prefix}/crm/accounts",
        headers={"Authorization": "Bearer not.a.real.token"},
    )

    assert response.status_code == 401


# --- Platform routes stay reachable -----------------------------------------


async def test_platform_routes_are_not_behind_the_product_gate(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Losing the CRM must not lock somebody out of the platform itself.

    Otherwise an organization whose licence lapsed could not sign in, read its
    own members, or — most importantly — see *why* the CRM stopped working.
    """
    await _set_entitlement(session_factory, alpha.organization_id, delete=True)

    assert as_alpha_admin.get("/organizations/current").status_code == 200
    assert as_alpha_admin.get("/products/entitlements").status_code == 200


async def test_the_entitlements_route_explains_the_refusal(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The 403 is answerable without a database session."""
    await _set_entitlement(session_factory, alpha.organization_id, status="SUSPENDED")

    entitlements = as_alpha_admin.get("/products/entitlements").json()
    crm = next(e for e in entitlements if e["product_code"] == "s3k-crm")

    assert crm["status"] == "SUSPENDED"
    assert crm["active"] is False
