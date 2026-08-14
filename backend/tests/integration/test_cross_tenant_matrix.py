"""Cross-tenant access matrix across every write-capable CRM module.

``test_tenant_isolation_api.py`` proves the matrix for Accounts. Isolation is
only as strong as its weakest endpoint, so this suite repeats the same attacks
against Leads and Opportunities, and covers the operations a single-entity
suite leaves untested: mutating another tenant's record, and reaching one
through a *nested* route parameter.

Every request below is made by a fully authenticated, fully authorised user —
Admin in their own organization. The only thing they lack is membership of the
organization that owns the target record.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


# --- Helpers ----------------------------------------------------------------


def _seed_lead(session: ApiSession, first_name: str) -> uuid.UUID:
    response = session.post(
        "/crm/leads", json={"first_name": first_name, "last_name": "Target"}
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def _seed_opportunity(session: ApiSession, name: str) -> tuple[uuid.UUID, uuid.UUID]:
    account = session.post("/crm/accounts", json={"name": f"{name} Account"})
    assert account.status_code == 201, account.text

    stages = session.get("/crm/opportunities/stages").json()
    stage_id = next(s["id"] for s in stages if s["name"] == "Qualification")

    response = session.post(
        "/crm/opportunities",
        json={"name": name, "account_id": account.json()["id"], "stage_id": stage_id},
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"]), uuid.UUID(account.json()["id"])


@pytest.fixture
def victim_lead(api: ApiSession, beta: Tenant) -> uuid.UUID:
    """A lead owned by beta, for alpha to try to reach."""
    api.login(beta.admin.email, organization_id=beta.organization_id)
    return _seed_lead(api, "BetaPrivate")


@pytest.fixture
def victim_opportunity(api: ApiSession, beta: Tenant) -> uuid.UUID:
    api.login(beta.admin.email, organization_id=beta.organization_id)
    opportunity_id, _account_id = _seed_opportunity(api, "Beta Secret Deal")
    return opportunity_id


# --- Leads ------------------------------------------------------------------


def test_another_tenants_lead_cannot_be_read(
    api: ApiSession, alpha: Tenant, victim_lead: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    assert api.get(f"/crm/leads/{victim_lead}").status_code == 404


def test_another_tenants_lead_cannot_be_updated(
    api: ApiSession, alpha: Tenant, victim_lead: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    response = api.patch(f"/crm/leads/{victim_lead}", json={"first_name": "Hijacked"})

    assert response.status_code == 404


def test_another_tenants_lead_cannot_be_archived(
    api: ApiSession, alpha: Tenant, victim_lead: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    assert api.delete(f"/crm/leads/{victim_lead}").status_code == 404


def test_another_tenants_lead_cannot_be_advanced_through_its_lifecycle(
    api: ApiSession, alpha: Tenant, victim_lead: uuid.UUID
) -> None:
    """Workflow routes are a separate code path from generic CRUD."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    response = api.post(f"/crm/leads/{victim_lead}/status", json={"status": "CONTACTED"})

    assert response.status_code == 404


def test_another_tenants_lead_cannot_be_reassigned(
    api: ApiSession, alpha: Tenant, victim_lead: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    response = api.post(
        f"/crm/leads/{victim_lead}/owner", json={"owner_id": str(uuid.uuid4())}
    )

    assert response.status_code == 404


def test_another_tenants_lead_cannot_be_converted(
    api: ApiSession, alpha: Tenant, victim_lead: uuid.UUID
) -> None:
    """Conversion writes three tables; it must not be reachable cross-tenant."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    response = api.post(f"/crm/leads/{victim_lead}/convert", json={})

    assert response.status_code == 404


def test_the_victim_lead_survives_every_attempt(
    api: ApiSession, alpha: Tenant, beta: Tenant, victim_lead: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    api.patch(f"/crm/leads/{victim_lead}", json={"first_name": "Hijacked"})
    api.post(f"/crm/leads/{victim_lead}/status", json={"status": "CONTACTED"})
    api.delete(f"/crm/leads/{victim_lead}")

    api.login(beta.admin.email, organization_id=beta.organization_id)
    survivor = api.get(f"/crm/leads/{victim_lead}")

    assert survivor.status_code == 200
    assert survivor.json()["first_name"] == "BetaPrivate"
    assert survivor.json()["status"] == "NEW"


# --- Opportunities ----------------------------------------------------------


def test_another_tenants_opportunity_cannot_be_read(
    api: ApiSession, alpha: Tenant, victim_opportunity: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    assert api.get(f"/crm/opportunities/{victim_opportunity}").status_code == 404


def test_another_tenants_opportunity_cannot_be_updated(
    api: ApiSession, alpha: Tenant, victim_opportunity: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    response = api.patch(
        f"/crm/opportunities/{victim_opportunity}", json={"deal_value": "1.00"}
    )

    assert response.status_code == 404


def test_another_tenants_opportunity_cannot_be_moved_between_stages(
    api: ApiSession, alpha: Tenant, victim_opportunity: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    own_stages = api.get("/crm/opportunities/stages").json()
    own_stage_id = own_stages[0]["id"]

    response = api.post(
        f"/crm/opportunities/{victim_opportunity}/stage", json={"stage_id": own_stage_id}
    )

    assert response.status_code == 404


def test_another_tenants_opportunity_history_is_not_readable(
    api: ApiSession, alpha: Tenant, victim_opportunity: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    assert api.get(f"/crm/opportunities/{victim_opportunity}/history").status_code == 404


def test_another_tenants_opportunity_cannot_be_archived(
    api: ApiSession, alpha: Tenant, victim_opportunity: uuid.UUID
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    assert api.delete(f"/crm/opportunities/{victim_opportunity}").status_code == 404


def test_an_opportunity_cannot_be_created_against_another_tenants_account(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """The foreign key is the attack surface here, not the record id."""
    api.login(beta.admin.email, organization_id=beta.organization_id)
    foreign_account = api.post("/crm/accounts", json={"name": "Beta Co"}).json()["id"]

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    stage_id = api.get("/crm/opportunities/stages").json()[0]["id"]

    response = api.post(
        "/crm/opportunities",
        json={
            "name": "Planted In Beta",
            "account_id": foreign_account,
            "stage_id": stage_id,
        },
    )

    assert response.status_code == 404


# --- Listing never leaks ----------------------------------------------------


@pytest.mark.parametrize("path", ["/crm/leads", "/crm/opportunities", "/crm/accounts"])
def test_listing_never_returns_another_tenants_records(
    api: ApiSession, alpha: Tenant, beta: Tenant, path: str
) -> None:
    api.login(beta.admin.email, organization_id=beta.organization_id)
    _seed_lead(api, "BetaLead")
    _seed_opportunity(api, "Beta Deal")

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    body = api.get(f"{path}?page_size=200").json()

    assert body["pagination"]["total"] == 0
    assert body["data"] == []
