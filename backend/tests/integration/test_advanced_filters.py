"""The ``?advanced_filter=`` query parameter on list endpoints (Checkpoint 5).

Additive on top of every existing list endpoint: the same
``reports.conditions.ReportFilterGroup`` document the custom-report builder
uses, resolved through the identical
``reports.custom.build_advanced_filter_predicate`` and ANDed onto whatever the
named query parameters (``?status=``, ``?owner_id=``, ``cf_*``) already
narrowed. Existing filter behaviour is not touched by any of this — proven
here only incidentally, by every list still working with the parameter
omitted — because that is the entire point of "additive".
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def other_rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.manager.email, organization_id=alpha.organization_id)
    return session


def _list_leads(session: ApiSession, group_filter: dict) -> list[dict]:
    response = session.get("/crm/leads", params={"advanced_filter": json.dumps(group_filter)})
    assert response.status_code == 200, response.text
    body: list[dict] = response.json()["data"]
    return body


def test_and_combination_narrows_a_list(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Match", "last_name": "Both", "company": "Acme"}
    )
    as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Match", "last_name": "OnlyOne", "company": "Zylo"}
    )

    rows = _list_leads(
        as_alpha_admin,
        {
            "logic": "AND",
            "conditions": [
                {"field": "first_name", "operator": "eq", "value": "Match"},
                {"field": "company", "operator": "eq", "value": "Acme"},
            ],
        },
    )

    last_names = {row["last_name"] for row in rows}
    assert "Both" in last_names
    assert "OnlyOne" not in last_names


def test_or_combination_widens_a_list(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/leads", json={"first_name": "OrAlpha", "last_name": "X"})
    as_alpha_admin.post("/crm/leads", json={"first_name": "OrBeta", "last_name": "Y"})
    as_alpha_admin.post("/crm/leads", json={"first_name": "OrGamma", "last_name": "Z"})

    rows = _list_leads(
        as_alpha_admin,
        {
            "logic": "OR",
            "conditions": [
                {"field": "first_name", "operator": "eq", "value": "OrAlpha"},
                {"field": "first_name", "operator": "eq", "value": "OrBeta"},
            ],
        },
    )

    names = {row["first_name"] for row in rows}
    assert names == {"OrAlpha", "OrBeta"}


def test_advanced_filter_combines_with_named_query_params(as_alpha_admin: ApiSession) -> None:
    """Additive, not a replacement — both narrow the same list at once."""
    as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Combo", "last_name": "Keep", "company": "Acme"}
    )
    combo = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Combo", "last_name": "DropByStatus"}
    )
    lead_id = combo.json()["id"]
    as_alpha_admin.post(f"/crm/leads/{lead_id}/status", json={"status": "CONTACTED"})

    response = as_alpha_admin.get(
        "/crm/leads",
        params={
            "status": "NEW",
            "advanced_filter": json.dumps(
                {
                    "logic": "AND",
                    "conditions": [{"field": "first_name", "operator": "eq", "value": "Combo"}],
                }
            ),
        },
    )
    assert response.status_code == 200, response.text
    last_names = {row["last_name"] for row in response.json()["data"]}

    assert "Keep" in last_names
    assert "DropByStatus" not in last_names


def test_malformed_json_is_a_422(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get("/crm/leads", params={"advanced_filter": "{not json"})

    assert response.status_code == 422, response.text


def test_an_unknown_field_is_a_422(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get(
        "/crm/leads",
        params={
            "advanced_filter": json.dumps(
                {
                    "logic": "AND",
                    "conditions": [{"field": "no_such_field", "operator": "eq", "value": "x"}],
                }
            )
        },
    )

    assert response.status_code == 422, response.text


def test_advanced_filter_never_widens_record_visibility(
    rep: ApiSession, other_rep: ApiSession
) -> None:
    """The filter narrows within whatever RecordVisibility already allows —
    it cannot be used to reach a colleague's records."""
    other_rep.post("/crm/leads", json={"first_name": "Hidden", "last_name": "FromRep"})

    rows = _list_leads(
        rep,
        {
            "logic": "AND",
            "conditions": [{"field": "first_name", "operator": "eq", "value": "Hidden"}],
        },
    )

    assert rows == []


def test_advanced_filter_on_opportunities_by_deal_value(as_alpha_admin: ApiSession) -> None:
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Advanced Filter Co"}).json()
    stage_id = next(
        s["id"]
        for s in as_alpha_admin.get("/crm/opportunities/stages").json()
        if s["name"] == "Qualification"
    )
    as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Big Deal",
            "account_id": account["id"],
            "stage_id": stage_id,
            "deal_value": "50000",
        },
    )
    as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Small Deal",
            "account_id": account["id"],
            "stage_id": stage_id,
            "deal_value": "100",
        },
    )

    response = as_alpha_admin.get(
        "/crm/opportunities",
        params={
            "advanced_filter": json.dumps(
                {
                    "logic": "AND",
                    "conditions": [{"field": "deal_value", "operator": "gte", "value": 10000}],
                }
            )
        },
    )
    assert response.status_code == 200, response.text
    names = {row["name"] for row in response.json()["data"]}

    assert "Big Deal" in names
    assert "Small Deal" not in names


# --- Saved views storing an advanced filter -----------------------------------


def test_a_saved_view_can_store_and_validate_an_advanced_filter(
    as_alpha_admin: ApiSession,
) -> None:
    created = as_alpha_admin.post(
        "/crm/views",
        json={
            "entity_type": "LEAD",
            "name": "High-value new leads",
            "advanced_filter": {
                "logic": "AND",
                "conditions": [{"field": "status", "operator": "eq", "value": "NEW"}],
            },
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["advanced_filter"]["conditions"][0]["field"] == "status"


def test_a_saved_view_rejects_an_advanced_filter_on_an_unknown_field(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.post(
        "/crm/views",
        json={
            "entity_type": "LEAD",
            "name": "Bad advanced filter",
            "advanced_filter": {
                "logic": "AND",
                "conditions": [{"field": "not_a_field", "operator": "eq", "value": "x"}],
            },
        },
    )

    assert response.status_code == 422, response.text


def test_updating_a_saved_views_advanced_filter_is_validated_too(
    as_alpha_admin: ApiSession,
) -> None:
    created = as_alpha_admin.post(
        "/crm/views", json={"entity_type": "LEAD", "name": "Editable view"}
    )
    assert created.status_code == 201, created.text
    view_id = created.json()["id"]

    updated = as_alpha_admin.patch(
        f"/crm/views/{view_id}",
        json={
            "advanced_filter": {
                "logic": "AND",
                "conditions": [{"field": "status", "operator": "eq", "value": "NEW"}],
            }
        },
    )
    bad_update = as_alpha_admin.patch(
        f"/crm/views/{view_id}",
        json={
            "advanced_filter": {
                "logic": "AND",
                "conditions": [{"field": "nonexistent", "operator": "eq", "value": "x"}],
            }
        },
    )

    assert updated.status_code == 200, updated.text
    assert bad_update.status_code == 422, bad_update.text
