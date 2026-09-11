"""Record layouts over HTTP: the builder API, publishing, and — the part that
matters most — that a published layout's conditional rule is enforced by the
server on a real write, not merely evaluated by a preview endpoint nobody has
to call.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def as_beta_admin(client: TestClient, integration_settings: Settings, beta: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(beta.admin.email, organization_id=beta.organization_id)
    return session


@pytest.fixture
def as_alpha_rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


def make_custom_field(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "entity_type": "LEAD",
        "api_name": "qualification_details",
        "label": "Qualification Details",
        "field_type": "TEXT",
        "is_required": False,
    }
    payload.update(overrides)
    response = api.post("/crm/custom-fields", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_layout(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {"entity_type": "LEAD", "name": "Lead Layout"}
    payload.update(overrides)
    response = api.post("/crm/layouts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_section(api: ApiSession, layout_id: str, **overrides: object) -> dict:
    payload: dict[str, object] = {"name": "Details", "columns": 1}
    payload.update(overrides)
    response = api.post(f"/crm/layouts/{layout_id}/sections", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def add_field(
    api: ApiSession, layout_id: str, section_id: str, field_key: str, **overrides: object
) -> dict:
    payload: dict[str, object] = {"section_id": section_id, "field_key": field_key}
    payload.update(overrides)
    response = api.post(f"/crm/layouts/{layout_id}/fields", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_lead(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {"first_name": "Ravi", "last_name": "Kumar"}
    payload.update(overrides)
    response = api.post("/crm/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Builder CRUD
# ---------------------------------------------------------------------------


def test_a_layout_can_be_built_with_sections_and_fields(as_alpha_admin: ApiSession) -> None:
    make_custom_field(as_alpha_admin)
    layout = make_layout(as_alpha_admin)
    section = make_section(as_alpha_admin, layout["id"])
    add_field(as_alpha_admin, layout["id"], section["id"], "first_name")
    add_field(as_alpha_admin, layout["id"], section["id"], "custom:qualification_details")

    detail = as_alpha_admin.get(f"/crm/layouts/{layout['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "DRAFT"
    assert len(body["sections"]) == 1
    assert {f["field_key"] for f in body["sections"][0]["fields"]} == {
        "first_name",
        "custom:qualification_details",
    }


def test_reordering_fields_persists(as_alpha_admin: ApiSession) -> None:
    layout = make_layout(as_alpha_admin, name="Reorder Layout")
    section = make_section(as_alpha_admin, layout["id"])
    a = add_field(as_alpha_admin, layout["id"], section["id"], "first_name")
    b = add_field(as_alpha_admin, layout["id"], section["id"], "last_name")

    response = as_alpha_admin.post(
        f"/crm/layouts/{layout['id']}/fields/reorder",
        json={
            "fields": [
                {"field_id": b["id"], "section_id": section["id"], "position": 0},
                {"field_id": a["id"], "section_id": section["id"], "position": 1},
            ]
        },
    )
    assert response.status_code == 200, response.text

    detail = as_alpha_admin.get(f"/crm/layouts/{layout['id']}").json()
    ordered = [f["field_key"] for f in detail["sections"][0]["fields"]]
    assert ordered == ["last_name", "first_name"]


def test_an_unknown_field_key_is_refused(as_alpha_admin: ApiSession) -> None:
    layout = make_layout(as_alpha_admin, name="Bad Field Layout")
    section = make_section(as_alpha_admin, layout["id"])
    response = as_alpha_admin.post(
        f"/crm/layouts/{layout['id']}/fields",
        json={"section_id": section["id"], "field_key": "not_a_real_field"},
    )
    assert response.status_code == 422, response.text


def test_a_rep_may_view_but_not_build_layouts(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    layout = make_layout(as_alpha_admin, name="Rep View Layout")

    listing = as_alpha_rep.get("/crm/layouts", params={"entity_type": "LEAD"})
    assert listing.status_code == 200, listing.text

    denied = as_alpha_rep.post("/crm/layouts", json={"entity_type": "LEAD", "name": "Nope"})
    assert denied.status_code == 403

    denied_section = as_alpha_rep.post(
        f"/crm/layouts/{layout['id']}/sections", json={"name": "x"}
    )
    assert denied_section.status_code == 403


def test_layout_isolation_between_organizations(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    layout = make_layout(as_alpha_admin, name="Alpha-Only Layout")
    response = as_beta_admin.get(f"/crm/layouts/{layout['id']}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


def test_publishing_an_empty_layout_is_refused(as_alpha_admin: ApiSession) -> None:
    layout = make_layout(as_alpha_admin, name="Empty Layout")
    response = as_alpha_admin.post(f"/crm/layouts/{layout['id']}/publish")
    assert response.status_code == 422, response.text


def test_publishing_demotes_the_previously_published_layout(as_alpha_admin: ApiSession) -> None:
    first = make_layout(as_alpha_admin, name="First Published")
    section = make_section(as_alpha_admin, first["id"])
    add_field(as_alpha_admin, first["id"], section["id"], "first_name")
    published = as_alpha_admin.post(f"/crm/layouts/{first['id']}/publish")
    assert published.status_code == 200, published.text

    second = make_layout(as_alpha_admin, name="Second Published")
    section2 = make_section(as_alpha_admin, second["id"])
    add_field(as_alpha_admin, second["id"], section2["id"], "last_name")
    published2 = as_alpha_admin.post(f"/crm/layouts/{second['id']}/publish")
    assert published2.status_code == 200, published2.text

    first_after = as_alpha_admin.get(f"/crm/layouts/{first['id']}").json()
    assert first_after["status"] == "DRAFT"

    live = as_alpha_admin.get("/crm/layouts/published", params={"entity_type": "LEAD"}).json()
    assert live["id"] == second["id"]


def test_a_rule_may_only_target_a_placed_custom_field(as_alpha_admin: ApiSession) -> None:
    layout = make_layout(as_alpha_admin, name="Rule Target Layout")
    response = as_alpha_admin.post(
        f"/crm/layouts/{layout['id']}/rules",
        json={
            "target_field_key": "first_name",  # built-in, not custom
            "conditions": [{"field_key": "status", "operator": "equals", "value": "QUALIFIED"}],
            "effect_visible": True,
            "effect_required": True,
        },
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Conditional rules: preview and — the important part — server enforcement
# ---------------------------------------------------------------------------


def _build_qualification_layout(api: ApiSession) -> dict:
    make_custom_field(api)
    layout = make_layout(api, name="Qualification Layout")
    section = make_section(api, layout["id"])
    add_field(api, layout["id"], section["id"], "custom:qualification_details")
    rule = api.post(
        f"/crm/layouts/{layout['id']}/rules",
        json={
            "target_field_key": "custom:qualification_details",
            "conditions": [{"field_key": "status", "operator": "equals", "value": "QUALIFIED"}],
            "logic": "AND",
            "effect_visible": True,
            "effect_required": True,
        },
    )
    assert rule.status_code == 201, rule.text
    published = api.post(f"/crm/layouts/{layout['id']}/publish")
    assert published.status_code == 200, published.text
    return layout


def test_the_preview_endpoint_reflects_the_rule(as_alpha_admin: ApiSession) -> None:
    layout = _build_qualification_layout(as_alpha_admin)

    not_qualified = as_alpha_admin.post(
        f"/crm/layouts/{layout['id']}/evaluate", json={"values": {"status": "NEW"}}
    )
    assert not_qualified.status_code == 200, not_qualified.text
    assert not_qualified.json()["states"]["custom:qualification_details"]["required"] is False

    qualified = as_alpha_admin.post(
        f"/crm/layouts/{layout['id']}/evaluate", json={"values": {"status": "QUALIFIED"}}
    )
    assert qualified.json()["states"]["custom:qualification_details"]["required"] is True


def test_a_hidden_custom_field_from_the_layout_field_itself_stays_optional(
    as_alpha_admin: ApiSession,
) -> None:
    """A field the layout marks not-required is unaffected until a rule fires."""
    lead = make_lead(as_alpha_admin)
    _build_qualification_layout(as_alpha_admin)

    response = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"custom_fields": {"qualification_details": ""}}
    )
    assert response.status_code == 200, response.text


def test_conditional_required_is_enforced_server_side_on_write(
    as_alpha_admin: ApiSession,
) -> None:
    """The central proof: a published rule blocks a real write, not just a preview.

    Server-side validation is authoritative regardless of what any client
    rendered — this test never calls the preview/evaluate endpoint at all,
    only the ordinary lead create/status/update endpoints, and the rule still
    fires because the record's own state now matches its condition.
    """
    _build_qualification_layout(as_alpha_admin)
    lead = make_lead(as_alpha_admin)

    # Still NEW: the field the rule would require is not required yet.
    unrelated_edit = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"custom_fields": {"qualification_details": ""}}
    )
    assert unrelated_edit.status_code == 200, unrelated_edit.text

    contacted = as_alpha_admin.post(
        f"/crm/leads/{lead['id']}/status", json={"status": "CONTACTED"}
    )
    assert contacted.status_code == 200, contacted.text
    status_change = as_alpha_admin.post(
        f"/crm/leads/{lead['id']}/status", json={"status": "QUALIFIED"}
    )
    assert status_change.status_code == 200, status_change.text

    blocked = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"custom_fields": {"qualification_details": ""}}
    )
    assert blocked.status_code == 422, blocked.text
    assert "qualification_details" in blocked.json()["error"]["details"]["fields"]

    allowed = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}",
        json={"custom_fields": {"qualification_details": "Budget confirmed, champion identified."}},
    )
    assert allowed.status_code == 200, allowed.text
    assert (
        allowed.json()["custom_fields"]["qualification_details"]
        == "Budget confirmed, champion identified."
    )


def test_unpublishing_stops_enforcement(as_alpha_admin: ApiSession) -> None:
    layout = _build_qualification_layout(as_alpha_admin)
    lead = make_lead(as_alpha_admin)
    as_alpha_admin.post(f"/crm/leads/{lead['id']}/status", json={"status": "CONTACTED"})
    as_alpha_admin.post(f"/crm/leads/{lead['id']}/status", json={"status": "QUALIFIED"})

    unpublish = as_alpha_admin.post(f"/crm/layouts/{layout['id']}/unpublish")
    assert unpublish.status_code == 200, unpublish.text

    response = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"custom_fields": {"qualification_details": ""}}
    )
    assert response.status_code == 200, response.text
