"""Stage 2: CSV import, export, undo and bulk operations.

Import is the adoption blocker the analysis names (§5.8), so the cases here are
weighted towards the ways an importer destroys data rather than the happy path:
a sparse file blanking populated columns, an undo removing records it did not
create, and a bulk action reaching a record the caller cannot see.
"""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """A second signed-in session for alpha's plain ``User``."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


def _upload(
    session: ApiSession,
    module: str,
    csv_text: str,
    *,
    path: str = "",
    **form: object,
) -> object:
    """POST a CSV to an import endpoint as multipart form data."""
    data = {key: str(value) for key, value in form.items()}
    return session.post(
        f"/crm/data/{module}{path}",
        files={"file": ("upload.csv", io.BytesIO(csv_text.encode()), "text/csv")},
        data=data,
    )


LEADS_CSV = """First Name,Last Name,Company,Email,Phone
Ada,Lovelace,Analytical Engines,ada@engines.example,555-0100
Grace,Hopper,Hopper Systems,grace@hopper.example,555-0101
"""


# --- Discovery ---------------------------------------------------------------


def test_the_module_catalog_describes_importable_fields(
    as_alpha_admin: ApiSession,
) -> None:
    """The mapping UI needs the field list, its types and its required set."""
    catalog = as_alpha_admin.get("/crm/data/modules")

    assert catalog.status_code == 200, catalog.text
    modules = {module["key"]: module for module in catalog.json()["modules"]}
    assert {"leads", "accounts", "contacts", "opportunities"} <= set(modules)

    leads = modules["leads"]
    assert "last_name" in leads["required_fields"]
    assert "email" in leads["match_fields"]
    status_field = next(f for f in leads["fields"] if f["name"] == "status")
    assert "QUALIFIED" in status_field["choices"]


# --- Preview -----------------------------------------------------------------


def test_a_preview_reports_what_would_happen_and_writes_nothing(
    as_alpha_admin: ApiSession,
) -> None:
    """A dry run must be the real run with the writes turned off."""
    response = _upload(as_alpha_admin, "leads", LEADS_CSV, path="/preview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_rows"] == 2
    assert body["will_create"] == 2
    assert body["error_count"] == 0
    # Auto-mapping matched "First Name" to first_name.
    assert body["mapping"]["First Name"] == "first_name"
    assert body["unmapped_headers"] == []

    listed = as_alpha_admin.get("/crm/leads").json()
    assert listed["pagination"]["total"] == 0, "preview must not create records"


def test_a_preview_reports_unmapped_columns(as_alpha_admin: ApiSession) -> None:
    """A silently dropped column is data the customer believes they imported."""
    csv_text = "First Name,Last Name,Favourite Colour\nAda,Lovelace,Green\n"

    response = _upload(as_alpha_admin, "leads", csv_text, path="/preview")

    assert response.status_code == 200, response.text
    assert response.json()["unmapped_headers"] == ["Favourite Colour"]


def test_a_file_whose_columns_match_nothing_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    """Almost always a file whose first row is data rather than headers."""
    csv_text = "aaa,bbb,ccc\n1,2,3\n"

    response = _upload(as_alpha_admin, "leads", csv_text, path="/preview")

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "import_file_invalid"


def test_an_empty_file_is_refused(as_alpha_admin: ApiSession) -> None:
    response = _upload(as_alpha_admin, "leads", "   ", path="/preview")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "import_file_invalid"


# --- Import ------------------------------------------------------------------


def test_importing_leads_creates_them(as_alpha_admin: ApiSession) -> None:
    response = _upload(as_alpha_admin, "leads", LEADS_CSV)

    assert response.status_code == 201, response.text
    job = response.json()["job"]
    assert job["created_count"] == 2
    assert job["error_count"] == 0

    listed = as_alpha_admin.get("/crm/leads").json()
    assert listed["pagination"]["total"] == 2
    names = {row["last_name"] for row in listed["data"]}
    assert names == {"Lovelace", "Hopper"}


def test_a_bad_row_fails_alone_and_the_file_still_lands(
    as_alpha_admin: ApiSession,
) -> None:
    """Failing 4,000 rows over one typo is how people import nothing."""
    csv_text = (
        "First Name,Last Name,Expected Deal Size\n"
        "Ada,Lovelace,50000\n"
        "Bad,Row,not-a-number\n"
        "Grace,Hopper,25000\n"
    )

    response = _upload(as_alpha_admin, "leads", csv_text)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["job"]["created_count"] == 2
    assert body["job"]["error_count"] == 1

    error = body["errors"][0]
    # Row 3 of the spreadsheet: header is row 1, so the number is the line the
    # customer can actually go and look at.
    assert error["row_number"] == 3
    assert error["field_name"] == "expected_deal_size"


def test_a_missing_required_field_is_reported_per_row(
    as_alpha_admin: ApiSession,
) -> None:
    csv_text = "First Name,Last Name\nAda,\nGrace,Hopper\n"

    response = _upload(as_alpha_admin, "leads", csv_text)

    body = response.json()
    assert body["job"]["created_count"] == 1
    assert body["job"]["error_count"] == 1
    assert "required" in body["errors"][0]["message"]


def test_an_invalid_picklist_value_names_the_valid_ones(
    as_alpha_admin: ApiSession,
) -> None:
    """"Invalid status" without the list is a support ticket, not a fix."""
    csv_text = "First Name,Last Name,Status\nAda,Lovelace,MAYBE\n"

    response = _upload(as_alpha_admin, "leads", csv_text)

    body = response.json()
    assert body["job"]["error_count"] == 1
    assert "QUALIFIED" in body["errors"][0]["message"]


def test_update_mode_matches_on_email_and_does_not_duplicate(
    as_alpha_admin: ApiSession,
) -> None:
    _upload(as_alpha_admin, "leads", LEADS_CSV)

    updated_csv = (
        "Email,First Name,Last Name,Industry\n"
        "ada@engines.example,Ada,Lovelace,Software\n"
    )
    response = _upload(
        as_alpha_admin, "leads", updated_csv, mode="UPDATE", match_field="email"
    )

    assert response.status_code == 201, response.text
    assert response.json()["job"]["updated_count"] == 1
    assert response.json()["job"]["created_count"] == 0

    listed = as_alpha_admin.get("/crm/leads").json()
    assert listed["pagination"]["total"] == 2, "update must not insert a second row"
    ada = next(row for row in listed["data"] if row["email"] == "ada@engines.example")
    assert ada["industry"] == "Software"


def test_both_mode_updates_matches_and_inserts_the_rest(
    as_alpha_admin: ApiSession,
) -> None:
    _upload(as_alpha_admin, "leads", LEADS_CSV)

    mixed = (
        "Email,First Name,Last Name,Industry\n"
        "ada@engines.example,Ada,Lovelace,Software\n"
        "katherine@nasa.example,Katherine,Johnson,Aerospace\n"
    )
    response = _upload(
        as_alpha_admin, "leads", mixed, mode="BOTH", match_field="email"
    )

    job = response.json()["job"]
    assert job["updated_count"] == 1
    assert job["created_count"] == 1
    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 3


def test_empty_cells_do_not_blank_populated_fields(
    as_alpha_admin: ApiSession,
) -> None:
    """The single checkbox that prevents the most destructive import.

    A spreadsheet that simply does not carry a phone column would otherwise
    erase every phone number it touched.
    """
    _upload(as_alpha_admin, "leads", LEADS_CSV)

    sparse = "Email,First Name,Last Name,Phone\nada@engines.example,Ada,Lovelace,\n"
    response = _upload(
        as_alpha_admin,
        "leads",
        sparse,
        mode="UPDATE",
        match_field="email",
        skip_empty_values=True,
    )
    assert response.status_code == 201, response.text

    listed = as_alpha_admin.get("/crm/leads").json()["data"]
    ada = next(row for row in listed if row["email"] == "ada@engines.example")
    assert ada["phone"] == "555-0100", "an empty cell must not clear a stored value"


def test_turning_the_guard_off_does_clear_the_value(
    as_alpha_admin: ApiSession,
) -> None:
    """Guards the guard: the protection must be doing something."""
    _upload(as_alpha_admin, "leads", LEADS_CSV)

    sparse = "Email,First Name,Last Name,Phone\nada@engines.example,Ada,Lovelace,\n"
    _upload(
        as_alpha_admin,
        "leads",
        sparse,
        mode="UPDATE",
        match_field="email",
        skip_empty_values=False,
    )

    listed = as_alpha_admin.get("/crm/leads").json()["data"]
    ada = next(row for row in listed if row["email"] == "ada@engines.example")
    assert ada["phone"] is None


def test_a_relation_can_be_given_by_name(as_alpha_admin: ApiSession) -> None:
    """A migrated contact list holds company names, never CRM identifiers."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Engines Ltd"})
    assert account.status_code == 201, account.text

    csv_text = "First Name,Last Name,Account\nAda,Lovelace,Engines Ltd\n"
    response = _upload(as_alpha_admin, "contacts", csv_text)

    assert response.status_code == 201, response.text
    assert response.json()["job"]["created_count"] == 1
    contact = as_alpha_admin.get("/crm/contacts").json()["data"][0]
    assert str(contact["account_id"]) == str(account.json()["id"])


