"""CSV import (`P3-W23-BE-01`, `P3-W23-BE-03`, `P3-W23-QA-01`).

The properties worth holding, in the order they would hurt:

* a caller without ``CREATE`` on the target module cannot import, and cannot
  use a *preview* to probe the organization's duplicate rule either;
* a preview keeps nothing — including the audit rows its creates produced;
* an invalid row is reported with its line and its column, and never silently
  accepted;
* one bad row does not take the rest of the file with it;
* imported records land in the caller's organization and nowhere else.

Every assertion goes through HTTP with a real multipart upload against real
PostgreSQL, because a service-level test would prove the parser works, not
that the endpoint authorizes.
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.products.crm.imports.service import MAX_IMPORT_ROWS
from tests.integration.conftest import (
    ApiSession,
    Tenant,
    grant_custom_role,
    membership_id_for,
    revoke_all_roles,
)

pytestmark = pytest.mark.integration

LEAD_MAPPING = {"First name": "first_name", "Last name": "last_name", "Email": "email"}
ACCOUNT_MAPPING = {"Name": "name", "Industry": "industry"}


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
    filename: str = "import.csv",
) -> Response:
    step = "preview" if dry_run else "commit"
    return session.post(
        f"/crm/imports/{slug}/{step}",
        files={"file": (filename, body, "text/csv")},
        data={"mapping": json.dumps(mapping), "duplicate_policy": duplicate_policy},
    )


def _leads_csv(*rows: str) -> bytes:
    return _csv("First name,Last name,Email", *rows)


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """Alpha's plain ``User`` — holds ``leads.CREATE``."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


# --- The catalogue ----------------------------------------------------------


def test_the_importable_entities_are_described(as_alpha_admin: ApiSession) -> None:
    """The mapping step renders itself from this."""
    response = as_alpha_admin.get("/crm/imports/entities")

    assert response.status_code == 200, response.text
    slugs = {entity["slug"] for entity in response.json()}
    assert slugs == {"leads", "accounts", "contacts"}


def test_required_fields_are_flagged_for_the_mapping_step(as_alpha_admin: ApiSession) -> None:
    entities = as_alpha_admin.get("/crm/imports/entities").json()
    leads = next(entity for entity in entities if entity["slug"] == "leads")

    required = {field["name"] for field in leads["fields"] if field["required"]}
    assert required == {"first_name", "last_name"}
    assert leads["max_rows"] == MAX_IMPORT_ROWS


def test_an_entity_that_cannot_be_imported_is_404(as_alpha_admin: ApiSession) -> None:
    """Opportunities are deliberately not importable."""
    response = _upload(
        as_alpha_admin,
        slug="opportunities",
        body=_leads_csv("A,B,a@b.example"),
        mapping=LEAD_MAPPING,
        dry_run=True,
    )

    assert response.status_code == 404


# --- Authorization ----------------------------------------------------------


@pytest.mark.parametrize("step", ["preview", "commit"])
async def test_importing_without_create_is_refused(
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    step: str,
) -> None:
    """Import requires ``<module>.CREATE`` on the entity being imported into.

    All three seeded roles hold CREATE on all three importable modules, so the
    refusal is proven with a custom role that holds only ``leads.VIEW`` --
    which is what a real tenant's read-only role looks like, and the case where
    letting an import through would be worst.
    """
    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await revoke_all_roles(session_factory, membership_id)
    await grant_custom_role(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=("leads.VIEW",),
    )

    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)

    response = _upload(
        session,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=step == "preview",
    )

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_denied"


