"""CRM CRUD, lead conversion and the opportunity lifecycle.

Covers the business rules that are not generic CRUD: the lead state machine,
conversion, and stage movement with win/loss handling.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


def _stage_id(session: ApiSession, name: str) -> uuid.UUID:
    stages = session.get("/crm/opportunities/stages").json()
    return uuid.UUID(next(stage["id"] for stage in stages if stage["name"] == name))


def _qualified_lead(session: ApiSession, **overrides: object) -> uuid.UUID:
    """Create a lead and walk it to QUALIFIED, the first convertible status."""
    payload: dict[str, object] = {
        "first_name": "Grace",
        "last_name": "Hopper",
        "company": "Hopper Systems",
        "email": "grace@hoppersystems.example",
    }
    payload.update(overrides)
    response = session.post("/crm/leads", json=payload)
    assert response.status_code == 201, response.text
    lead_id = response.json()["id"]

    for status in ("CONTACTED", "QUALIFIED"):
        moved = session.post(f"/crm/leads/{lead_id}/status", json={"status": status})
        assert moved.status_code == 200, moved.text
    return uuid.UUID(lead_id)


# --- CRUD and validation ----------------------------------------------------


def test_account_crud_round_trip(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post("/crm/accounts", json={"name": "Round Trip Ltd"})
    assert created.status_code == 201
    account_id = created.json()["id"]

    assert as_alpha_admin.get(f"/crm/accounts/{account_id}").json()["name"] == "Round Trip Ltd"

    patched = as_alpha_admin.patch(
        f"/crm/accounts/{account_id}", json={"status": "AT_RISK", "health_score": 42}
    )
    assert patched.json()["status"] == "AT_RISK"
    assert patched.json()["health_score"] == 42

    assert as_alpha_admin.delete(f"/crm/accounts/{account_id}").status_code == 204
    # Soft-deleted records disappear from reads.
    assert as_alpha_admin.get(f"/crm/accounts/{account_id}").status_code == 404


def test_creating_an_account_without_a_name_is_rejected(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.post("/crm/accounts", json={"industry": "Retail"})

    assert response.status_code == 422


def test_an_out_of_range_health_score_is_rejected(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/crm/accounts", json={"name": "Bad Score Ltd", "health_score": 900}
    )

    assert response.status_code == 422


def test_a_duplicate_account_name_is_flagged_but_can_be_overridden(
    as_alpha_admin: ApiSession,
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Acme Ltd"})

    blocked = as_alpha_admin.post("/crm/accounts", json={"name": "Acme Ltd"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "duplicate_account"

    allowed = as_alpha_admin.post(
        "/crm/accounts?allow_duplicate=true", json={"name": "Acme Ltd"}
    )
    assert allowed.status_code == 201


def test_the_organization_id_in_a_request_body_is_ignored(
    as_alpha_admin: ApiSession, beta: Tenant
) -> None:
    """Tenancy comes from the principal; a body cannot override it."""
    response = as_alpha_admin.post(
        "/crm/accounts",
        json={"name": "Smuggled Ltd", "organization_id": str(beta.organization_id)},
    )

    assert response.status_code == 201
    assert response.json()["organization_id"] != str(beta.organization_id)


def test_pagination_and_sorting(as_alpha_admin: ApiSession) -> None:
    for index in range(5):
        as_alpha_admin.post("/crm/accounts", json={"name": f"Company {index}"})

    page = as_alpha_admin.get("/crm/accounts?page=1&page_size=2&sort_by=name&sort_dir=asc")
    body = page.json()

    assert body["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total": 5,
        "total_pages": 3,
        "has_more": True,
    }
    assert [row["name"] for row in body["data"]] == ["Company 0", "Company 1"]


def test_an_unknown_sort_column_is_ignored_rather_than_injected(
    as_alpha_admin: ApiSession,
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Sortable Ltd"})

    response = as_alpha_admin.get("/crm/accounts?sort_by=name;DROP+TABLE+crm.accounts")

    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 1


def test_filtering_by_status(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Healthy Ltd"})
    as_alpha_admin.post(
        "/crm/accounts", json={"name": "Wobbly Ltd", "status": "AT_RISK"}
    )

    body = as_alpha_admin.get("/crm/accounts?status=AT_RISK").json()

    assert [row["name"] for row in body["data"]] == ["Wobbly Ltd"]


# --- Lead lifecycle ---------------------------------------------------------


def test_a_new_lead_starts_at_new(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Alan", "last_name": "Turing"}
    )

    assert response.json()["status"] == "NEW"


def test_a_legal_status_transition_is_accepted(as_alpha_admin: ApiSession) -> None:
    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Alan", "last_name": "Turing"}
    ).json()["id"]

    response = as_alpha_admin.post(
        f"/crm/leads/{lead_id}/status", json={"status": "CONTACTED"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CONTACTED"


def test_skipping_a_stage_is_rejected(as_alpha_admin: ApiSession) -> None:
    """NEW -> NEGOTIATION is not a legal move."""
    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Alan", "last_name": "Turing"}
    ).json()["id"]

    response = as_alpha_admin.post(
        f"/crm/leads/{lead_id}/status", json={"status": "NEGOTIATION"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_lead_transition"


def test_a_lead_cannot_be_marked_converted_directly(
    as_alpha_admin: ApiSession,
) -> None:
    """CONVERTED is reachable only through the conversion workflow."""
    lead_id = _qualified_lead(as_alpha_admin)

    response = as_alpha_admin.post(
        f"/crm/leads/{lead_id}/status", json={"status": "CONVERTED"}
    )

    assert response.status_code == 422


def test_status_counts_reflect_the_board(as_alpha_admin: ApiSession) -> None:
    _qualified_lead(as_alpha_admin)
    as_alpha_admin.post("/crm/leads", json={"first_name": "New", "last_name": "Lead"})

    counts = as_alpha_admin.get("/crm/leads/status-counts").json()["counts"]

    assert counts["QUALIFIED"] == 1
    assert counts["NEW"] == 1


# --- Lead conversion --------------------------------------------------------


def test_converting_a_lead_creates_an_account_and_contact(
    as_alpha_admin: ApiSession,
) -> None:
    lead_id = _qualified_lead(as_alpha_admin)

    response = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert response.status_code == 201
    body = response.json()
    assert body["account_id"] and body["contact_id"]
    assert body["opportunity_id"] is None

    account = as_alpha_admin.get(f"/crm/accounts/{body['account_id']}").json()
    assert account["name"] == "Hopper Systems"


def test_conversion_marks_the_lead_converted_and_links_the_records(
    as_alpha_admin: ApiSession,
) -> None:
    lead_id = _qualified_lead(as_alpha_admin)

    body = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={}).json()
    lead = as_alpha_admin.get(f"/crm/leads/{lead_id}").json()

    assert lead["status"] == "CONVERTED"
    assert lead["converted_at"] is not None
    assert lead["converted_account_id"] == body["account_id"]
    assert lead["converted_contact_id"] == body["contact_id"]


def test_conversion_can_create_an_opportunity(as_alpha_admin: ApiSession) -> None:
    lead_id = _qualified_lead(as_alpha_admin)

    body = as_alpha_admin.post(
        f"/crm/leads/{lead_id}/convert",
        json={"create_opportunity": True, "opportunity_name": "Hopper — Phase 1"},
    ).json()

    assert body["opportunity_id"] is not None
    opportunity = as_alpha_admin.get(
        f"/crm/opportunities/{body['opportunity_id']}"
    ).json()
    assert opportunity["name"] == "Hopper — Phase 1"
    assert opportunity["account_id"] == body["account_id"]


def test_converting_into_an_existing_account_reuses_it(
    as_alpha_admin: ApiSession,
) -> None:
    existing = as_alpha_admin.post("/crm/accounts", json={"name": "Existing Ltd"}).json()
    lead_id = _qualified_lead(as_alpha_admin)

    body = as_alpha_admin.post(
        f"/crm/leads/{lead_id}/convert", json={"account_id": existing["id"]}
    ).json()

    assert body["account_id"] == existing["id"]


def test_an_unqualified_lead_cannot_be_converted(as_alpha_admin: ApiSession) -> None:
    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Too", "last_name": "Early"}
    ).json()["id"]

    response = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "lead_not_convertible"


def test_a_lead_cannot_be_converted_twice(as_alpha_admin: ApiSession) -> None:
    lead_id = _qualified_lead(as_alpha_admin)
    as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    response = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "lead_already_converted"


def test_conversion_cannot_attach_to_another_organizations_account(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(beta.admin.email, organization_id=beta.organization_id)
    foreign = api.post("/crm/accounts", json={"name": "Beta Only Ltd"}).json()

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    lead_id = _qualified_lead(api)

    response = api.post(
        f"/crm/leads/{lead_id}/convert", json={"account_id": foreign["id"]}
    )

    assert response.status_code == 404


# --- Opportunity lifecycle --------------------------------------------------


@pytest.fixture
def opportunity_id(as_alpha_admin: ApiSession) -> uuid.UUID:
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Deal Co"}).json()
    response = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Deal Co — Platform",
            "account_id": account["id"],
            "stage_id": str(_stage_id(as_alpha_admin, "Qualification")),
            "deal_value": "50000.00",
        },
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def test_a_stage_change_updates_probability_and_records_history(
    as_alpha_admin: ApiSession, opportunity_id: uuid.UUID
) -> None:
    proposal = _stage_id(as_alpha_admin, "Proposal")

    response = as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage", json={"stage_id": str(proposal)}
    )

    assert response.status_code == 200
    assert response.json()["win_probability"] == 50

    history = as_alpha_admin.get(f"/crm/opportunities/{opportunity_id}/history").json()
    assert history[0]["to_stage_id"] == str(proposal)


def test_winning_a_deal_closes_it(
    as_alpha_admin: ApiSession, opportunity_id: uuid.UUID
) -> None:
    won = _stage_id(as_alpha_admin, "Closed Won")

    response = as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage",
        json={"stage_id": str(won), "win_reason": "Best fit"},
    )

    assert response.status_code == 200
    assert response.json()["won_at"] is not None
    assert response.json()["win_reason"] == "Best fit"


def test_losing_a_deal_requires_a_reason(
    as_alpha_admin: ApiSession, opportunity_id: uuid.UUID
) -> None:
    lost = _stage_id(as_alpha_admin, "Closed Lost")

    response = as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage", json={"stage_id": str(lost)}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "loss_reason_required"


def test_losing_a_deal_with_a_reason_succeeds(
    as_alpha_admin: ApiSession, opportunity_id: uuid.UUID
) -> None:
    lost = _stage_id(as_alpha_admin, "Closed Lost")

    response = as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage",
        json={"stage_id": str(lost), "loss_reason": "Lost on price"},
    )

    assert response.status_code == 200
    assert response.json()["lost_at"] is not None


def test_a_closed_deal_cannot_be_edited(
    as_alpha_admin: ApiSession, opportunity_id: uuid.UUID
) -> None:
    won = _stage_id(as_alpha_admin, "Closed Won")
    as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage", json={"stage_id": str(won)}
    )

    response = as_alpha_admin.patch(
        f"/crm/opportunities/{opportunity_id}", json={"deal_value": "1.00"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "opportunity_closed"


def test_a_closed_deal_can_be_reopened(
    as_alpha_admin: ApiSession, opportunity_id: uuid.UUID
) -> None:
    won = _stage_id(as_alpha_admin, "Closed Won")
    as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage", json={"stage_id": str(won)}
    )

    response = as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/reopen",
        json={"stage_id": str(_stage_id(as_alpha_admin, "Negotiation"))},
    )

    assert response.status_code == 200
    assert response.json()["won_at"] is None


def test_an_opportunity_cannot_use_another_organizations_stage(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(beta.admin.email, organization_id=beta.organization_id)
    foreign_stage = _stage_id(api, "Proposal")

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    account = api.post("/crm/accounts", json={"name": "Alpha Co"}).json()

    response = api.post(
        "/crm/opportunities",
        json={
            "name": "Cross-tenant stage",
            "account_id": account["id"],
            "stage_id": str(foreign_stage),
        },
    )

    assert response.status_code == 404


def test_an_account_with_open_opportunities_cannot_be_archived(
    as_alpha_admin: ApiSession, opportunity_id: uuid.UUID
) -> None:
    account_id = as_alpha_admin.get(
        f"/crm/opportunities/{opportunity_id}"
    ).json()["account_id"]

    response = as_alpha_admin.delete(f"/crm/accounts/{account_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_has_open_opportunities"