def test_an_unresolvable_relation_is_a_row_error(as_alpha_admin: ApiSession) -> None:
    csv_text = "First Name,Last Name,Account\nAda,Lovelace,No Such Company\n"

    response = _upload(as_alpha_admin, "contacts", csv_text)

    body = response.json()
    assert body["job"]["created_count"] == 0
    assert body["job"]["error_count"] == 1
    assert "No Such Company" in body["errors"][0]["message"]


def test_import_errors_are_retrievable_afterwards(as_alpha_admin: ApiSession) -> None:
    """A summary that says "412 failed" and cannot say which is not a report."""
    csv_text = "First Name,Last Name,Status\nAda,Lovelace,NONSENSE\n"
    job_id = _upload(as_alpha_admin, "leads", csv_text).json()["job"]["id"]

    errors = as_alpha_admin.get(f"/crm/data/{job_id}/errors")

    assert errors.status_code == 200, errors.text
    assert len(errors.json()) == 1
    assert errors.json()[0]["row_number"] == 2


# --- Undo --------------------------------------------------------------------


def test_undo_archives_the_records_the_import_created(
    as_alpha_admin: ApiSession,
) -> None:
    job_id = _upload(as_alpha_admin, "leads", LEADS_CSV).json()["job"]["id"]
    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 2

    undo = as_alpha_admin.post(f"/crm/data/{job_id}/undo")

    assert undo.status_code == 200, undo.text
    assert undo.json()["archived"] == 2
    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 0