async def test_a_refused_import_creates_nothing(
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The 403 lands before the file is read, so nothing can leak through."""
    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await revoke_all_roles(session_factory, membership_id)
    await grant_custom_role(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=("leads.VIEW",),
    )

    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    _upload(
        session,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=False,
    )

    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 0


@pytest.mark.parametrize("step", ["preview", "commit"])
def test_an_unauthenticated_import_is_401(client: TestClient, step: str) -> None:
    response = client.post(
        f"/api/v1/crm/imports/leads/{step}",
        files={"file": ("import.csv", _leads_csv("A,B,a@b.example"), "text/csv")},
        data={"mapping": json.dumps(LEAD_MAPPING)},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("step", ["preview", "commit"])
def test_a_preview_needs_the_same_permission_as_a_commit(
    as_alpha_admin: ApiSession, step: str
) -> None:
    """A preview runs the real creates, so it is not a lesser act.

    Treating it as read-only would let a caller without ``CREATE`` learn
    whether an email is already on a lead, by reading the duplicate report.
    """
    response = _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=step == "preview",
    )

    assert response.status_code == 200, response.text


# --- The dry run ------------------------------------------------------------


def test_a_preview_reports_what_would_happen(as_alpha_admin: ApiSession) -> None:
    response = _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com", "Alan,Turing,alan@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=True,
    )

    body = response.json()
    assert response.status_code == 200, response.text
    assert body["dry_run"] is True
    assert body["summary"] == {
        "total_rows": 2,
        "created": 2,
        "skipped_duplicates": 0,
        "failed": 0,
    }


def test_a_preview_persists_nothing(as_alpha_admin: ApiSession) -> None:
    """The whole point of a dry run."""
    before = as_alpha_admin.get("/crm/leads").json()["pagination"]["total"]

    _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=True,
    )

    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == before


def test_a_preview_writes_no_audit_entry(as_alpha_admin: ApiSession) -> None:
    """Nothing happened, so the trail must not say something did."""
    _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=True,
    )

    entries = as_alpha_admin.get("/audit-logs", params={"page_size": 200}).json()["data"]
    assert [entry for entry in entries if entry["action"] == "RECORDS_IMPORTED"] == []
    assert [entry for entry in entries if entry["action"] == "CREATED"] == []


def test_the_preview_and_the_commit_agree(as_alpha_admin: ApiSession) -> None:
    """Same execution, so the summaries must match exactly."""
    body = _leads_csv(
        "Ada,Lovelace,ada@example.com",
        "Alan,,alan@example.com",
        "Grace,Hopper,not-an-email",
    )

    preview = _upload(
        as_alpha_admin, slug="leads", body=body, mapping=LEAD_MAPPING, dry_run=True
    ).json()
    commit = _upload(
        as_alpha_admin, slug="leads", body=body, mapping=LEAD_MAPPING, dry_run=False
    ).json()

    assert preview["summary"] == commit["summary"]
    assert preview["dry_run"] is True
    assert commit["dry_run"] is False


# --- Committing -------------------------------------------------------------


def test_a_commit_creates_the_records(as_alpha_admin: ApiSession) -> None:
    response = _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com", "Alan,Turing,alan@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=False,
    )

    assert response.status_code == 200, response.text
    assert response.json()["summary"]["created"] == 2

    names = {
        f'{row["first_name"]} {row["last_name"]}'
        for row in as_alpha_admin.get("/crm/leads").json()["data"]
    }
    assert {"Ada Lovelace", "Alan Turing"} <= names


def test_imported_records_belong_to_the_callers_organization(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    beta: Tenant,
) -> None:
    _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=False,
    )

    other = ApiSession(client, integration_settings.api_prefix)
    other.login(beta.admin.email, organization_id=beta.organization_id)

    assert other.get("/crm/leads").json()["data"] == []
    rows = as_alpha_admin.get("/crm/leads").json()["data"]
    assert all(row["organization_id"] == str(alpha.organization_id) for row in rows)


def test_the_importer_owns_what_they_imported(rep: ApiSession, alpha: Tenant) -> None:
    """Unowned rows are visible organization-wide, so ownership is not cosmetic."""
    _upload(
        rep,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=False,
    )

    row = rep.get("/crm/leads").json()["data"][0]
    assert row["owner_id"] == str(alpha.member.user_id)


def test_a_commit_is_audited_once_for_the_file(as_alpha_admin: ApiSession) -> None:
    _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com", "Alan,Turing,alan@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=False,
    )

    entries = as_alpha_admin.get("/audit-logs", params={"page_size": 200}).json()["data"]
    imports = [entry for entry in entries if entry["action"] == "RECORDS_IMPORTED"]

    assert len(imports) == 1
    detail = as_alpha_admin.get(f"/audit-logs/{imports[0]['id']}").json()
    assert detail["details"]["created"] == 2
    assert detail["details"]["total_rows"] == 2


def test_each_imported_record_is_also_audited_individually(
    as_alpha_admin: ApiSession,
) -> None:
    """Import reuses the entity service, so per-record auditing comes free."""
    _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=False,
    )

    entries = as_alpha_admin.get("/audit-logs", params={"page_size": 200}).json()["data"]
    created = [
        entry for entry in entries if entry["action"] == "CREATED" and entry["module"] == "leads"
    ]
    assert len(created) == 1


# --- Row-level validation ---------------------------------------------------


def test_an_invalid_row_is_reported_with_its_line_and_column(
    as_alpha_admin: ApiSession,
) -> None:
    body = _leads_csv("Ada,Lovelace,ada@example.com", "Grace,Hopper,not-an-email")

    result = _upload(
        as_alpha_admin, slug="leads", body=body, mapping=LEAD_MAPPING, dry_run=True
    ).json()

    assert result["summary"]["created"] == 1
    assert result["summary"]["failed"] == 1
    error = result["errors"][0]
    # Line 3: the header is line 1, so the second data row is line 3.
    assert error["row"] == 3
    assert error["field"] == "email"


def test_a_missing_required_field_is_reported(as_alpha_admin: ApiSession) -> None:
    result = _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=True,
    ).json()

    assert result["summary"]["failed"] == 1
    assert result["errors"][0]["field"] == "last_name"


def test_invalid_rows_are_never_silently_accepted(as_alpha_admin: ApiSession) -> None:
    """Two bad rows, nothing created, and both are named."""
    body = _leads_csv("Ada,,x@example.com", "Grace,Hopper,nope")

    result = _upload(
        as_alpha_admin, slug="leads", body=body, mapping=LEAD_MAPPING, dry_run=False
    ).json()

    assert result["summary"] == {
        "total_rows": 2,
        "created": 0,
        "skipped_duplicates": 0,
        "failed": 2,
    }
    assert {issue["row"] for issue in result["errors"]} == {2, 3}
    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 0


def test_one_bad_row_does_not_take_the_file_with_it(as_alpha_admin: ApiSession) -> None:
    """Partial failure: the good rows still land.

    Without a per-row SAVEPOINT the first failure aborts the transaction and
    every later row fails for an unrelated reason.
    """
    body = _leads_csv(
        "Ada,Lovelace,ada@example.com",
        "Bad,,broken",
        "Alan,Turing,alan@example.com",
    )

    result = _upload(
        as_alpha_admin, slug="leads", body=body, mapping=LEAD_MAPPING, dry_run=False
    ).json()

    assert result["summary"]["created"] == 2
    assert result["summary"]["failed"] == 1
    names = {
        f'{row["first_name"]} {row["last_name"]}'
        for row in as_alpha_admin.get("/crm/leads").json()["data"]
    }
    assert names == {"Ada Lovelace", "Alan Turing"}


def test_a_blank_optional_cell_is_absent_rather_than_empty(
    as_alpha_admin: ApiSession,
) -> None:
    """A spreadsheet cannot express "absent"; an empty string must not fail."""
    result = _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,"),
        mapping=LEAD_MAPPING,
        dry_run=False,
    ).json()

    assert result["summary"]["created"] == 1
    assert as_alpha_admin.get("/crm/leads").json()["data"][0]["email"] is None


# --- Duplicates -------------------------------------------------------------


def test_a_duplicate_is_skipped_by_default(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
    )

    result = _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=False,
        duplicate_policy="SKIP",
    ).json()

    assert result["summary"]["skipped_duplicates"] == 1
    assert result["summary"]["created"] == 0
    assert result["duplicates"][0]["row"] == 2
    assert result["duplicates"][0]["field"] == "email"
    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 1


def test_a_duplicate_can_be_imported_anyway(as_alpha_admin: ApiSession) -> None:
    """Decision C03: duplicates are warned about, not blocked."""
    as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
    )

    result = _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping=LEAD_MAPPING,
        dry_run=False,
        duplicate_policy="CREATE",
    ).json()

    assert result["summary"]["created"] == 1
    assert as_alpha_admin.get("/crm/leads").json()["pagination"]["total"] == 2


def test_duplicates_are_reported_separately_from_errors(as_alpha_admin: ApiSession) -> None:
    """A duplicate is a decision, not a mistake, and reads differently."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Acme Ltd"})

    result = _upload(
        as_alpha_admin,
        slug="accounts",
        body=_csv("Name,Industry", "Acme Ltd,Logistics"),
        mapping=ACCOUNT_MAPPING,
        dry_run=True,
    ).json()

    assert result["duplicates"] and not result["errors"]
    assert result["duplicates"][0]["field"] == "name"


