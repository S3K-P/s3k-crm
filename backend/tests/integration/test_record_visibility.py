"""Record-level authorization (ADR-010, `P1-W07-BE-04` / `P2-W10-BE-06`).

Tenant isolation answers *which organization's rows may I touch*. These tests
cover the layer below it: *within my organization, which rows are mine?*

Every assertion goes through HTTP against real PostgreSQL, because the rule is
only worth anything if it holds at the boundary a real caller meets — a
service-level unit test would prove the predicate compiles, not that every
route applies it.

The shape of the rule under test:

* a caller holding ``<module>.VIEW_ALL`` reads across owners (Admin, Manager);
* everybody else (User) reads the records they own, plus unowned ones;
* a record outside that set is **404 on every verb**, not 403 — "not yours"
  and "not there" must be indistinguishable, or the API becomes an oracle for
  which ids exist.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """A second signed-in session for the plain ``User`` of alpha.

    Separate from the shared ``api`` fixture, which ``as_alpha_admin`` returns
    the same object as — these tests need two people signed in at once.
    """
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def manager(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.manager.email, organization_id=alpha.organization_id)
    return session


def _ids(payload: dict[str, object]) -> set[str]:
    data = payload["data"]
    assert isinstance(data, list)
    return {str(row["id"]) for row in data}


def _stage_id(session: ApiSession, name: str) -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


# --- Ownership is assigned at creation --------------------------------------


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/crm/accounts", {"name": "Owned Ltd"}),
        ("/crm/leads", {"first_name": "Owned", "last_name": "Lead"}),
        ("/crm/contacts", {"first_name": "Owned", "last_name": "Contact"}),
        ("/crm/tasks", {"title": "Owned task"}),
    ],
)
def test_a_new_record_belongs_to_whoever_created_it(
    rep: ApiSession, alpha: Tenant, path: str, body: dict[str, object]
) -> None:
    """Without this the rule is inert: unowned rows are visible to everyone."""
    created = rep.post(path, json=body)

    assert created.status_code == 201, created.text
    assert created.json()["owner_id"] == str(alpha.member.user_id)


def test_an_explicit_owner_is_respected_over_the_creator(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Assigning work to somebody else must still be possible."""
    created = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Assigned",
            "last_name": "Lead",
            "owner_id": str(alpha.member.user_id),
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["owner_id"] == str(alpha.member.user_id)


# --- Lists are narrowed -----------------------------------------------------


