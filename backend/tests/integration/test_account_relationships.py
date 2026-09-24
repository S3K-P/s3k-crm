"""Account 360 (Checkpoint 2): the overview, the timeline, and the
relationships they aggregate — contacts, deals and the primary contact.

Every assertion goes through HTTP against real PostgreSQL, for the same
reason ``test_record_visibility.py`` does: a service-level test would prove
the query compiles, not that the route enforces tenant isolation and
record-level visibility for a real caller.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """A second signed-in session for the plain ``User`` of alpha.

    Mirrors the fixture in ``test_record_visibility.py`` — these tests need
    two people signed in on the same organization at once.
    """
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


def _stage_id(session: ApiSession, name: str) -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


def _account(session: ApiSession, name: str = "Zephyr Systems") -> str:
    created = session.post("/crm/accounts", json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _contact(session: ApiSession, account_id: str, first: str, last: str) -> str:
    created = session.post(
        "/crm/contacts",
        json={"first_name": first, "last_name": last, "account_id": account_id},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _deal(session: ApiSession, account_id: str, name: str, **overrides: object) -> str:
    body: dict[str, object] = {
        "name": name,
        "account_id": account_id,
        # Required by the schema; overridable per-call for tests that need a
        # specific stage (e.g. the ``won`` and ``open_stage`` cases below).
        "stage_id": _stage_id(session, "Qualification"),
    }
    body.update(overrides)
    created = session.post("/crm/opportunities", json=body)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


# --- Overview: real aggregates -----------------------------------------------


def test_overview_reflects_real_contacts_and_deals(as_alpha_admin: ApiSession) -> None:
    account_id = _account(as_alpha_admin)
    _contact(as_alpha_admin, account_id, "Priya", "Shah")
    _contact(as_alpha_admin, account_id, "Rahul", "Sharma")
    _deal(as_alpha_admin, account_id, "Platform rollout", deal_value="150000", currency="INR")
    _deal(as_alpha_admin, account_id, "Small add-on", deal_value="20000", currency="INR")

    overview = as_alpha_admin.get(f"/crm/accounts/{account_id}/overview")

    assert overview.status_code == 200
    body = overview.json()
    assert body["contacts_count"] == 2
    assert body["open_deals_count"] == 2
    assert Decimal(body["open_pipeline_value"]) == Decimal("170000.00")
    assert body["open_pipeline_currency"] == "INR"
    assert body["won_deals_count"] == 0
    assert Decimal(body["won_revenue"]) == Decimal(0)


def test_won_revenue_counts_only_closed_won_deals(as_alpha_admin: ApiSession) -> None:
    account_id = _account(as_alpha_admin)
    deal_id = _deal(as_alpha_admin, account_id, "Won deal", deal_value="50000", currency="INR")
    won_stage = _stage_id(as_alpha_admin, "Closed Won")

    moved = as_alpha_admin.post(f"/crm/opportunities/{deal_id}/stage", json={"stage_id": won_stage})
    assert moved.status_code == 200, moved.text

    overview = as_alpha_admin.get(f"/crm/accounts/{account_id}/overview")

    body = overview.json()
    assert body["won_deals_count"] == 1
    assert Decimal(body["won_revenue"]) == Decimal("50000.00")
    assert body["won_revenue_currency"] == "INR"
    # A won deal is no longer open pipeline.
    assert body["open_deals_count"] == 0


def test_overview_resolves_owner_and_primary_contact_by_name(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    account_id = _account(as_alpha_admin)
    contact_id = _contact(as_alpha_admin, account_id, "Priya", "Shah")

    promoted = as_alpha_admin.post(f"/crm/contacts/{contact_id}/primary")
    assert promoted.status_code == 200, promoted.text

    overview = as_alpha_admin.get(f"/crm/accounts/{account_id}/overview").json()

    assert overview["primary_contact_name"] == "Priya Shah"
    # The account was created by the admin, who is therefore its owner.
    assert overview["owner_name"] not in (None, "")


def test_an_account_with_nothing_on_it_reports_zeros_not_errors(
    as_alpha_admin: ApiSession,
) -> None:
    account_id = _account(as_alpha_admin, "Empty Shell Ltd")

    overview = as_alpha_admin.get(f"/crm/accounts/{account_id}/overview")

    assert overview.status_code == 200
    body = overview.json()
    assert body["contacts_count"] == 0
    assert body["open_deals_count"] == 0
    assert Decimal(body["open_pipeline_value"]) == Decimal(0)
    assert body["open_pipeline_currency"] is None
    assert body["won_deals_count"] == 0
    assert Decimal(body["won_revenue"]) == Decimal(0)
    assert body["won_revenue_currency"] is None
    assert body["open_tasks_count"] == 0
    assert body["last_activity_at"] is None
    assert body["next_meeting_id"] is None
    assert body["primary_contact_name"] is None
    assert body["primary_contact_title"] is None
    # The account was created by the admin, who is therefore its owner.
    assert body["owner_name"] not in (None, "")


# --- Primary contact ----------------------------------------------------------


def test_promoting_a_contact_demotes_the_incumbent(as_alpha_admin: ApiSession) -> None:
    account_id = _account(as_alpha_admin)
    first = _contact(as_alpha_admin, account_id, "Priya", "Shah")
    second = _contact(as_alpha_admin, account_id, "Rahul", "Sharma")

    as_alpha_admin.post(f"/crm/contacts/{first}/primary")
    assert as_alpha_admin.get(f"/crm/accounts/{account_id}").json()["primary_contact_id"] == first

    promoted = as_alpha_admin.post(f"/crm/contacts/{second}/primary")
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["id"] == second

    account = as_alpha_admin.get(f"/crm/accounts/{account_id}").json()
    assert account["primary_contact_id"] == second


def test_a_contact_with_no_account_cannot_be_made_primary(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post(
        "/crm/contacts", json={"first_name": "Orphan", "last_name": "Contact"}
    )
    contact_id = created.json()["id"]

    response = as_alpha_admin.post(f"/crm/contacts/{contact_id}/primary")

    assert response.status_code == 404


# --- Timeline ------------------------------------------------------------------


def test_timeline_merges_deal_creation_stage_changes_and_contact_creation(
    as_alpha_admin: ApiSession,
) -> None:
    account_id = _account(as_alpha_admin)
    _contact(as_alpha_admin, account_id, "Priya", "Shah")
    deal_id = _deal(as_alpha_admin, account_id, "Platform rollout")
    won_stage = _stage_id(as_alpha_admin, "Closed Won")
    as_alpha_admin.post(f"/crm/opportunities/{deal_id}/stage", json={"stage_id": won_stage})

    timeline = as_alpha_admin.get(f"/crm/accounts/{account_id}/timeline")

    assert timeline.status_code == 200
    kinds = [entry["kind"] for entry in timeline.json()]
    assert "contact_created" in kinds
    assert "deal_created" in kinds
    assert "stage_changed" in kinds

    # Newest first.
    timestamps = [entry["occurred_at"] for entry in timeline.json()]
    assert timestamps == sorted(timestamps, reverse=True)


def test_timeline_includes_notes_without_echoing_their_content(
    as_alpha_admin: ApiSession,
) -> None:
    """Notes join the unified timeline as of Checkpoint 3, filtered by the
    notes module's own visibility predicate rather than a copy of it (see
    ``test_record_timelines.py`` for the visibility-scoping tests). What
    reaches this shared view is deliberately a bare "Note added" — never the
    content itself, which stays behind the Notes tab's own read."""
    account_id = _account(as_alpha_admin)
    note = as_alpha_admin.post(
        "/crm/notes",
        json={
            "content": "Confidential pricing discussion",
            "related_entity_type": "ACCOUNT",
            "related_entity_id": account_id,
        },
    )
    assert note.status_code == 201, note.text

    timeline = as_alpha_admin.get(f"/crm/accounts/{account_id}/timeline").json()

    assert any(entry["kind"] == "note_added" for entry in timeline)
    assert not any("pricing" in str(entry).lower() for entry in timeline)


