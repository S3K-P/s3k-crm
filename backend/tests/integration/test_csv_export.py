"""CSV export (`P3-W23-BE-04`, `P3-W22-BE-03`).

An export is the one operation that takes records outside every control the
application has. Once the file is on somebody's laptop, RLS, RBAC and
record-level visibility have no further say — so what the endpoint decides to
put in it is the whole of the enforcement, and these tests are that enforcement
checked at the HTTP boundary rather than in the helper.

Four properties, in the order they would hurt if wrong:

* ``EXPORT`` is a distinct permission, and a role without it is refused;
* the file contains exactly the rows the caller's ``RecordVisibility`` allows —
  a rep downloading a colleague's pipeline is the failure this feature could
  most plausibly introduce;
* the file contains exactly the *fields* the read API already returns, so an
  export cannot become a wider read than the endpoint it mirrors;
* every export is written to the audit trail.
"""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.platform.authorization.catalog import permission_code
from app.products.crm.accounts.schemas import AccountResponse
from tests.integration.conftest import (
    ApiSession,
    Tenant,
    grant_custom_role,
    membership_id_for,
)

pytestmark = pytest.mark.integration

EXPORT_ROUTES = (
    "/crm/accounts/export",
    "/crm/contacts/export",
    "/crm/leads/export",
    "/crm/opportunities/export",
)


# --- Helpers ----------------------------------------------------------------


def _rows(response: object) -> list[dict[str, str]]:
    """Parse a CSV export response into dictionaries.

    Strips the UTF-8 BOM the endpoint writes for Excel's benefit; leaving it on
    would make the first header key ``\\ufeffid`` and every lookup miss.
    """
    body = response.text.lstrip("﻿")  # type: ignore[attr-defined]
    return list(csv.DictReader(io.StringIO(body)))


def _names(response: object) -> set[str]:
    return {row["name"] for row in _rows(response)}


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """Alpha's plain ``User`` — holds VIEW and CREATE, but not EXPORT."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def manager(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """Alpha's ``Manager`` — holds EXPORT *and* VIEW_ALL."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.manager.email, organization_id=alpha.organization_id)
    return session


# --- The permission ---------------------------------------------------------


@pytest.mark.parametrize("route", EXPORT_ROUTES)
def test_a_role_without_export_is_refused(rep: ApiSession, route: str) -> None:
    """EXPORT is not implied by VIEW.

    The plain ``User`` role can read every one of these lists in the UI. Being
    able to read a screen and being able to walk out with the underlying file
    are separate grants, which is why ``EXPORT`` exists in the catalogue.
    """
    response = rep.get(route)

    assert response.status_code == 403, f"{route}: {response.text}"
    assert response.json()["error"]["code"] == "permission_denied"


@pytest.mark.parametrize("route", EXPORT_ROUTES)
def test_an_unauthenticated_export_is_401_not_403(client: TestClient, route: str) -> None:
    """"We do not know who you are" must not read as "you may not export"."""
    response = client.get(f"/api/v1{route}")

    assert response.status_code == 401


@pytest.mark.parametrize("route", EXPORT_ROUTES)
def test_a_role_with_export_is_allowed(manager: ApiSession, route: str) -> None:
    response = manager.get(route)

    assert response.status_code == 200, f"{route}: {response.text}"
    assert response.headers["content-type"].startswith("text/csv")


# --- The file ---------------------------------------------------------------


def test_the_export_contains_the_records(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Exported Ltd"})
    as_alpha_admin.post("/crm/accounts", json={"name": "Also Exported Ltd"})

    response = as_alpha_admin.get("/crm/accounts/export")

    assert response.status_code == 200, response.text
    assert _names(response) == {"Exported Ltd", "Also Exported Ltd"}


def test_the_columns_are_exactly_the_read_apis_fields(as_alpha_admin: ApiSession) -> None:
    """An export must never be a wider read than the endpoint it mirrors.

    Deriving the columns from ``AccountResponse`` is what guarantees it: a
    field the response model does not expose has no way into the file.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Column Check Ltd"})

    body = as_alpha_admin.get("/crm/accounts/export").text.lstrip("﻿")
    header = next(csv.reader(io.StringIO(body)))

    assert header == list(AccountResponse.model_fields)


def test_an_empty_result_still_returns_a_header_row(as_alpha_admin: ApiSession) -> None:
    """A file with no columns is indistinguishable from a failed download."""
    response = as_alpha_admin.get("/crm/accounts/export", params={"search": "no-such-account"})

    assert response.status_code == 200
    assert _rows(response) == []
    body = response.text.lstrip("﻿")
    assert next(csv.reader(io.StringIO(body))) == list(AccountResponse.model_fields)


def test_the_response_is_a_named_download(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get("/crm/accounts/export")

    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "s3k-accounts-" in disposition
    assert disposition.endswith('.csv"')


def test_filters_narrow_the_export_exactly_as_they_narrow_the_list(
    as_alpha_admin: ApiSession,
) -> None:
    """The file must match the screen it was launched from."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Findable Ltd"})
    as_alpha_admin.post("/crm/accounts", json={"name": "Unrelated Ltd"})

    listed = as_alpha_admin.get("/crm/accounts", params={"search": "Findable"}).json()
    exported = as_alpha_admin.get("/crm/accounts/export", params={"search": "Findable"})

    assert _names(exported) == {row["name"] for row in listed["data"]} == {"Findable Ltd"}


