"""The built-in report library.

Real PostgreSQL, real RLS, every assertion through HTTP. Grouped by the
question each set answers:

**Is an aggregate narrowed the way a list is.** This is the point of the
module and the thing that could most easily be wrong in the dangerous
direction. A report is a number, and a number computed over rows the caller
cannot open is a disclosure no later 404 can take back — a rep who cannot see
their colleagues' deals must not learn what those deals are worth by opening
a chart. So the same rep-versus-manager comparison the record-visibility
suite makes for lists is made here for totals.

**Is it authorized at all**, given there is no ``reports`` permission module:
each report declares the module it reads and the route must enforce
``<module>.VIEW`` against *that*, for a caller who holds some CRM permissions
but not that one.

**Does the catalogue tell the truth** — it lists what the caller can run, not
everything that exists.

**Does the tenant boundary hold**, which for an aggregate means one
organization's rows never reach another's total.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from tests.integration.conftest import (
    ApiSession,
    Tenant,
    grant_custom_role,
    membership_id_for,
)

pytestmark = pytest.mark.integration

REPORTS = "/crm/reports"


# --- Helpers ----------------------------------------------------------------


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """Alpha's plain ``User``: no ``VIEW_ALL``, so owner-scoped reads narrow."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def manager(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """Alpha's ``Manager``: holds ``VIEW_ALL`` across the CRM modules."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.manager.email, organization_id=alpha.organization_id)
    return session


def _stage_id(session: ApiSession, name: str = "Qualification") -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