def test_timeline_respects_the_limit(as_alpha_admin: ApiSession) -> None:
    account_id = _account(as_alpha_admin)
    for index in range(5):
        _deal(as_alpha_admin, account_id, f"Deal {index}")

    timeline = as_alpha_admin.get(f"/crm/accounts/{account_id}/timeline?limit=3")

    assert timeline.status_code == 200
    assert len(timeline.json()) == 3


# --- Record-level visibility: an overview must not out-count the caller's own lists ---


def test_overview_counts_only_what_the_rep_can_see(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """A KPI that disagreed with the list beneath it would be worse than none
    (the same property ``test_the_dashboard_counts_only_what_the_rep_can_open``
    checks for the org-wide dashboard, here for one account)."""
    account_id = _account(rep, "Shared Account Ltd")  # the rep creates it, so the rep owns it
    _contact(rep, account_id, "Reps", "OwnContact")

    # The admin (accounts.VIEW_ALL) can still see and act on the rep's account,
    # and attaches a contact and a deal the *admin* owns.
    _contact(as_alpha_admin, account_id, "Admins", "OwnContact")
    _deal(as_alpha_admin, account_id, "Admin's deal")

    rep_view = rep.get(f"/crm/accounts/{account_id}/overview")
    admin_view = as_alpha_admin.get(f"/crm/accounts/{account_id}/overview")

    assert rep_view.status_code == 200
    assert rep_view.json()["contacts_count"] == 1
    assert rep_view.json()["open_deals_count"] == 0

    assert admin_view.status_code == 200
    assert admin_view.json()["contacts_count"] == 2
    assert admin_view.json()["open_deals_count"] == 1


def test_timeline_hides_a_deal_the_rep_does_not_own(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    account_id = _account(rep, "Another Shared Account")
    _deal(as_alpha_admin, account_id, "Admin only deal")

    rep_timeline = rep.get(f"/crm/accounts/{account_id}/timeline").json()
    admin_timeline = as_alpha_admin.get(f"/crm/accounts/{account_id}/timeline").json()

    assert not any(entry["kind"] == "deal_created" for entry in rep_timeline)
    assert any(entry["kind"] == "deal_created" for entry in admin_timeline)


# --- Tenant isolation ----------------------------------------------------------


def test_another_organizations_account_overview_and_timeline_are_404(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """``ApiSession`` is one mutable, shared identity — the last ``login()``
    wins — so alpha's account is seeded and then beta logs in on the *same*
    object before the cross-tenant request, exactly as
    ``test_cross_tenant_matrix.py`` does for the modules it covers.
    """
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    account_id = _account(api)
    assert api.get(f"/crm/accounts/{account_id}/overview").status_code == 200

    api.login(beta.admin.email, organization_id=beta.organization_id)

    assert api.get(f"/crm/accounts/{account_id}/overview").status_code == 404
    assert api.get(f"/crm/accounts/{account_id}/timeline").status_code == 404


def test_a_random_account_id_is_404_not_500(as_alpha_admin: ApiSession) -> None:
    random_id = uuid.uuid4()

    overview = as_alpha_admin.get(f"/crm/accounts/{random_id}/overview")
    timeline = as_alpha_admin.get(f"/crm/accounts/{random_id}/timeline")

    assert overview.status_code == 404
    assert timeline.status_code == 404