def test_undo_never_removes_a_record_that_existed_before(
    as_alpha_admin: ApiSession,
) -> None:
    """The property that makes undo safe to offer at all."""
    existing = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company": "Analytical Engines",
            "email": "ada@engines.example",
        },
    )
    assert existing.status_code == 201, existing.text
    existing_id = existing.json()["id"]

    # An UPDATE-mode import touches it but does not create it.
    updated_csv = "Email,First Name,Last Name,Industry\nada@engines.example,Ada,Lovelace,Software\n"
    job_id = _upload(
        as_alpha_admin, "leads", updated_csv, mode="UPDATE", match_field="email"
    ).json()["job"]["id"]

    undo = as_alpha_admin.post(f"/crm/data/{job_id}/undo")

    assert undo.status_code == 200, undo.text
    assert undo.json()["archived"] == 0
    assert undo.json()["updates_not_reverted"] == 1
    # The pre-existing lead is untouched.
    assert as_alpha_admin.get(f"/crm/leads/{existing_id}").status_code == 200


def test_an_import_cannot_be_undone_twice(as_alpha_admin: ApiSession) -> None:
    job_id = _upload(as_alpha_admin, "leads", LEADS_CSV).json()["job"]["id"]
    assert as_alpha_admin.post(f"/crm/data/{job_id}/undo").status_code == 200

    second = as_alpha_admin.post(f"/crm/data/{job_id}/undo")

    assert second.status_code == 422
    assert second.json()["error"]["code"] == "import_not_undoable"


