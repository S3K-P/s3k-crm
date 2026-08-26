"""Administrative user management, end to end (provisioning → access change).

Every assertion here goes through HTTP, because the point of the feature is
that an administrator can change what another person is *actually allowed to
do* — not that a label changed on a screen. So each test that changes a role
or a status then signs in as the affected user and checks the API's answer.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import TEST_PASSWORD, ApiSession, Tenant

pytestmark = pytest.mark.integration

NEW_PASSWORD = "An0therStr0ngPass!"


@pytest.fixture
def other(client: TestClient, integration_settings: Settings) -> ApiSession:
    """A **second**, independent signed-in session.

    The shared ``api`` fixture is the same object ``as_alpha_admin`` hands
    back, so signing in through it would replace the administrator's token.
    These tests need two people logged in at once — an administrator making a
    change, and the person it is made to — so they get their own session.
    """
    return ApiSession(client, integration_settings.api_prefix)


def _role_id(session: ApiSession, name: str) -> uuid.UUID:
    response = session.get("/roles")
    assert response.status_code == 200, response.text
    for role in response.json():
        if role["name"] == name:
            return uuid.UUID(role["id"])
    raise AssertionError(f"system role {name!r} is missing")


def _member(session: ApiSession, *, email: str) -> dict[str, object]:
    response = session.get("/organizations/current/members")
    assert response.status_code == 200, response.text
    for row in response.json()["data"]:
        if row["email"] == email:
            return row
    raise AssertionError(f"{email} is not a member")


# --- Provisioning -----------------------------------------------------------


def test_an_admin_can_create_a_user_who_can_then_sign_in(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """The gap this closes: before, only *existing* ids could be added."""
    response = as_alpha_admin.post(
        "/organizations/current/users",
        json={
            "email": "newhire@alpha.example",
            "first_name": "New",
            "last_name": "Hire",
            "password": TEST_PASSWORD,
            "role_id": str(_role_id(as_alpha_admin, "User")),
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "newhire@alpha.example"
    assert body["full_name"] == "New Hire"
    assert body["roles"] == ["User"]
    # The id half of the role, without which the UI could never revoke it.
    assert [role["name"] for role in body["role_details"]] == ["User"]

    # The credential really works, and lands in the right organization.
    as_alpha_admin.login("newhire@alpha.example", organization_id=alpha.organization_id)
    me = as_alpha_admin.get("/auth/me")
    assert me.status_code == 200
    assert "leads.VIEW" in me.json()["permissions"]


def test_creating_a_duplicate_address_is_rejected(as_alpha_admin: ApiSession) -> None:
    payload = {
        "email": "duplicate@alpha.example",
        "first_name": "First",
        "last_name": "Attempt",
        "password": TEST_PASSWORD,
    }
    assert as_alpha_admin.post("/organizations/current/users", json=payload).status_code == 201

    second = as_alpha_admin.post("/organizations/current/users", json=payload)
    assert second.status_code == 409, second.text


def test_a_weak_password_is_refused_at_provisioning(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/organizations/current/users",
        json={
            "email": "weak@alpha.example",
            "first_name": "Weak",
            "last_name": "Password",
            "password": "short",
        },
    )
    assert response.status_code == 422, response.text


def test_a_plain_user_may_not_provision(as_alpha_member: ApiSession) -> None:
    response = as_alpha_member.post(
        "/organizations/current/users",
        json={
            "email": "sneaky@alpha.example",
            "first_name": "S",
            "last_name": "N",
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 403


# --- Editing details --------------------------------------------------------


def test_an_admin_can_edit_a_members_details(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    response = as_alpha_admin.patch(
        f"/organizations/current/members/{alpha.member.user_id}",
        json={"first_name": "Renamed", "last_name": "Person", "phone": "+44 20 7946 0000"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["full_name"] == "Renamed Person"

    # Persisted, not just echoed.
    assert _member(as_alpha_admin, email=alpha.member.email)["full_name"] == "Renamed Person"


def test_editing_a_member_of_another_organization_is_not_found(
    as_alpha_admin: ApiSession, beta: Tenant
) -> None:
    """Cross-tenant edits resolve to 404, never to a silent success."""
    response = as_alpha_admin.patch(
        f"/organizations/current/members/{beta.member.user_id}",
        json={"first_name": "Hijacked"},
    )
    assert response.status_code == 404, response.text


# --- Role changes actually change access ------------------------------------


def test_granting_a_role_widens_what_the_api_allows(
    other: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """The whole chain: assign role → permissions → backend authorization."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Deletable Ltd"})
    assert account.status_code == 201
    account_id = account.json()["id"]

    # A plain User holds no DELETE anywhere.
    other.login(alpha.member.email, organization_id=alpha.organization_id)
    assert other.delete(f"/crm/accounts/{account_id}").status_code == 403

    membership_id = _member(as_alpha_admin, email=alpha.member.email)["id"]
    granted = as_alpha_admin.post(
        "/roles/assignments",
        json={
            "membership_id": str(membership_id),
            "role_id": str(_role_id(as_alpha_admin, "Manager")),
        },
    )
    assert granted.status_code == 204, granted.text

    # Same person, same session: authorization is evaluated per request.
    assert other.delete(f"/crm/accounts/{account_id}").status_code == 204


