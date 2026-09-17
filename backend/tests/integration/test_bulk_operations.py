"""Bulk update/delete/status-change over HTTP (Checkpoint 4).

Every operation here processes several ids at once and the tests are written
to prove the one property that makes that safe: a bulk call is many
single-record calls in a trench coat, never a single blanket UPDATE. A record
outside the caller's permission or visibility fails exactly as a lone request
against it would; a record whose move a state machine or blueprint refuses
fails exactly as a lone drag on the Kanban board would; and neither ever takes
the rest of the batch down with it.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def as_alpha_rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


def make_lead(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {"first_name": "Ravi", "last_name": "Kumar"}
    payload.update(overrides)
    response = api.post("/crm/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_account(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {"name": "Zephyr Industries"}
    payload.update(overrides)
    response = api.post("/crm/accounts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def stage_ids(api: ApiSession) -> dict[str, str]:
    stages = api.get("/crm/opportunities/stages").json()
    return {stage["name"]: stage["id"] for stage in stages}


def make_opportunity(api: ApiSession, account_id: str, stage_id: str, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "name": "Big Deal",
        "account_id": account_id,
        "stage_id": stage_id,
    }
    payload.update(overrides)
    response = api.post("/crm/opportunities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Bulk update
# ---------------------------------------------------------------------------


def test_bulk_update_reports_success_and_a_missing_id_separately(
    as_alpha_admin: ApiSession,
) -> None:
    lead1 = make_lead(as_alpha_admin, first_name="Asha")
    lead2 = make_lead(as_alpha_admin, first_name="Bala")
    missing = str(uuid.uuid4())

    response = as_alpha_admin.post(
        "/crm/leads/bulk-update",
        json={"ids": [lead1["id"], lead2["id"], missing], "values": {"industry": "Finance"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert sorted(body["succeeded"]) == sorted([lead1["id"], lead2["id"]])
    assert len(body["failed"]) == 1
    assert body["failed"][0]["id"] == missing

    updated = as_alpha_admin.get(f"/crm/leads/{lead1['id']}").json()
    assert updated["industry"] == "Finance"


def test_bulk_update_cannot_change_a_leads_status(as_alpha_admin: ApiSession) -> None:
    """``LeadBulkUpdate.values`` is ``LeadUpdate``, which has no ``status`` field.

    A client that includes it anyway has the key silently ignored by the
    schema, exactly as a single-record PATCH already does — the status stays
    whatever the dedicated transition endpoint last set it to.
    """
    lead = make_lead(as_alpha_admin)
    response = as_alpha_admin.post(
        "/crm/leads/bulk-update",
        json={"ids": [lead["id"]], "values": {"status": "QUALIFIED", "industry": "Retail"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["succeeded"] == [lead["id"]]

    unchanged = as_alpha_admin.get(f"/crm/leads/{lead['id']}").json()
    assert unchanged["status"] == "NEW"
    assert unchanged["industry"] == "Retail"


def test_bulk_update_opportunities_cannot_edit_a_closed_deal(as_alpha_admin: ApiSession) -> None:
    account = make_account(as_alpha_admin)
    stages = stage_ids(as_alpha_admin)
    open_deal = make_opportunity(as_alpha_admin, account["id"], stages["Qualification"])
    closed_deal = make_opportunity(as_alpha_admin, account["id"], stages["Qualification"])
    won = as_alpha_admin.post(
        f"/crm/opportunities/{closed_deal['id']}/stage", json={"stage_id": stages["Closed Won"]}
    )
    assert won.status_code == 200, won.text

    response = as_alpha_admin.post(
        "/crm/opportunities/bulk-update",
        json={
            "ids": [open_deal["id"], closed_deal["id"]],
            "values": {"notes": "Quarterly review"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] == [open_deal["id"]]
    assert body["failed"][0]["id"] == closed_deal["id"]


def test_a_rep_without_view_all_cannot_bulk_update_a_colleagues_lead(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """Visibility is enforced per record inside the batch, not only the module gate.

    The admin-owned lead is invisible to a rep holding only ``leads.VIEW``
    (owner-scoped, no ``VIEW_ALL``) — it must fail the same way a single
    ``PATCH`` against it would, not be silently skipped or, worse, changed.
    """
    admins_lead = make_lead(as_alpha_admin, first_name="AdminOwned")
    reps_lead = make_lead(as_alpha_rep, first_name="RepOwned")

    response = as_alpha_rep.post(
        "/crm/leads/bulk-update",
        json={"ids": [admins_lead["id"], reps_lead["id"]], "values": {"industry": "Energy"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] == [reps_lead["id"]]
    assert body["failed"][0]["id"] == admins_lead["id"]

    untouched = as_alpha_admin.get(f"/crm/leads/{admins_lead['id']}").json()
    assert untouched["industry"] is None


# ---------------------------------------------------------------------------
# Bulk delete
# ---------------------------------------------------------------------------


def test_bulk_delete_archives_every_record(as_alpha_admin: ApiSession) -> None:
    lead1 = make_lead(as_alpha_admin)
    lead2 = make_lead(as_alpha_admin)

    response = as_alpha_admin.post(
        "/crm/leads/bulk-delete", json={"ids": [lead1["id"], lead2["id"]]}
    )
    assert response.status_code == 200, response.text
    assert sorted(response.json()["succeeded"]) == sorted([lead1["id"], lead2["id"]])

    assert as_alpha_admin.get(f"/crm/leads/{lead1['id']}").status_code == 404
    assert as_alpha_admin.get(f"/crm/leads/{lead2['id']}").status_code == 404


def test_a_rep_without_delete_permission_is_refused(as_alpha_rep: ApiSession) -> None:
    lead = make_lead(as_alpha_rep)
    response = as_alpha_rep.post("/crm/leads/bulk-delete", json={"ids": [lead["id"]]})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Bulk status / stage change
# ---------------------------------------------------------------------------


def test_bulk_status_change_reports_an_illegal_transition_as_a_failure(
    as_alpha_admin: ApiSession,
) -> None:
    contacted = make_lead(as_alpha_admin, first_name="Contacted")
    still_new = make_lead(as_alpha_admin, first_name="StillNew")
    first_move = as_alpha_admin.post(
        f"/crm/leads/{contacted['id']}/status", json={"status": "CONTACTED"}
    )
    assert first_move.status_code == 200, first_move.text

    response = as_alpha_admin.post(
        "/crm/leads/bulk-status",
        json={"ids": [contacted["id"], still_new["id"]], "status": "QUALIFIED"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] == [contacted["id"]]
    assert body["failed"][0]["id"] == still_new["id"]

    unmoved = as_alpha_admin.get(f"/crm/leads/{still_new['id']}").json()
    assert unmoved["status"] == "NEW"


def test_bulk_stage_change_reports_a_closed_deal_as_a_failure(as_alpha_admin: ApiSession) -> None:
    account = make_account(as_alpha_admin)
    stages = stage_ids(as_alpha_admin)
    open_deal = make_opportunity(as_alpha_admin, account["id"], stages["Qualification"])
    closed_deal = make_opportunity(as_alpha_admin, account["id"], stages["Qualification"])
    as_alpha_admin.post(
        f"/crm/opportunities/{closed_deal['id']}/stage", json={"stage_id": stages["Closed Won"]}
    )

    response = as_alpha_admin.post(
        "/crm/opportunities/bulk-stage",
        json={"ids": [open_deal["id"], closed_deal["id"]], "stage_id": stages["Discovery"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["succeeded"] == [open_deal["id"]]
    assert body["failed"][0]["id"] == closed_deal["id"]

    moved = as_alpha_admin.get(f"/crm/opportunities/{open_deal['id']}").json()
    assert moved["stage_id"] == stages["Discovery"]