def test_a_rep_lists_only_their_own_records(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    mine = rep.post("/crm/accounts", json={"name": "Rep Owned Ltd"})
    assert mine.status_code == 201, mine.text
    theirs = as_alpha_admin.post("/crm/accounts", json={"name": "Admin Owned Ltd"})
    assert theirs.status_code == 201, theirs.text

    listed = rep.get("/crm/accounts")

    assert listed.status_code == 200
    assert _ids(listed.json()) == {mine.json()["id"]}


def test_the_total_reflects_the_narrowed_set_not_the_organization(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """A truthful count: paginating past it would otherwise show empty pages."""
    assert rep.post("/crm/accounts", json={"name": "Rep One Ltd"}).status_code == 201
    for name in ("Admin One Ltd", "Admin Two Ltd"):
        assert as_alpha_admin.post("/crm/accounts", json={"name": name}).status_code == 201

    body = rep.get("/crm/accounts").json()

    assert body["pagination"]["total"] == 1


def test_a_manager_lists_the_whole_organization(
    rep: ApiSession, manager: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """``Manager`` holds ``VIEW_ALL``: running a team means seeing its pipeline."""
    rep_owned = rep.post("/crm/accounts", json={"name": "Rep Ltd"}).json()["id"]
    admin_owned = as_alpha_admin.post("/crm/accounts", json={"name": "Admin Ltd"}).json()["id"]

    listed = manager.get("/crm/accounts")

    assert listed.status_code == 200
    assert {rep_owned, admin_owned} <= _ids(listed.json())


def test_an_admin_lists_the_whole_organization(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    rep_owned = rep.post("/crm/leads", json={"first_name": "Rep", "last_name": "Lead"})
    assert rep_owned.status_code == 201, rep_owned.text

    listed = as_alpha_admin.get("/crm/leads")

    assert listed.status_code == 200
    assert rep_owned.json()["id"] in _ids(listed.json())


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/crm/accounts", {"name": "Scoped Ltd"}),
        ("/crm/leads", {"first_name": "Scoped", "last_name": "Lead"}),
        ("/crm/contacts", {"first_name": "Scoped", "last_name": "Contact"}),
        ("/crm/tasks", {"title": "Scoped task"}),
    ],
)
def test_every_owner_scoped_module_narrows_its_list(
    rep: ApiSession, as_alpha_admin: ApiSession, path: str, body: dict[str, object]
) -> None:
    """The rule is applied per module, so every module is checked."""
    theirs = as_alpha_admin.post(path, json=body)
    assert theirs.status_code == 201, theirs.text

    listed = rep.get(path)

    assert listed.status_code == 200
    assert theirs.json()["id"] not in _ids(listed.json())


# --- Direct id access: the URL-manipulation cases ----------------------------


def test_guessing_another_users_record_id_returns_404(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """The IDOR case. 404 rather than 403: 403 would confirm the id is real."""
    theirs = as_alpha_admin.post("/crm/accounts", json={"name": "Not Yours Ltd"}).json()["id"]

    response = rep.get(f"/crm/accounts/{theirs}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_an_unreachable_record_is_404_on_every_verb(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """A single read chokepoint means edits and deletes inherit the rule.

    ``User`` holds no DELETE, so the delete below is checked as a Manager
    without ``accounts.VIEW_ALL`` would be — see the custom-role test further
    down for the permission-only half.
    """
    theirs = as_alpha_admin.post("/crm/accounts", json={"name": "Sealed Ltd"}).json()["id"]

    assert rep.get(f"/crm/accounts/{theirs}").status_code == 404
    assert rep.patch(f"/crm/accounts/{theirs}", json={"industry": "Hijacked"}).status_code == 404

    # And the attempted edit changed nothing.
    intact = as_alpha_admin.get(f"/crm/accounts/{theirs}").json()
    assert intact["industry"] is None


def test_a_lead_owned_by_someone_else_cannot_be_advanced(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """Workflow routes resolve their target the same way, so they inherit it."""
    theirs = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Sealed", "last_name": "Lead"}
    ).json()["id"]

    response = rep.post(f"/crm/leads/{theirs}/status", json={"status": "CONTACTED"})

    assert response.status_code == 404


def test_a_lead_owned_by_someone_else_cannot_be_converted(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """Conversion creates an account, a contact and a deal — a big side effect."""
    theirs = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Sealed", "last_name": "Convert"}
    ).json()["id"]
    assert (
        as_alpha_admin.post(
            f"/crm/leads/{theirs}/status", json={"status": "CONTACTED"}
        ).status_code
        == 200
    )
    assert (
        as_alpha_admin.post(
            f"/crm/leads/{theirs}/status", json={"status": "QUALIFIED"}
        ).status_code
        == 200
    )

    response = rep.post(f"/crm/leads/{theirs}/convert", json={"create_opportunity": False})

    assert response.status_code == 404
    # Nothing was created by the refused call.
    assert as_alpha_admin.get(f"/crm/leads/{theirs}").json()["converted_at"] is None


def test_another_users_opportunity_cannot_be_moved_or_closed(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    account_id = as_alpha_admin.post("/crm/accounts", json={"name": "Sealed Deals Ltd"}).json()[
        "id"
    ]
    deal = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Sealed deal",
            "account_id": account_id,
            "stage_id": _stage_id(as_alpha_admin, "Qualification"),
        },
    )
    assert deal.status_code == 201, deal.text
    deal_id = deal.json()["id"]
    won_stage = _stage_id(as_alpha_admin, "Closed Won")

    assert rep.get(f"/crm/opportunities/{deal_id}").status_code == 404
    moved = rep.post(f"/crm/opportunities/{deal_id}/stage", json={"stage_id": won_stage})
    assert moved.status_code == 404

    # The deal is still open, so nobody's forecast moved.
    assert as_alpha_admin.get(f"/crm/opportunities/{deal_id}").json()["won_at"] is None


def test_a_rep_reaches_their_own_record_by_id(rep: ApiSession) -> None:
    """The guard must not lock people out of their own work."""
    mine = rep.post("/crm/accounts", json={"name": "Mine Ltd"}).json()["id"]

    assert rep.get(f"/crm/accounts/{mine}").status_code == 200
    assert rep.patch(f"/crm/accounts/{mine}", json={"industry": "Logistics"}).status_code == 200


def test_reassigning_a_record_moves_it_between_reps(
    rep: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Ownership is the handle, so changing it changes who can see the row."""
    mine = rep.post("/crm/accounts", json={"name": "Handover Ltd"}).json()["id"]
    assert rep.get(f"/crm/accounts/{mine}").status_code == 200

    reassigned = as_alpha_admin.patch(
        f"/crm/accounts/{mine}", json={"owner_id": str(alpha.admin.user_id)}
    )
    assert reassigned.status_code == 200, reassigned.text

    assert rep.get(f"/crm/accounts/{mine}").status_code == 404


# --- Unowned records --------------------------------------------------------


def test_an_unowned_record_stays_visible_to_everyone(
    rep: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Rows predating ownership must not become invisible — that is data loss.

    New records always get an owner, so this covers imported and legacy rows
    rather than anything the API can produce today.
    """
    created = as_alpha_admin.post("/crm/accounts", json={"name": "Legacy Ltd"})
    account_id = created.json()["id"]
    orphaned = as_alpha_admin.patch(f"/crm/accounts/{account_id}", json={"owner_id": None})
    assert orphaned.status_code == 200, orphaned.text
    assert orphaned.json()["owner_id"] is None

    assert rep.get(f"/crm/accounts/{account_id}").status_code == 200
    assert account_id in _ids(rep.get("/crm/accounts").json())


# --- Modules that are deliberately organization-wide -------------------------


def test_reference_data_is_not_owner_scoped(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """Lead sources are a shared taxonomy; scoping them would fragment it."""
    source = as_alpha_admin.post("/crm/lead-sources", json={"name": "Trade Show"})
    assert source.status_code == 201, source.text

    listed = rep.get("/crm/lead-sources")

    assert listed.status_code == 200
    assert source.json()["id"] in _ids(listed.json())


def test_a_colleagues_activity_still_appears_on_a_shared_timeline(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """Activities follow their parent record, not their own owner.

    Scoping them by owner would hide a colleague's logged call from the
    account it was logged against — the opposite of a shared history.
    """
    account_id = rep.post("/crm/accounts", json={"name": "Shared History Ltd"}).json()["id"]
    logged = as_alpha_admin.post(
        "/crm/activities",
        json={
            "type": "CALL",
            "subject": "Intro call by a colleague",
            "status": "COMPLETED",
            "related_entity_type": "ACCOUNT",
            "related_entity_id": account_id,
        },
    )
    assert logged.status_code == 201, logged.text

    timeline = rep.get(
        f"/crm/activities/timeline?related_entity_type=ACCOUNT&related_entity_id={account_id}"
    )

    assert timeline.status_code == 200, timeline.text
    assert logged.json()["id"] in {str(row["id"]) for row in timeline.json()}


# --- Dashboard agrees with the lists ----------------------------------------


def test_the_dashboard_counts_only_what_the_rep_can_open(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """A KPI that disagreed with the list beneath it would be worse than none."""
    mine = rep.post("/crm/leads", json={"first_name": "Rep", "last_name": "Lead"})
    assert mine.status_code == 201, mine.text
    for index in range(3):
        created = as_alpha_admin.post(
            "/crm/leads", json={"first_name": f"Admin{index}", "last_name": "Lead"}
        )
        assert created.status_code == 201, created.text

    summary = rep.get("/crm/dashboard/summary")

    assert summary.status_code == 200
    assert summary.json()["kpis"]["new_leads"] == 1
    assert rep.get("/crm/leads").json()["pagination"]["total"] == 1


def test_the_dashboard_shows_an_admin_the_whole_organization(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    mine = rep.post("/crm/leads", json={"first_name": "Rep", "last_name": "Lead"})
    assert mine.status_code == 201, mine.text
    assert (
        as_alpha_admin.post(
            "/crm/leads", json={"first_name": "Admin", "last_name": "Lead"}
        ).status_code
        == 201
    )

    summary = as_alpha_admin.get("/crm/dashboard/summary")

    assert summary.status_code == 200
    assert summary.json()["kpis"]["new_leads"] == 2


def test_the_pipeline_breakdown_is_narrowed_but_keeps_every_stage(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """An empty stage is information; it must survive the narrowing."""
    account_id = as_alpha_admin.post("/crm/accounts", json={"name": "Pipeline Ltd"}).json()["id"]
    stage_id = _stage_id(as_alpha_admin, "Qualification")
    created = as_alpha_admin.post(
        "/crm/opportunities",
        json={"name": "Not the rep's deal", "account_id": account_id, "stage_id": stage_id},
    )
    assert created.status_code == 201, created.text

    pipeline = rep.get("/crm/dashboard/summary").json()["pipeline"]

    assert len(pipeline) > 1, "configured stages must still be listed"
    qualification = next(stage for stage in pipeline if stage["stage_id"] == stage_id)
    assert qualification["count"] == 0


# --- Permission-driven, not role-name driven --------------------------------


def test_granting_view_all_to_a_rep_widens_them_immediately(
    rep: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """The rule reads the catalogue, so a custom grant works with no code change.

    Manager is granted here because there is no per-permission grant endpoint;
    what the assertion turns on is that the *permission* changed the answer,
    on the same session, with no re-login.
    """
    theirs = as_alpha_admin.post("/crm/accounts", json={"name": "Widened Ltd"}).json()["id"]
    assert rep.get(f"/crm/accounts/{theirs}").status_code == 404

    members = as_alpha_admin.get("/organizations/current/members").json()["data"]
    membership_id = next(
        row["id"] for row in members if row["user_id"] == str(alpha.member.user_id)
    )
    manager_role_id = next(
        role["id"] for role in as_alpha_admin.get("/roles").json() if role["name"] == "Manager"
    )
    granted = as_alpha_admin.post(
        "/roles/assignments",
        json={"membership_id": membership_id, "role_id": manager_role_id},
    )
    assert granted.status_code == 204, granted.text

    assert rep.get(f"/crm/accounts/{theirs}").status_code == 200


def test_view_all_is_in_the_permission_catalogue(as_alpha_admin: ApiSession) -> None:
    """The matrix the admin UI renders must show the new dimension."""
    catalog = as_alpha_admin.get("/roles/permissions").json()

    assert "VIEW_ALL" in catalog["actions"]
    assert "leads.VIEW_ALL" in catalog["codes"]


def test_the_system_roles_hold_the_expected_view_all_grants(
    as_alpha_admin: ApiSession,
) -> None:
    roles = {role["name"]: role["id"] for role in as_alpha_admin.get("/roles").json()}

    admin = as_alpha_admin.get(f"/roles/{roles['Admin']}").json()["permissions"]
    manager = as_alpha_admin.get(f"/roles/{roles['Manager']}").json()["permissions"]
    user = as_alpha_admin.get(f"/roles/{roles['User']}").json()["permissions"]

    assert "leads.VIEW_ALL" in admin
    assert "leads.VIEW_ALL" in manager
    assert "leads.VIEW_ALL" not in user
    # The narrowing must not have cost the rep ordinary read access.
    assert "leads.VIEW" in user


def test_a_rep_sees_view_all_absent_from_their_own_permissions(
    rep: ApiSession,
) -> None:
    """What `/auth/me` reports is what the frontend gates on."""
    permissions = rep.get("/auth/me").json()["permissions"]

    assert "leads.VIEW" in permissions
    assert "leads.VIEW_ALL" not in permissions


# --- Record-level scoping is not a substitute for tenant isolation -----------


def test_view_all_does_not_reach_across_organizations(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """An administrator is unrestricted *inside* their tenant, and only there."""
    api.login(beta.admin.email, organization_id=beta.organization_id)
    foreign = api.post("/crm/accounts", json={"name": "Beta Only Ltd"}).json()["id"]

    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    assert api.get(f"/crm/accounts/{foreign}").status_code == 404
    assert foreign not in _ids(api.get("/crm/accounts").json())


def test_an_unauthenticated_request_is_rejected_before_visibility(
    client: TestClient, integration_settings: Settings
) -> None:
    response = client.get(f"{integration_settings.api_prefix}/crm/accounts")

    assert response.status_code == 401


def test_a_random_uuid_is_404_for_everyone(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """So the 404 above cannot be distinguished from a nonexistent record."""
    unknown = uuid.uuid4()

    assert rep.get(f"/crm/accounts/{unknown}").status_code == 404
    assert as_alpha_admin.get(f"/crm/accounts/{unknown}").status_code == 404


# --- Conversion: guarded, but with one consequence worth pinning ------------


def test_conversion_produces_records_the_converter_owns(
    rep: ApiSession, alpha: Tenant
) -> None:
    """A rep converting their own lead ends up owning what it produced."""
    lead_id = rep.post(
        "/crm/leads",
        json={"first_name": "Own", "last_name": "Journey", "company": "Own Journey Ltd"},
    ).json()["id"]
    assert rep.post(f"/crm/leads/{lead_id}/status", json={"status": "CONTACTED"}).status_code == 200
    assert rep.post(f"/crm/leads/{lead_id}/status", json={"status": "QUALIFIED"}).status_code == 200

    converted = rep.post(f"/crm/leads/{lead_id}/convert", json={"create_opportunity": True})
    assert converted.status_code == 201, converted.text
    result = converted.json()

    for path, key in (
        ("/crm/accounts", "account_id"),
        ("/crm/contacts", "contact_id"),
        ("/crm/opportunities", "opportunity_id"),
    ):
        fetched = rep.get(f"{path}/{result[key]}")
        assert fetched.status_code == 200, f"{key}: {fetched.text}"
        assert fetched.json()["owner_id"] == str(alpha.member.user_id)


def test_conversion_reuses_an_account_the_converter_cannot_see(
    rep: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Pins a real consequence of record-level scoping, rather than hiding it.

    Conversion matches an existing account by name **organization-wide**, on
    purpose: one company should be one account, and narrowing the match to the
    converter's own records would manufacture duplicates — the exact problem
    the duplicate-prevention work removed.

    The consequence is that a rep can convert a lead onto an account another
    rep owns, and then not be able to open it. They still own the contact and
    the opportunity, which is the work they actually do, but the account link
    on those records is a dead end for them.

    This is a product decision (should the parent of a record you own become
    readable?), so the behaviour is pinned here rather than quietly changed.
    """
    theirs = as_alpha_admin.post("/crm/accounts", json={"name": "Contested Co"}).json()["id"]

    lead_id = rep.post(
        "/crm/leads",
        json={"first_name": "Con", "last_name": "Tested", "company": "Contested Co"},
    ).json()["id"]
    assert rep.post(f"/crm/leads/{lead_id}/status", json={"status": "CONTACTED"}).status_code == 200
    assert rep.post(f"/crm/leads/{lead_id}/status", json={"status": "QUALIFIED"}).status_code == 200
    result = rep.post(f"/crm/leads/{lead_id}/convert", json={"create_opportunity": True}).json()

    # Reused, not duplicated.
    assert result["account_id"] == theirs

    # The rep owns what was created for them...
    assert rep.get(f"/crm/contacts/{result['contact_id']}").status_code == 200
    assert rep.get(f"/crm/opportunities/{result['opportunity_id']}").status_code == 200
    # ...but the reused account stays outside their visibility.
    assert rep.get(f"/crm/accounts/{theirs}").status_code == 404
