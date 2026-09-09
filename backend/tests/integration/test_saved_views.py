"""Saved list views over HTTP: sharing, editing rights, isolation.

The properties that only exist once a database and two people are involved:
that a private view is invisible to a colleague *and indistinguishable from a
missing one*, that "shared" does not quietly mean "communal", that a default is
personal, and that a view grants sight of no record at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def as_alpha_rep(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> ApiSession:
    """A rep's session that does not collide with ``as_alpha_admin``.

    ``as_alpha_admin`` and ``as_alpha_member`` are two logins through the *same*
    ``ApiSession`` object, so a test requesting both gets whichever signed in
    last for both. Any test needing two people at once builds the second here.
    """
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def as_beta_admin(
    client: TestClient, integration_settings: Settings, beta: Tenant
) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(beta.admin.email, organization_id=beta.organization_id)
    return session


def make_view(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "entity_type": "LEAD",
        "name": "My hot leads",
        "filters": {"status": "QUALIFIED"},
        "columns": ["first_name", "last_name", "status"],
        "sort_by": "created_at",
        "sort_dir": "desc",
    }
    payload.update(overrides)
    response = api.post("/crm/views", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# The basics
# ---------------------------------------------------------------------------


def test_a_view_round_trips(as_alpha_admin: ApiSession) -> None:
    view = make_view(as_alpha_admin)
    assert view["filters"] == {"status": "QUALIFIED"}
    assert view["columns"] == ["first_name", "last_name", "status"]
    assert view["visibility"] == "PRIVATE"
    assert view["can_edit"] is True

    listed = as_alpha_admin.get("/crm/views?entity_type=LEAD")
    assert [item["id"] for item in listed.json()] == [view["id"]]


def test_views_are_scoped_to_one_record_type(as_alpha_admin: ApiSession) -> None:
    make_view(as_alpha_admin, entity_type="LEAD", name="Leads")
    make_view(as_alpha_admin, entity_type="ACCOUNT", name="Accounts")

    leads = as_alpha_admin.get("/crm/views?entity_type=LEAD").json()
    assert [item["name"] for item in leads] == ["Leads"]


def test_the_same_name_on_two_record_types_is_allowed(
    as_alpha_admin: ApiSession,
) -> None:
    make_view(as_alpha_admin, entity_type="LEAD", name="Recent")
    make_view(as_alpha_admin, entity_type="ACCOUNT", name="Recent")


def test_a_duplicate_name_on_the_same_record_type_is_a_conflict(
    as_alpha_admin: ApiSession,
) -> None:
    make_view(as_alpha_admin)
    again = as_alpha_admin.post(
        "/crm/views", json={"entity_type": "LEAD", "name": "My hot leads"}
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "duplicate_view_name"


def test_two_people_may_each_have_a_view_of_the_same_name(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """Uniqueness is per person: refusing the second "My hot leads" in an
    organization would be surprising and wrong."""
    make_view(as_alpha_admin)
    make_view(as_alpha_rep)


def test_the_record_type_cannot_be_changed(as_alpha_admin: ApiSession) -> None:
    """Its filters would name columns the new entity has not got."""
    view = make_view(as_alpha_admin)
    patched = as_alpha_admin.patch(
        f"/crm/views/{view['id']}", json={"entity_type": "ACCOUNT"}
    )
    # Silently ignored by the schema rather than refused — but it must not
    # actually move, which is what this asserts.
    assert patched.json()["entity_type"] == "LEAD"


def test_a_nested_filter_document_is_refused(as_alpha_admin: ApiSession) -> None:
    """A filter the list endpoint cannot express is one the view would ignore,
    and a view that quietly drops half its filters shows the wrong records
    under a name that promises the right ones."""
    response = as_alpha_admin.post(
        "/crm/views",
        json={"entity_type": "LEAD", "name": "Nested", "filters": {"a": {"b": 1}}},
    )
    assert response.status_code == 422


def test_a_list_filter_is_accepted(as_alpha_admin: ApiSession) -> None:
    view = make_view(
        as_alpha_admin, name="Multi", filters={"status": ["NEW", "CONTACTED"]}
    )
    assert view["filters"] == {"status": ["NEW", "CONTACTED"]}


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


def test_a_private_view_is_invisible_to_a_colleague(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    view = make_view(as_alpha_admin)

    assert as_alpha_rep.get("/crm/views?entity_type=LEAD").json() == []
    # A 404 rather than a 403: a private view must not become visible through
    # the *error* of asking for it.
    assert as_alpha_rep.get(f"/crm/views/{view['id']}").status_code == 404


def test_an_organization_view_is_visible_to_everyone(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    view = make_view(as_alpha_admin, visibility="ORGANIZATION")

    listed = as_alpha_rep.get("/crm/views?entity_type=LEAD").json()
    assert [item["id"] for item in listed] == [view["id"]]
    assert as_alpha_rep.get(f"/crm/views/{view['id']}").status_code == 200


def test_a_shared_view_is_not_editable_by_everyone(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """The property that stops "shared" quietly meaning "communal"."""
    view = make_view(as_alpha_admin, visibility="ORGANIZATION")

    fetched = as_alpha_rep.get(f"/crm/views/{view['id']}").json()
    assert fetched["can_edit"] is False

    patched = as_alpha_rep.patch(f"/crm/views/{view['id']}", json={"name": "Hijacked"})
    assert patched.status_code == 404
    assert as_alpha_rep.delete(f"/crm/views/{view['id']}").status_code == 404


def test_a_manager_may_edit_a_colleagues_view(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """``views.VIEW_ALL`` is what lets a manager tidy up somebody else's views,
    reusing the existing grant rather than inventing one nobody would think to
    hand out."""
    rep = ApiSession(client, integration_settings.api_prefix)
    rep.login(alpha.member.email, organization_id=alpha.organization_id)
    view = make_view(rep, visibility="ORGANIZATION")

    manager = ApiSession(client, integration_settings.api_prefix)
    manager.login(alpha.manager.email, organization_id=alpha.organization_id)

    fetched = manager.get(f"/crm/views/{view['id']}").json()
    assert fetched["can_edit"] is True
    assert manager.patch(f"/crm/views/{view['id']}", json={"name": "Tidied"}).status_code == 200


def test_a_view_grants_sight_of_no_record(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """A view names filters; running it goes through the record type's own
    endpoint, behind that module's permission and visibility. Two colleagues
    opening one shared view legitimately see different rows."""
    make_view(as_alpha_admin, visibility="ORGANIZATION")

    # The admin's lead, owned by the admin.
    created = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Ravi", "last_name": "Kumar"}
    )
    assert created.status_code == 201

    # The rep can read the view but not the record it would return: a plain
    # User holds `leads.VIEW` without `VIEW_ALL`, so they see only their own.
    assert as_alpha_rep.get("/crm/views?entity_type=LEAD").json() != []
    visible = as_alpha_rep.get("/crm/leads").json()["data"]
    assert [lead["id"] for lead in visible] == []


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_at_most_one_default_per_person_per_record_type(
    as_alpha_admin: ApiSession,
) -> None:
    first = make_view(as_alpha_admin, name="First", is_default=True)
    second = make_view(as_alpha_admin, name="Second", is_default=True)

    listed = as_alpha_admin.get("/crm/views?entity_type=LEAD").json()
    defaults = [item["id"] for item in listed if item["is_default"]]
    assert defaults == [second["id"]]
    assert first["id"] not in defaults


def test_a_default_is_personal(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """One administrator's choice must not become everybody's."""
    admin_view = make_view(as_alpha_admin, name="Admin default", is_default=True)
    rep_view = make_view(as_alpha_rep, name="Rep default", is_default=True)

    admin_listed = as_alpha_admin.get("/crm/views?entity_type=LEAD").json()
    assert [v["id"] for v in admin_listed if v["is_default"]] == [admin_view["id"]]

    rep_listed = as_alpha_rep.get("/crm/views?entity_type=LEAD").json()
    assert [v["id"] for v in rep_listed if v["is_default"]] == [rep_view["id"]]


def test_promoting_a_default_on_one_entity_leaves_another_alone(
    as_alpha_admin: ApiSession,
) -> None:
    leads = make_view(as_alpha_admin, entity_type="LEAD", name="L", is_default=True)
    make_view(as_alpha_admin, entity_type="ACCOUNT", name="A", is_default=True)

    still = as_alpha_admin.get(f"/crm/views/{leads['id']}").json()
    assert still["is_default"] is True


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------


def test_a_view_can_be_deleted_by_its_owner(as_alpha_admin: ApiSession) -> None:
    view = make_view(as_alpha_admin)
    assert as_alpha_admin.delete(f"/crm/views/{view['id']}").status_code == 204
    assert as_alpha_admin.get("/crm/views?entity_type=LEAD").json() == []


def test_deleting_a_view_leaves_the_name_free(as_alpha_admin: ApiSession) -> None:
    """Uniqueness is partial on ``deleted_at IS NULL``: deletion is soft here,
    so an unconditional constraint would burn every name anybody retired."""
    view = make_view(as_alpha_admin)
    as_alpha_admin.delete(f"/crm/views/{view['id']}")
    make_view(as_alpha_admin)


def test_deleting_a_view_touches_no_record(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Ravi", "last_name": "Kumar"}
    ).json()
    view = make_view(as_alpha_admin)

    as_alpha_admin.delete(f"/crm/views/{view['id']}")
    assert as_alpha_admin.get(f"/crm/leads/{created['id']}").status_code == 200


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_one_tenants_views_are_invisible_to_another(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    make_view(as_alpha_admin, visibility="ORGANIZATION")
    assert as_beta_admin.get("/crm/views?entity_type=LEAD").json() == []


def test_another_tenants_view_cannot_be_read_or_changed(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    view = make_view(as_alpha_admin, visibility="ORGANIZATION")

    assert as_beta_admin.get(f"/crm/views/{view['id']}").status_code == 404
    assert (
        as_beta_admin.patch(f"/crm/views/{view['id']}", json={"name": "X"}).status_code == 404
    )
    assert as_beta_admin.delete(f"/crm/views/{view['id']}").status_code == 404


def test_two_tenants_may_use_the_same_view_name(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    make_view(as_alpha_admin)
    make_view(as_beta_admin)
