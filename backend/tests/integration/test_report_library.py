"""Saved reports and report folders.

Real PostgreSQL, real RLS, every assertion through HTTP. Grouped by the
question each set answers:

**Does sharing leak numbers.** This is the one that matters. A saved report is
a stored *question*, and the answer is recomputed for whoever runs it — so a
manager can share a report with a rep and the rep still sees only their own
rows. If that were ever untrue, sharing would be a mechanism for handing out a
wider view than the permission system grants, and no other test here would
catch it.

**Is the object's lifecycle authorized separately from the data.** ``reports.*``
governs naming, filing and sharing; ``<module>.VIEW`` governs the rows. The
tests below hold one and not the other, in both directions.

**Does privacy hold.** A colleague's ``PRIVATE`` report must be absent from
lists, uncounted, and a 404 when asked for by id.

**Does the tenant boundary hold**, which here means a folder id from another
organization is a 404 rather than a foreign-key error.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.products.crm.reports.library import resolve_period
from app.products.crm.reports.models import ReportPeriod
from tests.integration.conftest import (
    ApiSession,
    Tenant,
    grant_custom_role,
    membership_id_for,
)

pytestmark = pytest.mark.integration

REPORTS = "/crm/reports"
FOLDERS = f"{REPORTS}/folders"
SAVED = f"{REPORTS}/saved"


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


async def _only_permissions(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    codes: list[str],
    name: str,
) -> None:
    """Give a membership exactly ``codes`` and nothing else.

    ``grant_custom_role`` *adds* a role, and the seeded ``User`` template
    already grants ``VIEW`` on every CRM module — left in place it would make
    every "holds one permission but not another" assertion below vacuous.
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


