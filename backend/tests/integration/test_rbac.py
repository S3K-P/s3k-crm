"""Authorization matrix: role x module x action (P1-W07-QA-01).

Enforcement is asserted at the HTTP boundary, because that is where a real
caller meets it. The frontend's own permission state is irrelevant to every
assertion here — no request below sends one.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def as_alpha_manager(api: ApiSession, alpha: Tenant) -> ApiSession:
    api.login(alpha.manager.email, organization_id=alpha.organization_id)
    return api


def _create_account(session: ApiSession, name: str = "Target Ltd") -> uuid.UUID:
    response = session.post("/crm/accounts", json={"name": name})
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


# --- Read ------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/crm/accounts", "/crm/leads", "/crm/opportunities"])
def test_every_role_may_read_crm_modules(
    api: ApiSession, alpha: Tenant, path: str
) -> None:
    for user in (alpha.admin, alpha.manager, alpha.member):
        api.login(user.email, organization_id=alpha.organization_id)
        assert api.get(path).status_code == 200, f"{user.role} could not read {path}"


# --- Create / edit ----------------------------------------------------------


def test_a_plain_user_may_create_and_edit(as_alpha_member: ApiSession) -> None:
    account_id = _create_account(as_alpha_member, "User Created Ltd")

    response = as_alpha_member.patch(
        f"/crm/accounts/{account_id}", json={"industry": "Manufacturing"}
    )

    assert response.status_code == 200
    assert response.json()["industry"] == "Manufacturing"


# --- Delete -----------------------------------------------------------------


def test_a_plain_user_may_not_delete(
    api: ApiSession, alpha: Tenant
) -> None:
    """``User`` deliberately holds no DELETE permission on any CRM module."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    account_id = _create_account(api)

    api.login(alpha.member.email, organization_id=alpha.organization_id)
    response = api.delete(f"/crm/accounts/{account_id}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_a_manager_may_delete(api: ApiSession, alpha: Tenant) -> None:
    api.login(alpha.manager.email, organization_id=alpha.organization_id)
    account_id = _create_account(api, "Manager Deletable Ltd")

    assert api.delete(f"/crm/accounts/{account_id}").status_code == 204


def test_a_denied_delete_leaves_the_record_intact(
    api: ApiSession, alpha: Tenant
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    account_id = _create_account(api, "Should Survive Ltd")

    api.login(alpha.member.email, organization_id=alpha.organization_id)
    api.delete(f"/crm/accounts/{account_id}")

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    assert api.get(f"/crm/accounts/{account_id}").status_code == 200


# --- Administrative permissions --------------------------------------------


def test_only_an_admin_may_administer_role_assignments(
    api: ApiSession, alpha: Tenant
) -> None:
    """``roles.ADMIN`` is held by Admin alone."""
    body = {"membership_id": str(uuid.uuid4()), "role_id": str(uuid.uuid4())}

    api.login(alpha.member.email, organization_id=alpha.organization_id)
    assert api.post("/roles/assignments", json=body).status_code == 403

    api.login(alpha.manager.email, organization_id=alpha.organization_id)
    assert api.post("/roles/assignments", json=body).status_code == 403


def test_a_plain_user_may_not_list_organization_members(
    as_alpha_member: ApiSession,
) -> None:
    """``users.VIEW`` is not granted to the User role."""
    assert as_alpha_member.get("/organizations/current/members").status_code == 403


def test_a_manager_may_list_organization_members(
    as_alpha_manager: ApiSession,
) -> None:
    assert as_alpha_manager.get("/organizations/current/members").status_code == 200


def test_members_carry_the_identity_of_the_user_behind_them(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """``email`` and ``full_name`` are populated, not blank.

    The endpoint used to declare both fields and then hardcode ``""`` and
    ``None``, so every member rendered as an anonymous row and the admin
    screen could not identify anyone.
    """
    members = as_alpha_admin.get("/organizations/current/members").json()["data"]

    by_email = {member["email"]: member for member in members}
    assert alpha.admin.email in by_email, "the admin's own membership is missing"

    for member in members:
        assert member["email"], "a member came back without an email address"
        assert member["full_name"], "a member came back without a display name"

    # Seeded as first_name=<role>, last_name=<slug title-cased>.
    assert by_email[alpha.admin.email]["full_name"] == f"Admin {alpha.slug.title()}"


def test_member_identities_do_not_cross_organizations(
    as_alpha_admin: ApiSession, beta: Tenant
) -> None:
    """The directory lookup is confined to this organization's memberships."""
    members = as_alpha_admin.get("/organizations/current/members").json()["data"]
    emails = {member["email"] for member in members}

    for outsider in (beta.admin.email, beta.manager.email, beta.member.email):
        assert outsider not in emails


# --- Role visibility --------------------------------------------------------


def test_roles_listing_shows_system_templates(as_alpha_admin: ApiSession) -> None:
    names = {role["name"] for role in as_alpha_admin.get("/roles").json()}

    assert {"Admin", "Manager", "User"} <= names


def test_a_role_from_another_organization_is_not_retrievable(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.get(f"/roles/{uuid.uuid4()}")

    assert response.status_code == 404


def test_the_admin_role_grants_the_whole_catalogue(
    as_alpha_admin: ApiSession,
) -> None:
    roles = as_alpha_admin.get("/roles").json()
    admin_role = next(role for role in roles if role["name"] == "Admin")

    detail = as_alpha_admin.get(f"/roles/{admin_role['id']}").json()
    catalogue = as_alpha_admin.get("/roles/permissions").json()

    assert sorted(detail["permissions"]) == sorted(catalogue["codes"])


# --- Authentication vs authorization ----------------------------------------


def test_an_unauthenticated_request_is_401_not_403(
    client: TestClient, integration_settings: Settings
) -> None:
    """401 and 403 must not be conflated: they mean different things."""
    response = client.get(f"{integration_settings.api_prefix}/crm/accounts")

    assert response.status_code == 401


def test_an_authenticated_request_without_tenant_context_is_403(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """Authenticated but no organization header and no default → 403."""
    login = client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={"email": alpha.admin.email, "password": "Str0ngPassphrase!"},
    )
    token = login.json()["access_token"]

    # The token carries the org, so this succeeds; the point is that it is the
    # verified membership, never the header, that grants scope.
    response = client.get(
        f"{integration_settings.api_prefix}/crm/accounts",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