# --- The file itself --------------------------------------------------------


def test_an_unmapped_column_is_reported_not_silently_dropped(
    as_alpha_admin: ApiSession,
) -> None:
    body = _csv("First name,Last name,Email,Nickname", "Ada,Lovelace,ada@example.com,Countess")

    result = _upload(
        as_alpha_admin, slug="leads", body=body, mapping=LEAD_MAPPING, dry_run=True
    ).json()

    assert result["ignored_columns"] == ["Nickname"]


def test_a_mapping_naming_an_unknown_field_is_refused(as_alpha_admin: ApiSession) -> None:
    response = _upload(
        as_alpha_admin,
        slug="leads",
        body=_leads_csv("Ada,Lovelace,ada@example.com"),
        mapping={"First name": "first_name", "Email": "not_a_field"},
        dry_run=True,
    )

    assert response.status_code == 422
    assert "not_a_field" in response.json()["error"]["message"]


def test_a_mapping_that_is_not_json_is_refused(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/crm/imports/leads/preview",
        files={"file": ("import.csv", _leads_csv("A,B,a@b.example"), "text/csv")},
        data={"mapping": "{not json"},
    )

    assert response.status_code == 422


def test_an_empty_file_is_refused(as_alpha_admin: ApiSession) -> None:
    response = _upload(
        as_alpha_admin, slug="leads", body=b"", mapping=LEAD_MAPPING, dry_run=True
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "import_file_invalid"


def test_a_binary_file_is_refused(as_alpha_admin: ApiSession) -> None:
    """A .csv name is not evidence of a CSV."""
    response = _upload(
        as_alpha_admin,
        slug="leads",
        body=b"PK\x03\x04\x00\x00rubbish\x00binary",
        mapping=LEAD_MAPPING,
        dry_run=True,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "import_file_invalid"


def test_a_header_only_file_imports_nothing_and_says_so(as_alpha_admin: ApiSession) -> None:
    result = _upload(
        as_alpha_admin,
        slug="leads",
        body=_csv("First name,Last name,Email"),
        mapping=LEAD_MAPPING,
        dry_run=True,
    ).json()

    assert result["summary"]["total_rows"] == 0


def test_a_file_over_the_row_limit_is_refused(as_alpha_admin: ApiSession) -> None:
    """The ceiling is enforced, not merely documented."""
    rows = [f"First{index},Last{index}," for index in range(MAX_IMPORT_ROWS + 1)]
    response = _upload(
        as_alpha_admin,
        slug="leads",
        body=_csv("First name,Last name,Email", *rows),
        mapping=LEAD_MAPPING,
        dry_run=True,
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "import_too_large"


def test_a_utf8_bom_is_tolerated(as_alpha_admin: ApiSession) -> None:
    """Excel writes one back out, so a re-uploaded export must still parse."""
    body = "﻿".encode() + _leads_csv("Ada,Lovelace,ada@example.com")

    result = _upload(
        as_alpha_admin, slug="leads", body=body, mapping=LEAD_MAPPING, dry_run=True
    ).json()

    assert result["summary"]["created"] == 1


def test_a_formula_in_a_cell_is_stored_as_text(as_alpha_admin: ApiSession) -> None:
    """Import must not execute anything, and must not mangle the value either."""
    hostile = "=HYPERLINK(1)"
    result = _upload(
        as_alpha_admin,
        slug="accounts",
        body=_csv("Name,Industry", f'"{hostile}",Logistics'),
        mapping=ACCOUNT_MAPPING,
        dry_run=False,
    ).json()

    assert result["summary"]["created"] == 1
    assert as_alpha_admin.get("/crm/accounts").json()["data"][0]["name"] == hostile


# --- Round trip -------------------------------------------------------------


def test_an_export_can_be_imported_back(as_alpha_admin: ApiSession) -> None:
    """Journey E end to end: the two halves have to agree on a dialect."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Round Trip Ltd", "industry": "Freight"})
    exported = as_alpha_admin.get("/crm/accounts/export")
    assert exported.status_code == 200

    result = _upload(
        as_alpha_admin,
        slug="accounts",
        body=exported.content,
        mapping={"name": "name", "industry": "industry"},
        dry_run=True,
        duplicate_policy="SKIP",
    ).json()

    # The one row is recognised as a duplicate of itself, which is the correct
    # answer and proves the file parsed and the values matched.
    assert result["summary"]["total_rows"] == 1
    assert result["summary"]["skipped_duplicates"] == 1


def test_an_unknown_uuid_reference_fails_that_row_only(as_alpha_admin: ApiSession) -> None:
    """A foreign key to nothing is a row error, not a 500."""
    body = _csv(
        "First name,Last name,Account",
        f"Ada,Lovelace,{uuid.uuid4()}",
        "Alan,Turing,",
    )

    result = _upload(
        as_alpha_admin,
        slug="contacts",
        body=body,
        mapping={"First name": "first_name", "Last name": "last_name", "Account": "account_id"},
        dry_run=False,
    ).json()

    assert result["summary"]["created"] == 1
    assert result["summary"]["failed"] == 1