def _folder(session: ApiSession, name: str) -> str:
    created = session.post(FOLDERS, json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _save(
    session: ApiSession,
    *,
    name: str,
    key: str = "pipeline-by-stage",
    **extra: object,
) -> dict[str, object]:
    created = session.post(
        SAVED, json={"name": name, "base_report_key": key, **extra}
    )
    assert created.status_code == 201, created.text
    body: dict[str, object] = created.json()
    return body


def _account(session: ApiSession, name: str) -> str:
    created = session.post("/crm/accounts", json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _stage_id(session: ApiSession, name: str = "Qualification") -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


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


# --- Period resolution ------------------------------------------------------
#
# A unit-level concern, tested here rather than in tests/unit because the
# behaviour it protects — a saved report that keeps meaning what it said — is
# what the rest of this file is about.


def test_a_relative_period_moves_with_the_calendar() -> None:
    """The whole point of storing a period instead of two dates."""
    june = resolve_period(
        ReportPeriod.THIS_MONTH, date_from=None, date_to=None, today=dt.date(2026, 6, 15)
    )
    july = resolve_period(
        ReportPeriod.THIS_MONTH, date_from=None, date_to=None, today=dt.date(2026, 7, 15)
    )

    assert june == (dt.date(2026, 6, 1), dt.date(2026, 6, 30))
    assert july == (dt.date(2026, 7, 1), dt.date(2026, 7, 31))


def test_a_named_period_covers_the_whole_span_not_only_up_to_today() -> None:
    """Truncating at today would empty every forward-looking report.

    "This quarter's closing pipeline" must include deals due later this
    quarter; stopping at today would show only the ones already past due and
    call it the quarter.
    """
    start, end = resolve_period(
        ReportPeriod.THIS_QUARTER,
        date_from=None,
        date_to=None,
        today=dt.date(2026, 8, 3),
    )
    assert (start, end) == (dt.date(2026, 7, 1), dt.date(2026, 9, 30))


def test_a_trailing_window_includes_today() -> None:
    """Seven days means today and the six before it."""
    start, end = resolve_period(
        ReportPeriod.LAST_7_DAYS, date_from=None, date_to=None, today=dt.date(2026, 3, 10)
    )
    assert (start, end) == (dt.date(2026, 3, 4), dt.date(2026, 3, 10))


def test_last_quarter_wraps_the_year_boundary() -> None:
    """January's previous quarter is the last one of the year before."""
    start, end = resolve_period(
        ReportPeriod.LAST_QUARTER, date_from=None, date_to=None, today=dt.date(2026, 1, 20)
    )
    assert (start, end) == (dt.date(2025, 10, 1), dt.date(2025, 12, 31))


def test_a_custom_period_uses_the_stored_dates() -> None:
    resolved = resolve_period(
        ReportPeriod.CUSTOM,
        date_from=dt.date(2026, 2, 1),
        date_to=dt.date(2026, 2, 28),
        today=dt.date(2026, 9, 9),
    )
    assert resolved == (dt.date(2026, 2, 1), dt.date(2026, 2, 28))


# --- Folders ----------------------------------------------------------------


def test_a_folder_can_be_created_listed_and_renamed(as_alpha_admin: ApiSession) -> None:
    folder_id = _folder(as_alpha_admin, "Board pack")

    listed = as_alpha_admin.get(FOLDERS)
    assert listed.status_code == 200, listed.text
    assert [folder["name"] for folder in listed.json()["data"]] == ["Board pack"]

    renamed = as_alpha_admin.patch(
        f"{FOLDERS}/{folder_id}", json={"name": "Board pack 2027"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Board pack 2027"


def test_two_folders_cannot_share_a_name(as_alpha_admin: ApiSession) -> None:
    _folder(as_alpha_admin, "Sales")

    duplicate = as_alpha_admin.post(FOLDERS, json={"name": "Sales"})

    assert duplicate.status_code == 409, duplicate.text


def test_a_folder_holding_reports_is_not_deleted(as_alpha_admin: ApiSession) -> None:
    """Cascading would delete colleagues' work as a side effect of tidying."""
    folder_id = _folder(as_alpha_admin, "Quarterly")
    _save(as_alpha_admin, name="Q3 pipeline", folder_id=folder_id)

    refused = as_alpha_admin.delete(f"{FOLDERS}/{folder_id}")

    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "folder_not_empty"


def test_an_emptied_folder_can_then_be_deleted(as_alpha_admin: ApiSession) -> None:
    folder_id = _folder(as_alpha_admin, "Temporary")
    saved = _save(as_alpha_admin, name="Scratch", folder_id=folder_id)

    unfiled = as_alpha_admin.patch(f"{SAVED}/{saved['id']}", json={"folder_id": None})
    assert unfiled.status_code == 200, unfiled.text

    deleted = as_alpha_admin.delete(f"{FOLDERS}/{folder_id}")
    assert deleted.status_code == 204, deleted.text


def test_a_folder_from_another_organization_is_not_found(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    """A cross-tenant id must 404, not raise a foreign-key error."""
    other = ApiSession(client, integration_settings.api_prefix)
    other.login(beta.admin.email, organization_id=beta.organization_id)
    foreign_folder = _folder(other, "Beta's folder")

    refused = as_alpha_admin.post(
        SAVED,
        json={
            "name": "Cross tenant",
            "base_report_key": "pipeline-by-stage",
            "folder_id": foreign_folder,
        },
    )

    assert refused.status_code == 404, refused.text


# --- Saving -----------------------------------------------------------------


def test_a_saved_report_round_trips(as_alpha_admin: ApiSession) -> None:
    folder_id = _folder(as_alpha_admin, "Sales")
    saved = _save(
        as_alpha_admin,
        name="Pipeline this quarter",
        folder_id=folder_id,
        period="THIS_QUARTER",
        visibility="SHARED",
        description="What the team is working.",
    )

    fetched = as_alpha_admin.get(f"{SAVED}/{saved['id']}")

    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["name"] == "Pipeline this quarter"
    assert body["base_report_key"] == "pipeline-by-stage"
    assert body["folder_id"] == folder_id
    assert body["period"] == "THIS_QUARTER"
    assert body["visibility"] == "SHARED"


def test_a_report_defaults_to_private(as_alpha_admin: ApiSession) -> None:
    """A half-built report should not be broadcast the moment it is named."""
    saved = _save(as_alpha_admin, name="Draft")

    assert saved["visibility"] == "PRIVATE"


def test_an_unknown_catalogue_key_is_rejected(as_alpha_admin: ApiSession) -> None:
    refused = as_alpha_admin.post(
        SAVED, json={"name": "Nonsense", "base_report_key": "no-such-report"}
    )

    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "unknown_report"


def test_a_custom_period_without_dates_is_rejected(as_alpha_admin: ApiSession) -> None:
    """CUSTOM with no dates silently means ALL_TIME, which is a different thing."""
    refused = as_alpha_admin.post(
        SAVED,
        json={
            "name": "Ambiguous",
            "base_report_key": "deals-closing",
            "period": "CUSTOM",
        },
    )

    assert refused.status_code == 422, refused.text


def test_two_reports_cannot_share_a_name(as_alpha_admin: ApiSession) -> None:
    _save(as_alpha_admin, name="Pipeline")

    duplicate = as_alpha_admin.post(
        SAVED, json={"name": "Pipeline", "base_report_key": "lead-funnel"}
    )

    assert duplicate.status_code == 409, duplicate.text


def test_filtering_by_folder_and_by_unfiled(as_alpha_admin: ApiSession) -> None:
    folder_id = _folder(as_alpha_admin, "Filed")
    _save(as_alpha_admin, name="In the folder", folder_id=folder_id)
    _save(as_alpha_admin, name="Loose", key="lead-funnel")

    filed = as_alpha_admin.get(f"{SAVED}?folder_id={folder_id}")
    unfiled = as_alpha_admin.get(f"{SAVED}?unfiled=true")

    assert [item["name"] for item in filed.json()["data"]] == ["In the folder"]
    assert [item["name"] for item in unfiled.json()["data"]] == ["Loose"]


# --- Privacy ----------------------------------------------------------------


def test_a_colleagues_private_report_is_invisible(
    manager: ApiSession, rep: ApiSession
) -> None:
    """Absent from the list, uncounted, and 404 by id."""
    private = _save(manager, name="Manager's draft")

    listed = rep.get(SAVED)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == []
    assert listed.json()["pagination"]["total"] == 0

    fetched = rep.get(f"{SAVED}/{private['id']}")
    assert fetched.status_code == 404, fetched.text


def test_sharing_a_report_makes_it_visible_to_colleagues(
    manager: ApiSession, rep: ApiSession
) -> None:
    shared = _save(manager, name="Team pipeline", visibility="SHARED")

    listed = rep.get(SAVED)

    assert [item["id"] for item in listed.json()["data"]] == [shared["id"]]


def test_only_the_owner_may_edit_a_shared_report(
    manager: ApiSession, rep: ApiSession
) -> None:
    """Sharing invites colleagues to run it, not to rewrite it underneath them."""
    shared = _save(manager, name="Team pipeline", visibility="SHARED")

    refused = rep.patch(f"{SAVED}/{shared['id']}", json={"name": "Hijacked"})

    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "not_owner"


def test_only_the_owner_may_delete_a_shared_report(
    manager: ApiSession, rep: ApiSession
) -> None:
    shared = _save(manager, name="Team pipeline", visibility="SHARED")

    refused = rep.delete(f"{SAVED}/{shared['id']}")

    assert refused.status_code == 403, refused.text


def test_ownership_cannot_be_reassigned_through_a_patch(
    manager: ApiSession, rep: ApiSession, alpha: Tenant
) -> None:
    """Owner decides who may edit, so accepting it from the body would be a hole."""
    saved = _save(manager, name="Mine", visibility="SHARED")

    patched = manager.patch(
        f"{SAVED}/{saved['id']}", json={"owner_id": str(uuid.uuid4()), "name": "Still mine"}
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["owner_id"] == saved["owner_id"]
    assert patched.json()["name"] == "Still mine"


# --- Running ----------------------------------------------------------------


def test_an_explicit_null_clears_a_nullable_field_but_not_a_required_one(
    as_alpha_admin: ApiSession,
) -> None:
    """PATCH null means "clear it" — where clearing is a thing that exists.

    ``folder_id`` is nullable, and sending null is how a report is taken out
    of a folder. ``name`` and ``period`` are ``NOT NULL``, so the same gesture
    there is not a change anybody can want; it is ignored rather than passed
    to the database, which would answer with a 500.
    """
    folder_id = _folder(as_alpha_admin, "Filed")
    saved = _save(
        as_alpha_admin, name="Both at once", folder_id=folder_id, period="ALL_TIME"
    )

    patched = as_alpha_admin.patch(
        f"{SAVED}/{saved['id']}",
        json={"folder_id": None, "name": None, "period": None, "visibility": None},
    )

    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["folder_id"] is None
    assert body["name"] == "Both at once"
    assert body["period"] == "ALL_TIME"
    assert body["visibility"] == "PRIVATE"


def test_running_a_saved_report_returns_the_same_shape_as_an_ad_hoc_run(
    as_alpha_admin: ApiSession,
) -> None:
    saved = _save(as_alpha_admin, name="Pipeline")

    from_saved = as_alpha_admin.post(f"{SAVED}/{saved['id']}/run", json={})
    ad_hoc = as_alpha_admin.post(f"{REPORTS}/pipeline-by-stage/run", json={})

    assert from_saved.status_code == 200, from_saved.text
    assert from_saved.json()["columns"] == ad_hoc.json()["columns"]
    assert from_saved.json()["key"] == "pipeline-by-stage"


def test_a_shared_report_still_runs_as_whoever_opens_it(
    manager: ApiSession, rep: ApiSession, alpha: Tenant
) -> None:
    """The gate for this whole feature.

    The manager owns two deals and shares a pipeline report. The rep opens
    *the same saved report* and must see zero — the report carries the
    question, never the manager's answer. If this ever inverted, sharing would
    become a way to hand a rep a view the permission system denies them.
    """
    account_id = _account(manager, "Northwind Traders")
    _deal(manager, name="Managed deal one", account_id=account_id, value="40000.00")
    _deal(manager, name="Managed deal two", account_id=account_id, value="60000.00")

    shared = _save(manager, name="Team pipeline", visibility="SHARED")

    managers_view = manager.post(f"{SAVED}/{shared['id']}/run", json={})
    reps_view = rep.post(f"{SAVED}/{shared['id']}/run", json={})

    assert managers_view.status_code == 200, managers_view.text
    assert reps_view.status_code == 200, reps_view.text
    assert managers_view.json()["totals"]["deals"] == 2
    assert float(managers_view.json()["totals"]["value"]) == 100000.0
    assert reps_view.json()["totals"]["deals"] == 0
    assert float(reps_view.json()["totals"]["value"]) == 0.0


def test_a_saved_period_narrows_the_run(as_alpha_admin: ApiSession) -> None:
    """A stored period must actually reach the query."""
    account_id = _account(as_alpha_admin, "Contoso")
    deal_id = _deal(
        as_alpha_admin, name="Closing in 2031", account_id=account_id, value="5000.00"
    )
    dated = as_alpha_admin.patch(
        f"/crm/opportunities/{deal_id}", json={"expected_close_date": "2031-06-01"}
    )
    assert dated.status_code == 200, dated.text

    inside = _save(
        as_alpha_admin,
        name="Closing in 2031",
        key="deals-closing",
        period="CUSTOM",
        date_from="2031-01-01",
        date_to="2031-12-31",
    )
    outside = _save(
        as_alpha_admin,
        name="Closing in 2030",
        key="deals-closing",
        period="CUSTOM",
        date_from="2030-01-01",
        date_to="2030-12-31",
    )

    hit = as_alpha_admin.post(f"{SAVED}/{inside['id']}/run", json={})
    miss = as_alpha_admin.post(f"{SAVED}/{outside['id']}/run", json={})

    assert len(hit.json()["rows"]) == 1
    assert miss.json()["rows"] == []


# --- Authorization ----------------------------------------------------------


async def test_saving_is_allowed_without_permission_on_the_reports_own_module(
    session_factory: async_sessionmaker[AsyncSession],
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    """Writing down a question discloses nothing; running it is where VIEW bites.

    The caller below may manage the library and may not read opportunities.
    Saving the pipeline report succeeds — they have stored a name and a key —
    and running it is refused, which is the only step that would have returned
    a number.
    """
    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await _only_permissions(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=["reports.VIEW", "reports.CREATE"],
        name="Library only",
    )
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)

    saved = session.post(
        SAVED, json={"name": "Pipeline", "base_report_key": "pipeline-by-stage"}
    )
    assert saved.status_code == 201, saved.text

    refused = session.post(f"{SAVED}/{saved.json()['id']}/run", json={})
    assert refused.status_code == 403, refused.text


async def test_managing_the_library_needs_the_reports_module(
    session_factory: async_sessionmaker[AsyncSession],
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    """The mirror image: all the data, none of the library.

    A caller holding ``opportunities.VIEW`` can run the report ad hoc and
    still may not save one, because the two permissions govern different
    things.
    """
    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await _only_permissions(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=["opportunities.VIEW"],
        name="Data only",
    )
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)

    ran = session.post(f"{REPORTS}/pipeline-by-stage/run", json={})
    assert ran.status_code == 200, ran.text

    refused = session.post(
        SAVED, json={"name": "Pipeline", "base_report_key": "pipeline-by-stage"}
    )
    assert refused.status_code == 403, refused.text


# --- Tenant isolation -------------------------------------------------------


def test_one_organizations_saved_reports_never_reach_another(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    _save(as_alpha_admin, name="Alpha's report", visibility="SHARED")

    other = ApiSession(client, integration_settings.api_prefix)
    other.login(beta.admin.email, organization_id=beta.organization_id)
    listed = other.get(SAVED)

    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == []


# --- Audit ------------------------------------------------------------------


def test_saving_a_report_is_recorded_under_the_reports_module(
    as_alpha_admin: ApiSession,
) -> None:
    """Filed under ``reports``, not under the ``saved_reports`` table name.

    The base class derives the audit module from the table, which would put
    these entries under a module that does not exist in the permission
    vocabulary and make the trail unfilterable.
    """
    _save(as_alpha_admin, name="Audited report")

    entries = as_alpha_admin.get("/audit-logs?module=reports")

    assert entries.status_code == 200, entries.text
    actions = {entry["action"] for entry in entries.json()["data"]}
    assert "CREATED" in actions