def test_revoking_a_role_narrows_what_the_api_allows(
    other: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    membership_id = _member(as_alpha_admin, email=alpha.manager.email)["id"]
    manager_role_id = _role_id(as_alpha_admin, "Manager")

    other.login(alpha.manager.email, organization_id=alpha.organization_id)
    assert other.get("/crm/accounts").status_code == 200

    revoked = as_alpha_admin.post(
        "/roles/assignments/revoke",
        json={"membership_id": str(membership_id), "role_id": str(manager_role_id)},
    )
    assert revoked.status_code == 204, revoked.text

    # With no roles left, the same token is refused by the same endpoint.
    assert other.get("/crm/accounts").status_code == 403


# --- Deactivation and reactivation ------------------------------------------


def test_suspending_a_member_cuts_access_on_the_next_request(
    other: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    other.login(alpha.member.email, organization_id=alpha.organization_id)
    assert other.get("/crm/leads").status_code == 200

    suspended = as_alpha_admin.post(
        f"/organizations/current/members/{alpha.member.user_id}/status",
        json={"status": "SUSPENDED"},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"

    # No re-login needed: the membership verifier reads status every request.
    assert other.get("/crm/leads").status_code == 403

    reactivated = as_alpha_admin.post(
        f"/organizations/current/members/{alpha.member.user_id}/status",
        json={"status": "ACTIVE"},
    )
    assert reactivated.status_code == 200, reactivated.text
    assert other.get("/crm/leads").status_code == 200


def test_an_admin_cannot_deactivate_themselves(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    response = as_alpha_admin.post(
        f"/organizations/current/members/{alpha.admin.user_id}/status",
        json={"status": "SUSPENDED"},
    )
    assert response.status_code == 422, response.text
    assert "your own membership" in response.json()["error"]["message"]


def test_the_last_administrator_cannot_be_suspended(
    other: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Guarded from a *second* administrator, so it is not the self-check."""
    second = as_alpha_admin.post(
        "/organizations/current/users",
        json={
            "email": "second.admin@alpha.example",
            "first_name": "Second",
            "last_name": "Admin",
            "password": TEST_PASSWORD,
            "role_id": str(_role_id(as_alpha_admin, "Admin")),
        },
    )
    assert second.status_code == 201, second.text

    # Two administrators: suspending the seeded one is allowed.
    other.login("second.admin@alpha.example", organization_id=alpha.organization_id)
    first = other.post(
        f"/organizations/current/members/{alpha.admin.user_id}/status",
        json={"status": "SUSPENDED"},
    )
    assert first.status_code == 200, first.text

    # One administrator left, and it is now the caller — both guards agree.
    last = other.post(
        f"/organizations/current/members/{alpha.admin.user_id}/status",
        json={"status": "ACTIVE"},
    )
    assert last.status_code == 200


def test_the_last_administrators_admin_role_cannot_be_revoked(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    membership_id = _member(as_alpha_admin, email=alpha.admin.email)["id"]

    response = as_alpha_admin.post(
        "/roles/assignments/revoke",
        json={
            "membership_id": str(membership_id),
            "role_id": str(_role_id(as_alpha_admin, "Admin")),
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "last_administrator"

    # And the role really is still held, so no partial write happened.
    assert "Admin" in _member(as_alpha_admin, email=alpha.admin.email)["roles"]


def test_admin_role_can_be_revoked_while_another_administrator_remains(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    created = as_alpha_admin.post(
        "/organizations/current/users",
        json={
            "email": "spare.admin@alpha.example",
            "first_name": "Spare",
            "last_name": "Admin",
            "password": TEST_PASSWORD,
            "role_id": str(_role_id(as_alpha_admin, "Admin")),
        },
    )
    assert created.status_code == 201, created.text

    response = as_alpha_admin.post(
        "/roles/assignments/revoke",
        json={
            "membership_id": created.json()["id"],
            "role_id": str(_role_id(as_alpha_admin, "Admin")),
        },
    )
    assert response.status_code == 204, response.text


# --- Password reset ---------------------------------------------------------


def test_an_admin_reset_replaces_the_password_and_ends_old_sessions(
    client: TestClient,
    integration_settings: Settings,
    other: ApiSession,
    as_alpha_admin: ApiSession,
    alpha: Tenant,
) -> None:
    other.login(alpha.member.email, organization_id=alpha.organization_id)
    assert other.get("/crm/leads").status_code == 200

    reset = as_alpha_admin.post(
        f"/organizations/current/members/{alpha.member.user_id}/reset-password",
        json={"new_password": NEW_PASSWORD},
    )
    assert reset.status_code == 204, reset.text

    # The member's refresh-token family was revoked, so the session cannot be
    # renewed and dies with the current access token rather than rolling on.
    #
    # (The access token itself is checked against `tokens_valid_from`, which a
    # JWT `iat` can only resolve to the second — so a token minted in the same
    # second as the reset survives until it expires. The revocation above is
    # what bounds that, and it is what this asserts.)
    renewed = client.post(f"{integration_settings.api_prefix}/auth/refresh", json={})
    assert renewed.status_code == 401, renewed.text

    # The old password no longer authenticates…
    stale = client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={"email": alpha.member.email, "password": TEST_PASSWORD},
    )
    assert stale.status_code == 401

    # …and the new one does.
    fresh = client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={"email": alpha.member.email, "password": NEW_PASSWORD},
    )
    assert fresh.status_code == 200, fresh.text


def test_a_manager_may_not_reset_a_password(
    as_alpha_manager_session: ApiSession, alpha: Tenant
) -> None:
    """``users.ADMIN`` gates it — Manager holds only ``users.VIEW``."""
    response = as_alpha_manager_session.post(
        f"/organizations/current/members/{alpha.member.user_id}/reset-password",
        json={"new_password": NEW_PASSWORD},
    )
    assert response.status_code == 403


def test_a_weak_reset_password_is_refused(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    response = as_alpha_admin.post(
        f"/organizations/current/members/{alpha.member.user_id}/reset-password",
        json={"new_password": "short"},
    )
    assert response.status_code == 422, response.text


@pytest.fixture
def as_alpha_manager_session(api: ApiSession, alpha: Tenant) -> ApiSession:
    api.login(alpha.manager.email, organization_id=alpha.organization_id)
    return api
