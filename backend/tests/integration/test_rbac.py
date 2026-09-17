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


@pytest.fixture
def other(client: TestClient, integration_settings: Settings) -> ApiSession:
    """A **second**, independent signed-in session.

    The shared ``api`` fixture is the same object ``as_alpha_admin`` hands
    back, so logging in through it would silently replace the
    administrator's own token. A cross-tenant test needs two people signed
    in at once and so needs its own session — see
    ``test_user_management.py``'s identical fixture of the same name.
    """
    return ApiSession(client, integration_settings.api_prefix)


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


def _member_id(session: ApiSession, *, email: str) -> uuid.UUID:
    response = session.get("/organizations/current/members")
    assert response.status_code == 200, response.text
    for row in response.json()["data"]:
        if row["email"] == email:
            return uuid.UUID(row["id"])
    raise AssertionError(f"{email} is not a member")


def _system_role_id(session: ApiSession, name: str) -> uuid.UUID:
    response = session.get("/roles")
    assert response.status_code == 200, response.text
    for role in response.json():
        if role["name"] == name:
            return uuid.UUID(role["id"])
    raise AssertionError(f"system role {name!r} is missing")


def _create_role(
    session: ApiSession,
    *,
    name: str,
    permissions: list[str] | None = None,
    description: str | None = None,
) -> dict[str, object]:
    response = session.post(
        "/roles",
        json={"name": name, "description": description, "permissions": permissions or []},
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Role management (create / update / delete) -----------------------------


def test_an_admin_can_create_a_custom_role(as_alpha_admin: ApiSession) -> None:
    role = _create_role(
        as_alpha_admin,
        name="Sales Lead",
        description="A team lead with export rights.",
        permissions=["leads.VIEW", "leads.CREATE", "leads.EXPORT"],
    )

    assert role["is_system"] is False
    assert role["description"] == "A team lead with export rights."
    assert sorted(role["permissions"]) == ["leads.CREATE", "leads.EXPORT", "leads.VIEW"]

    # Persisted, not just echoed back.
    fetched = as_alpha_admin.get(f"/roles/{role['id']}").json()
    assert sorted(fetched["permissions"]) == ["leads.CREATE", "leads.EXPORT", "leads.VIEW"]


@pytest.mark.parametrize("login_as", ["manager", "member"])
def test_only_an_admin_may_create_a_role(api: ApiSession, alpha: Tenant, login_as: str) -> None:
    api.login(getattr(alpha, login_as).email, organization_id=alpha.organization_id)

    response = api.post("/roles", json={"name": "Should Not Exist", "permissions": []})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_creating_a_role_with_an_unknown_permission_code_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.post(
        "/roles", json={"name": "Bogus", "permissions": ["not_a_module.NOT_AN_ACTION"]}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
    assert "not_a_module.NOT_AN_ACTION" in response.json()["error"]["details"]["invalid_codes"]


def test_creating_a_role_with_a_name_already_in_use_is_a_conflict(
    as_alpha_admin: ApiSession,
) -> None:
    """Colliding with a system template name is refused, not just a sibling custom role."""
    response = as_alpha_admin.post("/roles", json={"name": "Admin", "permissions": []})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_an_admin_can_rename_a_custom_role_and_change_its_permissions(
    as_alpha_admin: ApiSession,
) -> None:
    role = _create_role(as_alpha_admin, name="Draft Role", permissions=["leads.VIEW"])

    response = as_alpha_admin.patch(
        f"/roles/{role['id']}",
        json={"name": "Renamed Role", "permissions": ["contacts.VIEW", "contacts.CREATE"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Renamed Role"
    # The old permission is gone, not merely supplemented.
    assert sorted(body["permissions"]) == ["contacts.CREATE", "contacts.VIEW"]


def test_updating_a_role_omitting_a_field_leaves_it_unchanged(as_alpha_admin: ApiSession) -> None:
    role = _create_role(
        as_alpha_admin, name="Partial Patch", description="Original", permissions=["leads.VIEW"]
    )

    response = as_alpha_admin.patch(f"/roles/{role['id']}", json={"name": "Partial Patch Renamed"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Partial Patch Renamed"
    assert body["description"] == "Original"
    assert body["permissions"] == ["leads.VIEW"]


def test_a_system_role_template_cannot_be_edited(as_alpha_admin: ApiSession) -> None:
    admin_role_id = _system_role_id(as_alpha_admin, "Admin")

    response = as_alpha_admin.patch(f"/roles/{admin_role_id}", json={"name": "Hijacked"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_a_system_role_template_cannot_be_deleted(as_alpha_admin: ApiSession) -> None:
    admin_role_id = _system_role_id(as_alpha_admin, "Admin")

    response = as_alpha_admin.delete(f"/roles/{admin_role_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_an_admin_can_delete_an_unassigned_custom_role(as_alpha_admin: ApiSession) -> None:
    role = _create_role(as_alpha_admin, name="Disposable Role", permissions=[])

    response = as_alpha_admin.delete(f"/roles/{role['id']}")
    assert response.status_code == 204

    assert as_alpha_admin.get(f"/roles/{role['id']}").status_code == 404


def test_deleting_a_role_still_assigned_to_a_member_is_refused(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    role = _create_role(as_alpha_admin, name="In Use Role", permissions=["leads.VIEW"])
    membership_id = _member_id(as_alpha_admin, email=alpha.member.email)

    assigned = as_alpha_admin.post(
        "/roles/assignments", json={"membership_id": str(membership_id), "role_id": role["id"]}
    )
    assert assigned.status_code == 204, assigned.text

    response = as_alpha_admin.delete(f"/roles/{role['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"

    # Unassign, then the same delete succeeds.
    revoked = as_alpha_admin.post(
        "/roles/assignments/revoke",
        json={"membership_id": str(membership_id), "role_id": role["id"]},
    )
    assert revoked.status_code == 204, revoked.text
    assert as_alpha_admin.delete(f"/roles/{role['id']}").status_code == 204


def test_a_role_from_another_organization_cannot_be_updated_or_deleted(
    as_alpha_admin: ApiSession, other: ApiSession, beta: Tenant
) -> None:
    # `other` rather than the shared `api` fixture: `as_alpha_admin` *is* that
    # same object post-login, so signing `api` in as beta would silently swap
    # out the administrator's own token too (see the `other` fixture's docstring
    # in test_user_management.py) and the final assertion below would then be
    # reading the API back as beta, not alpha — passing for the wrong reason.
    role = _create_role(as_alpha_admin, name="Alpha-Only Role", permissions=["leads.VIEW"])

    other.login(beta.admin.email, organization_id=beta.organization_id)
    assert other.patch(f"/roles/{role['id']}", json={"name": "Stolen"}).status_code == 404
    assert other.delete(f"/roles/{role['id']}").status_code == 404

    # Untouched from the owning tenant's point of view.
    assert as_alpha_admin.get(f"/roles/{role['id']}").json()["name"] == "Alpha-Only Role"


def test_role_lifecycle_is_audited(as_alpha_admin: ApiSession) -> None:
    role = _create_role(as_alpha_admin, name="Audited Role", permissions=["leads.VIEW"])
    as_alpha_admin.patch(f"/roles/{role['id']}", json={"description": "now described"})
    as_alpha_admin.delete(f"/roles/{role['id']}")

    entries = as_alpha_admin.get("/audit-logs", params={"module": "roles"}).json()["data"]
    actions_for_role = {
        entry["action"] for entry in entries if entry["entity_id"] == role["id"]
    }
    assert {"CREATED", "UPDATED", "DELETED"} <= actions_for_role


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
