"""Self-service onboarding: account, then organization, then apps.

The journey a brand-new customer takes, and the boundaries it must not cross.
Three properties matter more than the happy path and each has its own test:

* signing up creates an **identity, not a tenant** — the step that keeps an
  invited user from accidentally founding an organization of their own;
* the apps a signup asks for are a *filter over* what self-service permits,
  never a list of things to grant (ADR-011);
* a session with no organization can exist, and still reaches nothing.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from tests.integration.conftest import Tenant, scope_session_to

pytestmark = pytest.mark.integration

SIGNUP_PASSWORD = "Str0ngPassphrase!"


def _signup(
    client: TestClient,
    settings: Settings,
    *,
    email: str,
    first_name: str = "New",
    last_name: str = "Customer",
) -> str:
    """Create an account and return its access token."""
    response = client.post(
        f"{settings.api_prefix}/auth/signup",
        json={
            "email": email,
            "password": SIGNUP_PASSWORD,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str, organization_id: uuid.UUID | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if organization_id is not None:
        headers["X-Organization-Id"] = str(organization_id)
    return headers


# --- Signing up -------------------------------------------------------------


def test_signing_up_creates_an_identity_but_no_organization(
    client: TestClient, integration_settings: Settings
) -> None:
    """The property the whole two-step wizard rests on.

    If signup created a tenant, an invited user who followed the "create an
    account" link would end up in an organization of their own instead of the
    one that invited them — the failure Phase 11 warns about. It is prevented
    here, structurally, by signup simply not creating one.
    """
    token = _signup(client, integration_settings, email="founder@newco.example")

    me = client.get(f"{integration_settings.api_prefix}/auth/me", headers=_auth(token))

    assert me.status_code == 200
    body = me.json()
    assert body["memberships"] == []
    assert body["active_organization_id"] is None
    assert body["permissions"] == []


def test_a_session_with_no_organization_reaches_no_tenant_data(
    client: TestClient, integration_settings: Settings
) -> None:
    """A tenant-less token is valid for identity and useless for everything else."""
    token = _signup(client, integration_settings, email="nobody@newco.example")

    response = client.get(
        f"{integration_settings.api_prefix}/crm/leads", headers=_auth(token)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tenant_context_required"


def test_signing_up_with_an_address_already_registered_is_refused(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    response = client.post(
        f"{integration_settings.api_prefix}/auth/signup",
        json={
            "email": alpha.admin.email,
            "password": SIGNUP_PASSWORD,
            "first_name": "Impostor",
            "last_name": "Person",
        },
    )

    assert response.status_code == 409


def test_a_weak_password_is_refused_at_signup(
    client: TestClient, integration_settings: Settings
) -> None:
    """Self-service must not be a way around the configured password policy."""
    response = client.post(
        f"{integration_settings.api_prefix}/auth/signup",
        json={
            "email": "weak@newco.example",
            "password": "short",
            "first_name": "Weak",
            "last_name": "Password",
        },
    )

    assert response.status_code == 422


# --- Signing in without an organization -------------------------------------


def test_a_user_with_no_organization_can_still_sign_in(
    client: TestClient, integration_settings: Settings
) -> None:
    """Otherwise signup is a trap.

    Somebody who creates an account and closes the tab before finishing
    onboarding has a real account and a valid password. Refusing them at login
    left them permanently locked out of the very screen that would have fixed
    it.
    """
    _signup(client, integration_settings, email="abandoned@newco.example")

    response = client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={"email": "abandoned@newco.example", "password": SIGNUP_PASSWORD},
    )

    assert response.status_code == 200
    assert response.json()["organization_id"] is None


def test_naming_an_organization_you_do_not_belong_to_is_still_refused(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """The regression guard on the change above.

    Allowing a tenant-less login must not have widened the case where a caller
    *names* an organization: that is still an authorization decision, and it
    still fails.
    """
    _signup(client, integration_settings, email="outsider@newco.example")

    response = client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={
            "email": "outsider@newco.example",
            "password": SIGNUP_PASSWORD,
            "organization_id": str(alpha.organization_id),
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_organization"


# --- Creating the organization ----------------------------------------------


def test_creating_an_organization_makes_the_founder_its_administrator(
    client: TestClient, integration_settings: Settings
) -> None:
    """One request produces a usable tenant: membership, Admin role, CRM."""
    token = _signup(client, integration_settings, email="owner@acme.example")

    created = client.post(
        f"{integration_settings.api_prefix}/organizations",
        headers=_auth(token),
        json={
            "name": "Acme Analytics",
            "industry": "Technology",
            "company_size": "11-50",
            "country": "United Kingdom",
            "app_codes": ["s3k-crm"],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    organization_id = uuid.UUID(body["organization"]["id"])
    assert body["organization"]["slug"] == "acme-analytics"
    assert body["granted_app_codes"] == ["s3k-crm"]

    me = client.get(
        f"{integration_settings.api_prefix}/auth/me",
        headers=_auth(token, organization_id),
    ).json()
    assert len(me["memberships"]) == 1
    assert me["memberships"][0]["roles"] == ["Admin"]
    assert me["memberships"][0]["is_default"] is True


def test_a_new_organization_can_use_the_crm_immediately(
    client: TestClient, integration_settings: Settings
) -> None:
    """The whole point of provisioning inside the creating transaction.

    A tenant that exists but cannot open the product it just chose is a
    half-built state the customer meets as a broken product on their first
    visit.
    """
    token = _signup(client, integration_settings, email="user@readynow.example")
    created = client.post(
        f"{integration_settings.api_prefix}/organizations",
        headers=_auth(token),
        json={"name": "Ready Now", "app_codes": ["s3k-crm"]},
    )
    organization_id = uuid.UUID(created.json()["organization"]["id"])

    listed = client.get(
        f"{integration_settings.api_prefix}/crm/leads",
        headers=_auth(token, organization_id),
    )

    assert listed.status_code == 200
    assert listed.json()["data"] == []


async def test_a_new_organization_is_given_a_default_pipeline(
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The CRM's provisioning hook ran.

    Without it no opportunity can be created, because an opportunity needs a
    stage — so the Deals screen would refuse every save on a brand-new tenant.
    """
    token = _signup(client, integration_settings, email="deals@pipeline.example")
    created = client.post(
        f"{integration_settings.api_prefix}/organizations",
        headers=_auth(token),
        json={"name": "Pipeline Co", "app_codes": ["s3k-crm"]},
    )
    organization_id = uuid.UUID(created.json()["organization"]["id"])

    async with session_factory() as session:
        await scope_session_to(session, organization_id)
        stages = await session.scalar(
            text(
                "SELECT count(*) FROM crm.pipeline_stages WHERE organization_id = :org"
            ),
            {"org": organization_id},
        )

    assert stages is not None and stages > 0


