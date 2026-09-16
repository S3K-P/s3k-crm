"""Checkpoint 4 additions to CSV import: custom-field mapping targets and
saved mapping templates.

Reuses exactly the infrastructure ``test_csv_import.py`` already exercises
(the same preview/commit endpoints, the same per-row SAVEPOINT isolation) —
these tests are only about the two things added on top of it: a CSV column
can now map onto a tenant-defined field, validated by the same
``CustomFieldValueService`` every other write already goes through; and a
mapping, once built, can be saved and listed back for reuse.
"""

from __future__ import annotations

import json

import pytest
from httpx import Response

from tests.integration.conftest import ApiSession

pytestmark = pytest.mark.integration


def _csv(*lines: str) -> bytes:
    return ("\r\n".join(lines) + "\r\n").encode()


def _upload(
    session: ApiSession,
    *,
    slug: str,
    body: bytes,
    mapping: dict[str, str],
    dry_run: bool,
    duplicate_policy: str = "SKIP",
) -> Response:
    step = "preview" if dry_run else "commit"
    return session.post(
        f"/crm/imports/{slug}/{step}",
        files={"file": ("import.csv", body, "text/csv")},
        data={"mapping": json.dumps(mapping), "duplicate_policy": duplicate_policy},
    )


def make_custom_field(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "entity_type": "LEAD",
        "api_name": "territory",
        "label": "Territory",
        "field_type": "TEXT",
    }
    payload.update(overrides)
    response = api.post("/crm/custom-fields", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Custom-field mapping targets
# ---------------------------------------------------------------------------


def test_the_entity_catalogue_offers_this_organizations_custom_fields(
    as_alpha_admin: ApiSession,
) -> None:
    make_custom_field(as_alpha_admin)
    response = as_alpha_admin.get("/crm/imports/entities")
    assert response.status_code == 200, response.text
    leads = next(e for e in response.json() if e["slug"] == "leads")
    names = {field["name"] for field in leads["fields"]}
    assert "custom:territory" in names


def test_a_column_can_be_mapped_onto_a_custom_field_and_survives_the_round_trip(
    as_alpha_admin: ApiSession,
) -> None:
    make_custom_field(as_alpha_admin, is_required=False)
    body = _csv(
        "First name,Last name,Region",
        "Asha,Rao,EMEA",
    )
    committed = _upload(
        as_alpha_admin,
        slug="leads",
        body=body,
        mapping={
            "First name": "first_name",
            "Last name": "last_name",
            "Region": "custom:territory",
        },
        dry_run=False,
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["summary"]["created"] == 1

    leads = as_alpha_admin.get("/crm/leads", params={"search": "Asha"}).json()["data"]
    assert leads[0]["custom_fields"]["territory"] == "EMEA"


def test_a_required_custom_field_left_unmapped_fails_the_row_not_the_file(
    as_alpha_admin: ApiSession,
) -> None:
    make_custom_field(as_alpha_admin, is_required=True)
    body = _csv(
        "First name,Last name",
        "Asha,Rao",
        "Bala,Iyer",
    )
    result = _upload(
        as_alpha_admin,
        slug="leads",
        body=body,
        mapping={"First name": "first_name", "Last name": "last_name"},
        dry_run=True,
    )
    assert result.status_code == 200, result.text
    body_json = result.json()
    assert body_json["summary"]["created"] == 0
    assert body_json["summary"]["failed"] == 2
    assert any("territory" in issue["message"] for issue in body_json["errors"])


def test_an_unknown_custom_field_target_is_refused_before_the_file_is_read(
    as_alpha_admin: ApiSession,
) -> None:
    # No such field exists, so mapping a header onto it is refused as unknown.
    response = as_alpha_admin.post(
        "/crm/imports/leads/preview",
        files={"file": ("import.csv", _csv("First name,Last name,X", "Asha,Rao,Z"), "text/csv")},
        data={
            "mapping": json.dumps(
                {"First name": "first_name", "Last name": "last_name", "X": "custom:not_real"}
            ),
            "duplicate_policy": "SKIP",
        },
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Saved mapping templates
# ---------------------------------------------------------------------------


def test_a_mapping_template_can_be_saved_and_listed(as_alpha_admin: ApiSession) -> None:
    make_custom_field(as_alpha_admin)
    saved = as_alpha_admin.post(
        "/crm/imports/leads/mapping-templates",
        json={
            "name": "Monthly export",
            "mapping": {
                "First name": "first_name",
                "Last name": "last_name",
                "Region": "custom:territory",
            },
            "duplicate_policy": "SKIP",
        },
    )
    assert saved.status_code == 201, saved.text
    template_id = saved.json()["id"]

    listed = as_alpha_admin.get("/crm/imports/leads/mapping-templates")
    assert listed.status_code == 200, listed.text
    assert any(t["id"] == template_id for t in listed.json())


def test_a_mapping_template_naming_an_unknown_field_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.post(
        "/crm/imports/leads/mapping-templates",
        json={
            "name": "Bad template",
            "mapping": {"X": "not_a_real_field"},
            "duplicate_policy": "SKIP",
        },
    )
    assert response.status_code == 422, response.text


def test_a_saved_template_can_be_deleted(as_alpha_admin: ApiSession) -> None:
    saved = as_alpha_admin.post(
        "/crm/imports/leads/mapping-templates",
        json={"name": "Throwaway", "mapping": {"A": "first_name"}, "duplicate_policy": "SKIP"},
    )
    template_id = saved.json()["id"]

    deleted = as_alpha_admin.delete(f"/crm/imports/leads/mapping-templates/{template_id}")
    assert deleted.status_code == 204, deleted.text

    listed = as_alpha_admin.get("/crm/imports/leads/mapping-templates").json()
    assert all(t["id"] != template_id for t in listed)


def test_templates_are_isolated_per_entity_slug(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post(
        "/crm/imports/leads/mapping-templates",
        json={"name": "Leads mapping", "mapping": {"A": "first_name"}, "duplicate_policy": "SKIP"},
    )
    accounts_templates = as_alpha_admin.get("/crm/imports/accounts/mapping-templates").json()
    assert accounts_templates == []