def _account(session: ApiSession, name: str) -> str:
    created = session.post("/crm/accounts", json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _deal(session: ApiSession, *, name: str, account_id: str, value: str) -> str:
    created = session.post(
        "/crm/opportunities",
        json={
            "name": name,
            "account_id": account_id,
            "stage_id": _stage_id(session),
            "deal_value": value,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _run(session: ApiSession, key: str, **params: Any) -> dict[str, Any]:
    response = session.post(f"{REPORTS}/{key}/run", json=params or {})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _row(result: dict[str, Any], column: str, value: Any) -> dict[str, Any]:
    """The one row whose ``column`` equals ``value``."""
    matches = [row for row in result["rows"] if row[column] == value]
    assert len(matches) == 1, f"expected one row with {column}={value!r}, got {matches}"
    return matches[0]


async def _only_permissions(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    codes: list[str],
    name: str,
) -> None:
    """Give a membership exactly ``codes`` and nothing else.

    ``grant_custom_role`` *adds* a role, which is what the export tests want:
    they need a combination the shipped roles do not offer. These tests need
    the opposite — a caller who holds one module's ``VIEW`` and demonstrably
    not another's — and the seeded ``User`` template grants ``VIEW`` on every
    CRM module. Left in place it makes the custom role a superset and the
    assertion vacuous, so the system grant is removed first.

    ``clean_database`` empties ``membership_roles`` between tests, so nothing
    here leaks into the next one.
    """
    async with session_factory() as session:
        await session.execute(
            sql("DELETE FROM platform.membership_roles WHERE membership_id = :membership"),
            {"membership": membership_id},
        )
        await session.commit()

    await grant_custom_role(
        session_factory,
        organization_id=organization_id,
        membership_id=membership_id,
        codes=codes,
        name=name,
    )


# --- The catalogue ----------------------------------------------------------


def test_the_catalogue_describes_the_built_in_reports(as_alpha_admin: ApiSession) -> None:
    listed = as_alpha_admin.get(REPORTS)

    assert listed.status_code == 200, listed.text
    reports = listed.json()
    keys = {report["key"] for report in reports}
    assert "pipeline-by-stage" in keys
    assert "lead-funnel" in keys

    pipeline = next(r for r in reports if r["key"] == "pipeline-by-stage")
    assert pipeline["module"] == "opportunities"
    assert pipeline["chart"] == {
        "kind": "BAR",
        "category_key": "stage",
        "value_key": "value",
    }
    assert pipeline["accepts_date_range"] is False


async def test_the_catalogue_lists_only_reports_the_caller_may_run(
    session_factory: async_sessionmaker[AsyncSession],
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    """A menu of locked doors is worse than a short menu.

    The custom role below holds ``leads.VIEW`` and nothing else, so exactly
    the lead reports should be offered — and the opportunity ones, which it
    could not run, should not appear.
    """
    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await _only_permissions(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=["leads.VIEW"],
        name="Leads only",
    )

    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)

    offered = {report["key"] for report in session.get(REPORTS).json()}

    assert offered == {"lead-funnel", "lead-conversion-by-source"}


# --- Authorization ----------------------------------------------------------


async def test_a_report_requires_view_on_the_module_it_reads(
    session_factory: async_sessionmaker[AsyncSession],
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    """There is no ``reports`` permission; the module's own ``VIEW`` is it."""
    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await _only_permissions(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=["leads.VIEW"],
        name="Leads only",
    )
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)

    permitted = session.post(f"{REPORTS}/lead-funnel/run", json={})
    refused = session.post(f"{REPORTS}/pipeline-by-stage/run", json={})

    assert permitted.status_code == 200, permitted.text
    assert refused.status_code == 403


def test_an_unknown_report_is_404(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(f"{REPORTS}/no-such-report/run", json={})

    assert response.status_code == 404


def test_reports_require_authentication(
    client: TestClient, integration_settings: Settings
) -> None:
    assert client.get(f"{integration_settings.api_prefix}{REPORTS}").status_code == 401


# --- Record-level visibility (the gate) -------------------------------------


def test_a_rep_and_a_manager_see_different_pipeline_totals(
    rep: ApiSession, manager: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """The phase gate.

    Three deals, one owned by the rep and two by the administrator. The
    manager holds ``opportunities.VIEW_ALL`` and must see all three; the rep
    holds only ``VIEW`` and must see the one they own — in the *count*, in the
    *value*, and in the totals row, because a report that narrowed its rows
    but not its sum would leak the number while hiding the deals.
    """
    rep_account = _account(rep, "Rep Ltd")
    admin_account = _account(as_alpha_admin, "Admin Ltd")
    _deal(rep, name="Rep deal", account_id=rep_account, value="1000.00")
    _deal(as_alpha_admin, name="Admin deal one", account_id=admin_account, value="4000.00")
    _deal(as_alpha_admin, name="Admin deal two", account_id=admin_account, value="5000.00")

    as_rep = _run(rep, "pipeline-by-stage")
    as_manager = _run(manager, "pipeline-by-stage")

    rep_stage = _row(as_rep, "stage", "Qualification")
    manager_stage = _row(as_manager, "stage", "Qualification")

    assert rep_stage["deals"] == 1
    assert float(rep_stage["value"]) == 1000.0
    assert manager_stage["deals"] == 3
    assert float(manager_stage["value"]) == 10000.0

    assert as_rep["totals"]["deals"] == 1
    assert float(as_rep["totals"]["value"]) == 1000.0
    assert as_manager["totals"]["deals"] == 3
    assert float(as_manager["totals"]["value"]) == 10000.0


def test_every_configured_stage_appears_even_with_no_visible_deals(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """An empty column is information; a missing one reads as misconfiguration."""
    account = _account(as_alpha_admin, "Admin Ltd")
    _deal(as_alpha_admin, name="Not the rep's", account_id=account, value="2500.00")

    result = _run(rep, "pipeline-by-stage")

    assert len(result["rows"]) > 1, "the seeded pipeline has several open stages"
    assert all(row["deals"] == 0 for row in result["rows"])
    assert result["totals"]["deals"] == 0


def test_an_organization_wide_report_is_not_owner_narrowed(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """``activities`` is deliberately absent from ``OWNER_SCOPED_MODULES``.

    An activity belongs to the record it is logged against rather than to its
    own owner, so a shared history must not fragment per viewer. The report
    follows that rule rather than inventing a stricter one of its own.
    """
    logged = as_alpha_admin.post(
        "/crm/activities",
        json={"type": "CALL", "subject": "Admin's call", "status": "COMPLETED"},
    )
    assert logged.status_code == 201, logged.text

    result = _run(rep, "activity-by-owner")

    assert sum(row["activities"] for row in result["rows"]) == 1


# --- Tenant isolation -------------------------------------------------------


def test_one_organizations_records_never_reach_anothers_totals(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    account = _account(as_alpha_admin, "Alpha Ltd")
    _deal(as_alpha_admin, name="Alpha deal", account_id=account, value="7500.00")

    as_beta_admin = ApiSession(client, integration_settings.api_prefix)
    as_beta_admin.login(beta.admin.email, organization_id=beta.organization_id)

    alpha_result = _run(as_alpha_admin, "pipeline-by-stage")
    beta_result = _run(as_beta_admin, "pipeline-by-stage")

    assert float(alpha_result["totals"]["value"]) == 7500.0
    assert float(beta_result["totals"]["value"]) == 0.0


# --- Shaping ----------------------------------------------------------------


def test_owner_columns_resolve_to_people_not_identifiers(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """A report grouped by owner that printed UUIDs would not be a report."""
    created = as_alpha_admin.post(
        "/crm/tasks",
        json={
            "title": "Overdue thing",
            "due_date": "2020-01-01T09:00:00Z",
            "assigned_to_id": str(alpha.admin.user_id),
        },
    )
    assert created.status_code == 201, created.text

    result = _run(as_alpha_admin, "overdue-tasks")

    assert len(result["rows"]) == 1
    owner = result["rows"][0]["owner_id"]
    assert owner != str(alpha.admin.user_id), "the raw id must never reach the client"
    assert owner == f"Admin {alpha.slug.title()}"


def test_an_unassigned_row_is_labelled_rather_than_dropped(
    as_alpha_admin: ApiSession,
) -> None:
    """Rows with no owner still count, or the totals stop reconciling."""
    created = as_alpha_admin.post(
        "/crm/tasks",
        json={"title": "Nobody's task", "due_date": "2020-01-01T09:00:00Z"},
    )
    assert created.status_code == 201, created.text

    result = _run(as_alpha_admin, "overdue-tasks")

    assert result["totals"]["overdue"] == 1


def test_the_lead_funnel_is_zero_filled_and_ordered(as_alpha_admin: ApiSession) -> None:
    """The sequence carries the meaning, so every stage is always present."""
    created = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Funnel", "last_name": "Lead"}
    )
    assert created.status_code == 201, created.text

    result = _run(as_alpha_admin, "lead-funnel")

    statuses = [row["status"] for row in result["rows"]]
    assert statuses == [
        "NEW",
        "CONTACTED",
        "QUALIFIED",
        "PROPOSAL_SENT",
        "NEGOTIATION",
        "CONVERTED",
    ]
    assert _row(result, "status", "NEW")["leads"] == 1
    assert _row(result, "status", "QUALIFIED")["leads"] == 0


def test_won_and_lost_are_both_reported_even_when_one_is_empty(
    as_alpha_admin: ApiSession,
) -> None:
    """"Nothing lost this quarter" must look different from "it did not run"."""
    result = _run(as_alpha_admin, "won-lost-summary")

    assert [row["outcome"] for row in result["rows"]] == ["Won", "Lost"]
    assert all(row["deals"] == 0 for row in result["rows"])


def test_a_date_range_narrows_a_report_that_accepts_one(
    as_alpha_admin: ApiSession,
) -> None:
    account = _account(as_alpha_admin, "Timing Ltd")
    created = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Closes next year",
            "account_id": account,
            "stage_id": _stage_id(as_alpha_admin),
            "deal_value": "3000.00",
            "expected_close_date": "2027-06-01",
        },
    )
    assert created.status_code == 201, created.text

    inside = _run(as_alpha_admin, "deals-closing", date_from="2027-01-01", date_to="2027-12-31")
    outside = _run(as_alpha_admin, "deals-closing", date_from="2026-01-01", date_to="2026-12-31")

    assert len(inside["rows"]) == 1
    assert inside["date_from"] == "2027-01-01"
    assert outside["rows"] == []


def test_a_date_range_is_ignored_by_a_report_that_does_not_take_one(
    as_alpha_admin: ApiSession,
) -> None:
    """The same saved period may be replayed against several reports.

    Refusing one of them for carrying a field it has no use for would be the
    less useful behaviour, so the window is dropped and the response says so
    by reporting no dates back.
    """
    created = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Ignored", "last_name": "Window"}
    )
    assert created.status_code == 201, created.text

    result = _run(as_alpha_admin, "lead-funnel", date_from="1999-01-01", date_to="1999-12-31")

    assert result["date_from"] is None
    assert _row(result, "status", "NEW")["leads"] == 1


def test_an_inverted_date_range_is_refused(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        f"{REPORTS}/deals-closing/run",
        json={"date_from": "2027-12-31", "date_to": "2027-01-01"},
    )

    assert response.status_code == 422


def test_conversion_rate_is_reported_per_source(as_alpha_admin: ApiSession) -> None:
    source = as_alpha_admin.post("/crm/lead-sources", json={"name": "Webinar"})
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]

    for index in range(2):
        created = as_alpha_admin.post(
            "/crm/leads",
            json={
                "first_name": f"Lead{index}",
                "last_name": "Webinar",
                "lead_source_id": source_id,
            },
        )
        assert created.status_code == 201, created.text

    result = _run(as_alpha_admin, "lead-conversion-by-source")

    webinar = _row(result, "source", "Webinar")
    assert webinar["leads"] == 2
    assert webinar["converted"] == 0
    assert webinar["conversion_rate"] == 0.0


def test_leads_with_no_source_are_reported_rather_than_dropped(
    as_alpha_admin: ApiSession,
) -> None:
    created = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "No", "last_name": "Source"}
    )
    assert created.status_code == 201, created.text

    result = _run(as_alpha_admin, "lead-conversion-by-source")

    assert _row(result, "source", "Unattributed")["leads"] == 1


def test_accounts_are_grouped_by_industry_with_their_open_pipeline(
    as_alpha_admin: ApiSession,
) -> None:
    """Two coalesced group-bys exist in this module; both are exercised.

    The other one — lead source — was where a bound literal in ``GROUP BY``
    first failed against PostgreSQL, and an untested twin of a query that has
    already been wrong once is a defect waiting for a demo.
    """
    created = as_alpha_admin.post(
        "/crm/accounts", json={"name": "Acme Manufacturing", "industry": "Manufacturing"}
    )
    assert created.status_code == 201, created.text
    _deal(
        as_alpha_admin,
        name="Plant upgrade",
        account_id=str(created.json()["id"]),
        value="12000.00",
    )
    unspecified = as_alpha_admin.post("/crm/accounts", json={"name": "No Industry Ltd"})
    assert unspecified.status_code == 201, unspecified.text

    result = _run(as_alpha_admin, "accounts-by-industry")

    manufacturing = _row(result, "industry", "Manufacturing")
    assert manufacturing["accounts"] == 1
    assert float(manufacturing["open_pipeline"]) == 12000.0
    assert _row(result, "industry", "Unspecified")["accounts"] == 1
    assert result["totals"]["accounts"] == 2


def test_a_result_describes_its_own_columns(as_alpha_admin: ApiSession) -> None:
    """The frontend renders any report, including ones added later, from this."""
    result = _run(as_alpha_admin, "pipeline-by-stage")

    assert result["columns"] == [
        {"key": "stage", "label": "Stage", "type": "TEXT"},
        {"key": "deals", "label": "Deals", "type": "NUMBER"},
        {"key": "value", "label": "Value", "type": "CURRENCY"},
    ]
    assert result["row_limit_reached"] is False
    assert dt.datetime.fromisoformat(result["generated_at"]) is not None


def test_every_report_declares_a_column_for_every_field_it_returns(
    as_alpha_admin: ApiSession,
) -> None:
    """A row key with no column is data the screen can never show.

    The frontend renders strictly from ``columns``, so an undeclared field is
    invisible — and the way that surfaces is a reviewer wondering why a value
    plainly present in the JSON never appears on the page. Asserted across the
    whole catalogue rather than per report, because the mistake is an easy one
    to repeat the next time a query grows a field.
    """
    account_id = _account(as_alpha_admin, "Column Contract Ltd")
    deal_id = _deal(
        as_alpha_admin,
        name="Closing soon",
        account_id=account_id,
        value="9000.00",
    )
    dated = as_alpha_admin.patch(
        f"/crm/opportunities/{deal_id}",
        json={"expected_close_date": "2030-06-01"},
    )
    assert dated.status_code == 200, dated.text

    catalogue = as_alpha_admin.get(REPORTS).json()
    assert catalogue, "the seeded administrator should be offered reports"

    for summary in catalogue:
        result = _run(as_alpha_admin, summary["key"])
        declared = {column["key"] for column in result["columns"]}
        for row in result["rows"]:
            assert set(row) <= declared, (
                f"{summary['key']} returns {sorted(set(row) - declared)}, "
                "which no column declares"
            )


def test_the_lead_funnel_reports_status_as_a_status_column(
    as_alpha_admin: ApiSession,
) -> None:
    """``STATUS`` tells the client to humanize; ``TEXT`` tells it not to.

    The distinction matters in both directions: a funnel step labelled
    ``PROPOSAL_SENT`` is unreadable, and an industry named "Food & Beverage"
    put through the same helper comes back as "Food & beverage".
    """
    result = _run(as_alpha_admin, "lead-funnel")
    assert {column["key"]: column["type"] for column in result["columns"]}[
        "status"
    ] == "STATUS"

    industries = _run(as_alpha_admin, "accounts-by-industry")
    assert {column["key"]: column["type"] for column in industries["columns"]}[
        "industry"
    ] == "TEXT"