def test_two_organizations_with_the_same_name_get_distinct_slugs(
    client: TestClient, integration_settings: Settings
) -> None:
    """Self-service cannot fail on a name collision with a tenant you cannot see."""
    first = _signup(client, integration_settings, email="one@duplicate.example")
    second = _signup(client, integration_settings, email="two@duplicate.example")

    a = client.post(
        f"{integration_settings.api_prefix}/organizations",
        headers=_auth(first),
        json={"name": "Duplicate Ltd", "app_codes": ["s3k-crm"]},
    )
    b = client.post(
        f"{integration_settings.api_prefix}/organizations",
        headers=_auth(second),
        json={"name": "Duplicate Ltd", "app_codes": ["s3k-crm"]},
    )

    assert a.status_code == 201
    assert b.status_code == 201
    assert a.json()["organization"]["slug"] == "duplicate-ltd"
    assert b.json()["organization"]["slug"] == "duplicate-ltd-2"


def test_creating_an_organization_requires_authentication(
    client: TestClient, integration_settings: Settings
) -> None:
    response = client.post(
        f"{integration_settings.api_prefix}/organizations",
        json={"name": "Anonymous Ltd", "app_codes": ["s3k-crm"]},
    )

    assert response.status_code == 401


# --- App selection is a filter, not a grant ---------------------------------


def test_asking_for_an_unavailable_app_at_signup_grants_nothing(
    client: TestClient, integration_settings: Settings
) -> None:
    """The ADR-011 boundary, exercised from the one place a client picks apps.

    ``s3k-finance`` is a real catalogue row, so this is not rejected as an
    unknown code — it is rejected because self-service may not license it. A
    payload naming it must produce no entitlement and no error that would tell
    the caller the code was real.
    """
    token = _signup(client, integration_settings, email="greedy@newco.example")

    created = client.post(
        f"{integration_settings.api_prefix}/organizations",
        headers=_auth(token),
        json={
            "name": "Greedy Ltd",
            "app_codes": ["s3k-crm", "s3k-finance", "s3k-hr"],
        },
    )
    assert created.status_code == 201
    assert created.json()["granted_app_codes"] == ["s3k-crm"]

    organization_id = uuid.UUID(created.json()["organization"]["id"])
    entitlements = client.get(
        f"{integration_settings.api_prefix}/products/entitlements",
        headers=_auth(token, organization_id),
    ).json()

    assert [row["product_code"] for row in entitlements] == ["s3k-crm"]


def test_the_catalogue_lists_only_the_crm_as_available(
    client: TestClient, integration_settings: Settings
) -> None:
    """Nothing unbuilt may advertise itself as usable.

    This is the test that fails the day somebody adds an app to the catalogue
    and marks it AVAILABLE before there is anything behind it.
    """
    token = _signup(client, integration_settings, email="browser@newco.example")

    catalogue = client.get(
        f"{integration_settings.api_prefix}/products/catalogue", headers=_auth(token)
    )

    assert catalogue.status_code == 200
    rows = catalogue.json()
    available = [row["code"] for row in rows if row["availability"] == "AVAILABLE"]
    self_serve = [row["code"] for row in rows if row["self_serve"]]
    assert available == ["s3k-crm"]
    assert self_serve == ["s3k-crm"]


def test_the_catalogue_requires_authentication(
    client: TestClient, integration_settings: Settings
) -> None:
    response = client.get(f"{integration_settings.api_prefix}/products/catalogue")

    assert response.status_code == 401