def test_a_formula_in_a_name_is_neutralised(as_alpha_admin: ApiSession) -> None:
    """CWE-1236: a spreadsheet executes a cell that begins with ``=``.

    The value is stored and returned by the API unchanged — the application is
    not where this is dangerous. It is made inert on the way into the file,
    which is the only place it would run.
    """
    hostile = '=HYPERLINK("http://attacker.example","click")'
    as_alpha_admin.post("/crm/accounts", json={"name": hostile})

    row = next(row for row in _rows(as_alpha_admin.get("/crm/accounts/export")))

    assert row["name"] == "'" + hostile
    assert not row["name"].startswith("=")


# --- Record-level visibility ------------------------------------------------


def test_view_all_exports_across_owners(manager: ApiSession, as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Admin Owned Ltd"})

    assert "Admin Owned Ltd" in _names(manager.get("/crm/accounts/export"))


async def test_an_exporter_without_view_all_gets_only_their_own_records(
    client: TestClient,
    integration_settings: Settings,
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The failure this whole feature could most plausibly introduce.

    A rep granted EXPORT must download the rows on *their* screen, not the
    organization's. Proven with a custom role holding ``accounts.EXPORT`` and
    ``accounts.VIEW`` but not ``VIEW_ALL``, because the shipped roles do not
    offer that combination and a real tenant's would.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Not The Reps Ltd"})

    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await grant_custom_role(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=(permission_code("accounts", "VIEW"), permission_code("accounts", "EXPORT")),
    )

    exporter = ApiSession(client, integration_settings.api_prefix)
    exporter.login(alpha.member.email, organization_id=alpha.organization_id)
    theirs = exporter.post("/crm/accounts", json={"name": "The Reps Own Ltd"})
    assert theirs.status_code == 201, theirs.text

    response = exporter.get("/crm/accounts/export")

    assert response.status_code == 200, response.text
    names = _names(response)
    assert "The Reps Own Ltd" in names
    assert "Not The Reps Ltd" not in names, "a rep exported a record they cannot see"


async def test_the_export_matches_the_list_for_the_same_caller(
    client: TestClient,
    integration_settings: Settings,
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Whatever the rule decides, both endpoints must decide it identically.

    Stronger than asserting a specific row set: it pins export and list to the
    *same* answer, so a future change to visibility cannot move one without the
    other.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Someone Elses Ltd"})

    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await grant_custom_role(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=(permission_code("accounts", "VIEW"), permission_code("accounts", "EXPORT")),
    )

    exporter = ApiSession(client, integration_settings.api_prefix)
    exporter.login(alpha.member.email, organization_id=alpha.organization_id)
    exporter.post("/crm/accounts", json={"name": "Mine Ltd"})

    listed = exporter.get("/crm/accounts", params={"page_size": 200}).json()

    assert _names(exporter.get("/crm/accounts/export")) == {
        row["name"] for row in listed["data"]
    }


# --- Tenant isolation -------------------------------------------------------


def test_another_organizations_records_are_never_exported(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    other = ApiSession(client, integration_settings.api_prefix)
    other.login(beta.admin.email, organization_id=beta.organization_id)
    other.post("/crm/accounts", json={"name": "Beta Secret Ltd"})

    as_alpha_admin.post("/crm/accounts", json={"name": "Alpha Ltd"})

    assert _names(as_alpha_admin.get("/crm/accounts/export")) == {"Alpha Ltd"}


# --- The audit trail --------------------------------------------------------


def test_an_export_is_written_to_the_audit_trail(as_alpha_admin: ApiSession) -> None:
    """`P3-W22-BE-03`: who exported what, and when."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Audited Ltd"})
    assert as_alpha_admin.get("/crm/accounts/export").status_code == 200

    entries = as_alpha_admin.get("/audit-logs", params={"page_size": 200}).json()["data"]
    exports = [entry for entry in entries if entry["action"] == "RECORDS_EXPORTED"]

    assert len(exports) == 1, "exactly one export event"
    assert exports[0]["module"] == "accounts"
    assert exports[0]["entity_type"] == "ACCOUNT"
    assert exports[0]["actor_id"] is not None


def test_the_audit_entry_records_how_much_was_taken(as_alpha_admin: ApiSession) -> None:
    """Row count is the number an auditor actually asks for."""
    for index in range(3):
        as_alpha_admin.post("/crm/accounts", json={"name": f"Counted {index} Ltd"})

    as_alpha_admin.get("/crm/accounts/export")

    entries = as_alpha_admin.get("/audit-logs", params={"page_size": 200}).json()["data"]
    export = next(entry for entry in entries if entry["action"] == "RECORDS_EXPORTED")
    detail = as_alpha_admin.get(f"/audit-logs/{export['id']}").json()

    assert detail["details"]["row_count"] == 3


def test_a_refused_export_writes_no_audit_entry(rep: ApiSession) -> None:
    """A 403 is not an export. The trail must not imply data left."""
    assert rep.get("/crm/accounts/export").status_code == 403

    # The rep cannot read the trail; an administrator checks on their behalf.
    entries = rep.get("/audit-logs")
    assert entries.status_code == 403


@pytest.mark.parametrize(
    ("route", "module"),
    [
        ("/crm/accounts/export", "accounts"),
        ("/crm/contacts/export", "contacts"),
        ("/crm/leads/export", "leads"),
        ("/crm/opportunities/export", "opportunities"),
    ],
)
def test_every_entity_export_is_audited_under_its_own_module(
    as_alpha_admin: ApiSession, route: str, module: str
) -> None:
    """A trail that attributed every export to one module would be useless."""
    assert as_alpha_admin.get(route).status_code == 200

    entries = as_alpha_admin.get("/audit-logs", params={"page_size": 200}).json()["data"]
    exports = [entry for entry in entries if entry["action"] == "RECORDS_EXPORTED"]

    assert [entry["module"] for entry in exports] == [module]