# --- Export ------------------------------------------------------------------


def test_export_requires_the_export_permission(
    as_alpha_admin: ApiSession, rep: ApiSession
) -> None:
    """The permission the catalogue has always promised and nothing used."""
    _upload(as_alpha_admin, "leads", LEADS_CSV)

    allowed = as_alpha_admin.get("/crm/data/leads/export")
    assert allowed.status_code == 200, allowed.text

    # The plain User role holds VIEW/CREATE/EDIT but not EXPORT.
    refused = rep.get("/crm/data/leads/export")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "permission_denied"


def test_an_export_round_trips_back_through_the_importer(
    as_alpha_admin: ApiSession,
) -> None:
    """ISO formats throughout, so a downloaded file is a valid upload."""
    _upload(as_alpha_admin, "leads", LEADS_CSV)

    exported = as_alpha_admin.get("/crm/data/leads/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert exported.headers["X-Exported-Rows"] == "2"

    body = exported.text
    assert "last_name" in body.splitlines()[0]
    assert "Lovelace" in body

    # Re-importing the export as an update must match every row, not duplicate.
    response = _upload(
        as_alpha_admin, "leads", body, mode="UPDATE", match_field="email"
    )
    assert response.status_code == 201, response.text
    assert response.json()["job"]["updated_count"] == 2


def test_an_export_does_not_leak_another_tenants_rows(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    _upload(api, "leads", LEADS_CSV)

    api.login(beta.admin.email, organization_id=beta.organization_id)
    exported = api.get("/crm/data/leads/export")

    assert exported.status_code == 200
    assert "Lovelace" not in exported.text
    assert exported.headers["X-Exported-Rows"] == "0"


# --- Bulk operations ---------------------------------------------------------


def test_bulk_update_sets_a_field_on_many_records(as_alpha_admin: ApiSession) -> None:
    _upload(as_alpha_admin, "leads", LEADS_CSV)
    ids = [row["id"] for row in as_alpha_admin.get("/crm/leads").json()["data"]]

    response = as_alpha_admin.post(
        "/crm/data/leads/bulk/update",
        json={"ids": ids, "values": {"priority": "HIGH"}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 2
    for row in as_alpha_admin.get("/crm/leads").json()["data"]:
        assert row["priority"] == "HIGH"


def test_bulk_update_refuses_a_field_that_is_not_bulk_editable(
    as_alpha_admin: ApiSession,
) -> None:
    """Mass-editing a name is a mistake nobody meant to make at scale."""
    _upload(as_alpha_admin, "leads", LEADS_CSV)
    ids = [row["id"] for row in as_alpha_admin.get("/crm/leads").json()["data"]]

    response = as_alpha_admin.post(
        "/crm/data/leads/bulk/update",
        json={"ids": ids, "values": {"last_name": "Overwritten"}},
    )

    assert response.status_code == 422, response.text


def test_bulk_archive_and_restore_round_trip(as_alpha_admin: ApiSession) -> None:
    """Soft delete without restore is not a safety net."""
    _upload(as_alpha_admin, "leads", LEADS_CSV)
    ids = [row["id"] for row in as_alpha_admin.get("/crm/leads").json()["data"]]

    archived = as_alpha_admin.post("/crm/data/leads/bulk/archive", json={"ids": ids})
    assert archived.status_code == 200, archived.text
    assert archived.json()["changed"] == 2
    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 0

    restored = as_alpha_admin.post("/crm/data/leads/bulk/restore", json={"ids": ids})
    assert restored.status_code == 200, restored.text
    assert restored.json()["changed"] == 2
    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 2


def test_bulk_owner_assignment_reassigns_many_records(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    _upload(as_alpha_admin, "leads", LEADS_CSV)
    ids = [row["id"] for row in as_alpha_admin.get("/crm/leads").json()["data"]]

    response = as_alpha_admin.post(
        "/crm/data/leads/bulk/owner",
        json={"ids": ids, "owner_id": str(alpha.member.user_id)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 2
    for row in as_alpha_admin.get("/crm/leads").json()["data"]:
        assert str(row["owner_id"]) == str(alpha.member.user_id)


def test_a_bulk_action_cannot_reach_another_tenants_records(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """Foreign ids are dropped silently, not refused: a refusal confirms them."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    _upload(api, "leads", LEADS_CSV)
    alpha_ids = [row["id"] for row in api.get("/crm/leads").json()["data"]]

    api.login(beta.admin.email, organization_id=beta.organization_id)
    response = api.post(
        "/crm/data/leads/bulk/archive", json={"ids": alpha_ids}
    )

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 0

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    assert api.get("/crm/leads").json()["pagination"]["total"] == 2


def test_a_bulk_action_respects_record_visibility(
    as_alpha_admin: ApiSession, rep: ApiSession
) -> None:
    """A rep must not bulk-edit records they cannot open."""
    _upload(as_alpha_admin, "leads", LEADS_CSV)
    ids = [row["id"] for row in as_alpha_admin.get("/crm/leads").json()["data"]]

    response = rep.post(
        "/crm/data/leads/bulk/update",
        json={"ids": ids, "values": {"priority": "LOW"}},
    )

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 0


def test_bulk_stage_moves_run_the_real_stage_rules(
    as_alpha_admin: ApiSession,
) -> None:
    """A blind UPDATE would skip win/loss handling, history and follow-ups."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Bulk Stage Ltd"}).json()
    stages = as_alpha_admin.get("/crm/opportunities/stages").json()
    qualification = next(s for s in stages if s["name"] == "Qualification")
    lost = next(s for s in stages if s["name"] == "Closed Lost")

    ids = []
    for index in range(2):
        created = as_alpha_admin.post(
            "/crm/opportunities",
            json={
                "name": f"Deal {index}",
                "account_id": str(account["id"]),
                "stage_id": str(qualification["id"]),
                "expected_close_date": "2026-12-31",
            },
        )
        assert created.status_code == 201, created.text
        ids.append(created.json()["id"])

    # A lost stage without a reason must be refused, per deal, not silently done.
    refused = as_alpha_admin.post(
        "/crm/data/opportunities/bulk/stage",
        json={"ids": ids, "stage_id": str(lost["id"])},
    )
    assert refused.status_code == 200, refused.text
    assert refused.json()["changed"] == 0
    assert len(refused.json()["failures"]) == 2

    accepted = as_alpha_admin.post(
        "/crm/data/opportunities/bulk/stage",
        json={
            "ids": ids,
            "stage_id": str(lost["id"]),
            "loss_reason": "Budget cut",
        },
    )
    assert accepted.json()["changed"] == 2
    for opportunity_id in ids:
        deal = as_alpha_admin.get(f"/crm/opportunities/{opportunity_id}").json()
        assert deal["lost_at"] is not None
        assert deal["loss_reason"] == "Budget cut"
        history = as_alpha_admin.get(
            f"/crm/opportunities/{opportunity_id}/history"
        ).json()
        assert len(history) == 2, "the stage move must be recorded in history"


def test_an_empty_bulk_selection_is_rejected(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post("/crm/data/leads/bulk/archive", json={"ids": []})

    assert response.status_code == 422


def test_an_unknown_module_is_rejected(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/crm/data/nonsense/bulk/archive", json={"ids": [str(uuid.uuid4())]}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_module"
