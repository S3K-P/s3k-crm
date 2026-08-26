"""Cross-tenant access attempts through the HTTP API (P1-W06-QA-01/02).

The database-level guarantee is proven separately in
``test_tenant_isolation.py`` (RLS probe) and ``test_crm_rls.py`` (a real CRM
table). This suite proves the *application* layer: with the local superuser
role RLS is bypassed, so everything asserted here is enforced by the repository
filters and the membership checks alone — which is exactly the defence-in-depth
property worth testing independently.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import TEST_PASSWORD, ApiSession, Tenant

pytestmark = pytest.mark.integration


def _create_account(session: ApiSession, name: str) -> uuid.UUID:
    response = session.post("/crm/accounts", json={"name": name})
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


# --- Listing ----------------------------------------------------------------


def test_each_organization_sees_only_its_own_accounts(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    _create_account(api, "Alpha Industries")

    api.login(beta.admin.email, organization_id=beta.organization_id)
    _create_account(api, "Beta Corporation")

    names = [row["name"] for row in api.get("/crm/accounts").json()["data"]]

    assert names == ["Beta Corporation"]


def test_a_lead_created_in_one_organization_is_invisible_in_the_other(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    api.post("/crm/leads", json={"first_name": "Ada", "last_name": "Lovelace"})

    api.login(beta.admin.email, organization_id=beta.organization_id)
    body = api.get("/crm/leads").json()

    assert body["pagination"]["total"] == 0
    assert body["data"] == []


# --- Direct object reference ------------------------------------------------


def test_reading_another_organizations_account_by_id_returns_404(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """The core IDOR case: a valid id from another tenant must not resolve."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    victim_id = _create_account(api, "Alpha Confidential")

    api.login(beta.admin.email, organization_id=beta.organization_id)
    response = api.get(f"/crm/accounts/{victim_id}")

    assert response.status_code == 404


def test_updating_another_organizations_account_returns_404(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    victim_id = _create_account(api, "Alpha Confidential")

    api.login(beta.admin.email, organization_id=beta.organization_id)
    response = api.patch(f"/crm/accounts/{victim_id}", json={"name": "Owned"})

    assert response.status_code == 404


def test_deleting_another_organizations_account_returns_404(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    victim_id = _create_account(api, "Alpha Confidential")

    api.login(beta.admin.email, organization_id=beta.organization_id)

    assert api.delete(f"/crm/accounts/{victim_id}").status_code == 404


def test_the_victim_record_is_untouched_after_a_cross_tenant_attempt(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    victim_id = _create_account(api, "Alpha Confidential")

    api.login(beta.admin.email, organization_id=beta.organization_id)
    api.patch(f"/crm/accounts/{victim_id}", json={"name": "Owned"})
    api.delete(f"/crm/accounts/{victim_id}")

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    survivor = api.get(f"/crm/accounts/{victim_id}").json()

    assert survivor["name"] == "Alpha Confidential"


# --- Forged organization header ---------------------------------------------


def test_a_forged_organization_header_is_refused(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """Asserting membership of another tenant must not grant its scope."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    response = api.get("/crm/accounts", organization_id=beta.organization_id)

    assert response.status_code == 403


def test_a_forged_header_does_not_leak_data_through_the_error(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(beta.admin.email, organization_id=beta.organization_id)
    _create_account(api, "Beta Secret Project")

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    response = api.get("/crm/accounts", organization_id=beta.organization_id)

    assert "Beta Secret Project" not in response.text


def test_an_organization_header_for_a_nonexistent_org_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.get("/crm/accounts", organization_id=uuid.uuid4())

    assert response.status_code == 403


def test_a_malformed_organization_header_is_refused(
    as_alpha_admin: ApiSession, api_app: FastAPI, integration_settings: Settings
) -> None:
    from fastapi.testclient import TestClient

    with TestClient(api_app) as raw:
        response = raw.get(
            f"{integration_settings.api_prefix}/crm/accounts",
            headers={
                "Authorization": f"Bearer {as_alpha_admin.access_token}",
                "X-Organization-Id": "not-a-uuid",
            },
        )

    assert response.status_code == 403


# --- Login-time organization selection --------------------------------------


def test_logging_into_an_organization_you_do_not_belong_to_is_refused(
    api: ApiSession,
    alpha: Tenant,
    beta: Tenant,
    client: TestClient,
    integration_settings: Settings,
) -> None:
    """Naming another tenant at login fails exactly as a forged header does."""
    response = client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={
            "email": alpha.admin.email,
            "password": TEST_PASSWORD,
            "organization_id": str(beta.organization_id),
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_organization"


# --- Membership status ------------------------------------------------------


def test_a_suspended_member_loses_access_immediately(
    api: ApiSession, alpha: Tenant, integration_settings: Settings
) -> None:
    """Suspension must bite on the next request, not at token expiry."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    api.login(alpha.member.email, organization_id=alpha.organization_id)
    assert api.get("/crm/accounts").status_code == 200

    async def suspend() -> None:
        # A dedicated engine on this loop: asyncpg connections are bound to the
        # loop that opened them, so the fixtures' engine cannot be reused here.
        engine = create_async_engine(integration_settings.database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE platform.organization_memberships SET status = 'SUSPENDED' "
                        "WHERE organization_id = :org AND user_id = :user"
                    ),
                    {"org": alpha.organization_id, "user": alpha.member.user_id},
                )
        finally:
            await engine.dispose()

    asyncio.run(suspend())

    # The access token is still cryptographically valid; the membership is not.
    assert api.get("/crm/accounts").status_code == 403
