"""The dashboard summary endpoint.

A dashboard is the highest-risk read in a multi-tenant CRM: it aggregates
across every table at once, so a single missing ``organization_id`` filter
leaks a competitor's revenue as a headline number rather than as a row someone
has to go looking for. These tests therefore assert the aggregate arithmetic
*and* that it stays inside the tenant boundary.

Tasks, activities and meetings have no HTTP surface yet, so those rows are
seeded directly through the ORM. That is seeding, not verification: every
assertion still goes through the real API, with real authentication, real
membership verification and real RBAC.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.products.crm.activities.models import (
    Activity,
    ActivityStatus,
    ActivityType,
    Meeting,
    MeetingType,
)
from app.products.crm.common import CrmEntityType, Priority
from app.products.crm.tasks.models import Task, TaskStatus
from tests.integration.conftest import ApiSession, DualMember, Tenant, scope_session_to

pytestmark = pytest.mark.integration

SUMMARY = "/crm/dashboard/summary"


# --- Helpers ----------------------------------------------------------------


def _stage_id(session: ApiSession, name: str) -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


def _account(session: ApiSession, name: str) -> str:
    response = session.post("/crm/accounts", json={"name": name})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _opportunity(
    session: ApiSession, *, name: str, value: str, stage: str, currency: str | None = None
) -> str:
    payload: dict[str, object] = {
        "name": name,
        "account_id": _account(session, f"{name} Ltd"),
        "stage_id": _stage_id(session, stage),
        "deal_value": value,
    }
    if currency is not None:
        payload["currency"] = currency
    response = session.post("/crm/opportunities", json=payload)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _lead(session: ApiSession, *, company: str, qualified: bool = False) -> str:
    response = session.post(
        "/crm/leads",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company": company,
            "email": f"ada@{company.lower().replace(' ', '')}.example",
        },
    )
    assert response.status_code == 201, response.text
    lead_id = str(response.json()["id"])
    if qualified:
        for status in ("CONTACTED", "QUALIFIED"):
            moved = session.post(f"/crm/leads/{lead_id}/status", json={"status": status})
            assert moved.status_code == 200, moved.text
    return lead_id


async def _seed_task(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    title: str,
    due_date: dt.datetime | None,
    priority: Priority = Priority.MEDIUM,
    status: TaskStatus = TaskStatus.PENDING,
) -> Task:
    # The CRM tables are RLS-FORCEd; a session with no tenant scope
    # has its INSERT refused outright.
    await scope_session_to(session, organization_id)
    task = Task(
        organization_id=organization_id,
        title=title,
        due_date=due_date,
        priority=priority,
        status=status,
    )
    session.add(task)
    return task


async def _seed_meeting(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subject: str,
    start_time: dt.datetime,
    status: ActivityStatus = ActivityStatus.PLANNED,
    related: tuple[CrmEntityType, uuid.UUID] | None = None,
) -> Activity:
    # The CRM tables are RLS-FORCEd; a session with no tenant scope
    # has its INSERT refused outright.
    await scope_session_to(session, organization_id)
    activity = Activity(
        organization_id=organization_id,
        type=ActivityType.MEETING,
        subject=subject,
        status=status,
        due_date=start_time,
        related_entity_type=related[0] if related else None,
        related_entity_id=related[1] if related else None,
    )
    session.add(activity)
    await session.flush()
    session.add(
        Meeting(
            activity_id=activity.id,
            meeting_type=MeetingType.VIDEO,
            start_time=start_time,
            end_time=start_time + dt.timedelta(minutes=30),
        )
    )
    return activity


async def _seed_activity(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    subject: str,
    activity_type: ActivityType = ActivityType.CALL,
    completed_at: dt.datetime | None = None,
) -> Activity:
    # The CRM tables are RLS-FORCEd; a session with no tenant scope
    # has its INSERT refused outright.
    await scope_session_to(session, organization_id)
    activity = Activity(
        organization_id=organization_id,
        type=activity_type,
        subject=subject,
        status=ActivityStatus.COMPLETED if completed_at else ActivityStatus.PLANNED,
        completed_at=completed_at,
        outcome="Recorded",
    )
    session.add(activity)
    return activity


@pytest.fixture
def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --- Access control ---------------------------------------------------------


def test_the_dashboard_requires_authentication(
    client: TestClient, integration_settings: Settings
) -> None:
    """No token at all is 401 — never an anonymous, empty dashboard."""
    response = client.get(f"{integration_settings.api_prefix}{SUMMARY}")

    assert response.status_code == 401


def test_a_forged_bearer_token_is_rejected(
    client: TestClient, integration_settings: Settings
) -> None:
    response = client.get(
        f"{integration_settings.api_prefix}{SUMMARY}",
        headers={"Authorization": "Bearer not.a.real.token"},
    )

    assert response.status_code == 401


def test_a_member_with_no_role_assigned_is_denied(
    api: ApiSession, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """RBAC is enforced on the dashboard, not just on the record endpoints.

    Every system role grants ``dashboard.VIEW``, so the way to observe the
    check is to take the role away: a membership carrying no roles holds no
    permissions and must be refused.
    """
    members = as_alpha_admin.get("/organizations/current/members").json()["data"]
    membership_id = next(m["id"] for m in members if m["user_id"] == str(alpha.member.user_id))
    role_id = next(r["id"] for r in as_alpha_admin.get("/roles").json() if r["name"] == "User")

    revoked = as_alpha_admin.post(
        "/roles/assignments/revoke",
        json={"membership_id": membership_id, "role_id": role_id},
    )
    assert revoked.status_code == 204, revoked.text

    api.login(alpha.member.email, organization_id=alpha.organization_id)
    assert api.get(SUMMARY).status_code == 403


def test_every_system_role_may_read_the_dashboard(api: ApiSession, alpha: Tenant) -> None:
    for user in (alpha.admin, alpha.manager, alpha.member):
        api.login(user.email, organization_id=alpha.organization_id)
        assert api.get(SUMMARY).status_code == 200, user.role


# --- Empty state ------------------------------------------------------------


def test_an_organization_with_no_records_returns_a_real_empty_state(
    as_alpha_admin: ApiSession,
) -> None:
    """Zeros and empty lists — not an error, and not fabricated numbers."""
    body = as_alpha_admin.get(SUMMARY).json()

    assert body["kpis"] == {
        "new_leads": 0,
        "qualified_leads": 0,
        "open_opportunities": 0,
        "pipeline_value": "0",
        "meetings_today": 0,
        "tasks_due": 0,
        "tasks_due_high_priority": 0,
        "opportunities_closing_soon": 0,
    }
    assert body["tasks"] == []
    assert body["meetings"] == []
    assert body["activities"] == []
    assert Decimal(body["pipeline_total"]) == Decimal(0)


def test_configured_stages_appear_even_with_no_deals_in_them(
    as_alpha_admin: ApiSession,
) -> None:
    """An empty pipeline column is information; it must not vanish."""
    body = as_alpha_admin.get(SUMMARY).json()

    names = [stage["name"] for stage in body["pipeline"]]
    assert names, "the default pipeline should be reported"
    assert all(stage["count"] == 0 for stage in body["pipeline"])
    # Closed stages are not part of the open funnel.
    assert "Closed Won" not in names
    assert "Closed Lost" not in names
    # Reported in the organization's configured order.
    orders = [stage["sort_order"] for stage in body["pipeline"]]
    assert orders == sorted(orders)


# --- Real aggregation -------------------------------------------------------


def test_the_kpis_count_the_organizations_own_records(as_alpha_admin: ApiSession) -> None:
    _lead(as_alpha_admin, company="Northwind")
    _lead(as_alpha_admin, company="Contoso", qualified=True)
    _opportunity(as_alpha_admin, name="Deal A", value="50000.00", stage="Qualification")
    _opportunity(as_alpha_admin, name="Deal B", value="25000.50", stage="Proposal")

    kpis = as_alpha_admin.get(SUMMARY).json()["kpis"]

    assert kpis["new_leads"] == 2
    assert kpis["qualified_leads"] == 1
    assert kpis["open_opportunities"] == 2
    assert Decimal(kpis["pipeline_value"]) == Decimal("75000.50")


def test_the_pipeline_breakdown_matches_the_deals_in_each_stage(
    as_alpha_admin: ApiSession,
) -> None:
    _opportunity(as_alpha_admin, name="Deal A", value="50000.00", stage="Qualification")
    _opportunity(as_alpha_admin, name="Deal B", value="10000.00", stage="Qualification")
    _opportunity(as_alpha_admin, name="Deal C", value="25000.00", stage="Proposal")

    body = as_alpha_admin.get(SUMMARY).json()
    by_name = {stage["name"]: stage for stage in body["pipeline"]}

    assert by_name["Qualification"]["count"] == 2
    assert Decimal(by_name["Qualification"]["value"]) == Decimal("60000.00")
    assert by_name["Proposal"]["count"] == 1
    assert Decimal(body["pipeline_total"]) == Decimal("85000.00")


def test_the_total_is_denominated_when_every_open_deal_agrees(
    as_alpha_admin: ApiSession,
) -> None:
    _opportunity(
        as_alpha_admin, name="Deal A", value="50000.00", stage="Qualification", currency="EUR"
    )
    _opportunity(
        as_alpha_admin, name="Deal B", value="10000.00", stage="Proposal", currency="EUR"
    )

    assert as_alpha_admin.get(SUMMARY).json()["pipeline_currency"] == "EUR"


def test_a_mixed_currency_pipeline_reports_no_single_currency(
    as_alpha_admin: ApiSession,
) -> None:
    """Adding euros to dollars and stamping ``$`` on the result is a lie.

    The API declines to name a currency; the UI shows the bare figure and says
    the deals are mixed.
    """
    _opportunity(
        as_alpha_admin, name="Deal A", value="50000.00", stage="Qualification", currency="USD"
    )
    _opportunity(
        as_alpha_admin, name="Deal B", value="10000.00", stage="Proposal", currency="EUR"
    )

    assert as_alpha_admin.get(SUMMARY).json()["pipeline_currency"] is None


def test_a_won_deal_leaves_the_open_pipeline(as_alpha_admin: ApiSession) -> None:
    """Closing a deal must move the numbers, or the dashboard is stale."""
    opportunity_id = _opportunity(
        as_alpha_admin, name="Deal A", value="50000.00", stage="Qualification"
    )
    _opportunity(as_alpha_admin, name="Deal B", value="10000.00", stage="Qualification")

    won = as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage",
        json={"stage_id": _stage_id(as_alpha_admin, "Closed Won"), "win_reason": "Best fit"},
    )
    assert won.status_code == 200, won.text

    kpis = as_alpha_admin.get(SUMMARY).json()["kpis"]
    assert kpis["open_opportunities"] == 1
    assert Decimal(kpis["pipeline_value"]) == Decimal("10000.00")


def test_a_soft_deleted_record_stops_being_counted(as_alpha_admin: ApiSession) -> None:
    lead_id = _lead(as_alpha_admin, company="Northwind")
    assert as_alpha_admin.get(SUMMARY).json()["kpis"]["new_leads"] == 1

    assert as_alpha_admin.delete(f"/crm/leads/{lead_id}").status_code == 204

    assert as_alpha_admin.get(SUMMARY).json()["kpis"]["new_leads"] == 0


# --- Tasks, meetings and activity feed --------------------------------------


@pytest.mark.asyncio
async def test_open_tasks_are_listed_and_due_ones_counted(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    now: dt.datetime,
) -> None:
    async with session_factory() as session, session.begin():
        await _seed_task(
            session,
            organization_id=alpha.organization_id,
            title="Call Northwind",
            due_date=now - dt.timedelta(hours=2),
            priority=Priority.HIGH,
        )
        await _seed_task(
            session,
            organization_id=alpha.organization_id,
            title="Send proposal",
            due_date=now - dt.timedelta(days=1),
        )
        await _seed_task(
            session,
            organization_id=alpha.organization_id,
            title="Next month follow-up",
            due_date=now + dt.timedelta(days=20),
        )
        await _seed_task(
            session,
            organization_id=alpha.organization_id,
            title="Already handled",
            due_date=now - dt.timedelta(days=3),
            status=TaskStatus.COMPLETED,
        )

    body = as_alpha_admin.get(SUMMARY).json()

    # Due today or earlier, still open: two of the four.
    assert body["kpis"]["tasks_due"] == 2
    assert body["kpis"]["tasks_due_high_priority"] == 1
    titles = [task["title"] for task in body["tasks"]]
    assert "Already handled" not in titles
    assert titles[0] == "Send proposal", "soonest due date first"
    assert set(titles) == {"Send proposal", "Call Northwind", "Next month follow-up"}


@pytest.mark.asyncio
async def test_meetings_today_are_counted_and_upcoming_ones_listed(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    now: dt.datetime,
) -> None:
    end_of_day = dt.datetime.combine(now.date(), dt.time.max, tzinfo=dt.UTC)
    later_today = min(now + dt.timedelta(hours=1), end_of_day - dt.timedelta(seconds=1))

    async with session_factory() as session, session.begin():
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            subject="Discovery call",
            start_time=later_today,
        )
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            subject="Next week sync",
            start_time=now + dt.timedelta(days=7),
        )
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            subject="Cancelled review",
            start_time=later_today,
            status=ActivityStatus.CANCELLED,
        )

    body = as_alpha_admin.get(SUMMARY).json()

    assert body["kpis"]["meetings_today"] == 1, "a cancelled meeting is not a meeting"
    titles = [meeting["title"] for meeting in body["meetings"]]
    assert titles == ["Discovery call", "Next week sync"]
    assert body["meetings"][0]["end_time"] is not None


@pytest.mark.asyncio
async def test_the_activity_feed_is_newest_first(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    now: dt.datetime,
) -> None:
    async with session_factory() as session, session.begin():
        await _seed_activity(
            session,
            organization_id=alpha.organization_id,
            subject="Older call",
            completed_at=now - dt.timedelta(days=2),
        )
        await _seed_activity(
            session,
            organization_id=alpha.organization_id,
            subject="Recent email",
            activity_type=ActivityType.EMAIL,
            completed_at=now - dt.timedelta(hours=1),
        )

    activities = as_alpha_admin.get(SUMMARY).json()["activities"]

    assert [entry["subject"] for entry in activities] == ["Recent email", "Older call"]
    assert activities[0]["type"] == "EMAIL"


@pytest.mark.asyncio
async def test_a_planned_meeting_is_not_reported_as_recent_activity(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    now: dt.datetime,
) -> None:
    """"Recent" must mean happened, not entered.

    A meeting scheduled for next week is created *now*, so ordering the feed by
    creation time would put a future appointment at the top of a history panel
    and timestamp it "3 minutes ago".
    """
    async with session_factory() as session, session.begin():
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            subject="Next week sync",
            start_time=now + dt.timedelta(days=7),
        )
        await _seed_activity(
            session,
            organization_id=alpha.organization_id,
            subject="Call that happened",
            completed_at=now - dt.timedelta(hours=1),
        )

    body = as_alpha_admin.get(SUMMARY).json()

    assert [entry["subject"] for entry in body["activities"]] == ["Call that happened"]
    # It is still surfaced — as what it is.
    assert [meeting["title"] for meeting in body["meetings"]] == ["Next week sync"]


@pytest.mark.asyncio
async def test_a_related_record_from_another_tenant_is_not_named(
    session_factory: async_sessionmaker[AsyncSession],
    api: ApiSession,
    alpha: Tenant,
    beta: Tenant,
) -> None:
    """A dangling cross-tenant reference resolves to nothing, never to a name.

    The polymorphic ``related_entity_id`` has no foreign key, so nothing at the
    database level stops one pointing at another organization's row. The label
    lookup is organization-scoped precisely so that pointer cannot be used to
    read beta's account name out of alpha's dashboard.
    """
    api.login(beta.admin.email, organization_id=beta.organization_id)
    beta_account_id = uuid.UUID(_account(api, "Beta Secret Holdings"))

    async with session_factory() as session, session.begin():
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            subject="Meeting with a foreign reference",
            start_time=dt.datetime.now(dt.UTC) + dt.timedelta(hours=3),
            related=(CrmEntityType.ACCOUNT, beta_account_id),
        )

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    meetings = api.get(SUMMARY).json()["meetings"]

    assert len(meetings) == 1
    assert meetings[0]["related_label"] is None


# --- Tenant isolation -------------------------------------------------------


def test_one_tenants_records_never_reach_another_tenants_dashboard(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    _lead(api, company="Alpha Lead", qualified=True)
    _opportunity(api, name="Alpha Deal", value="900000.00", stage="Qualification")

    api.login(beta.admin.email, organization_id=beta.organization_id)
    body = api.get(SUMMARY).json()

    assert body["kpis"]["new_leads"] == 0
    assert body["kpis"]["qualified_leads"] == 0
    assert body["kpis"]["open_opportunities"] == 0
    assert Decimal(body["kpis"]["pipeline_value"]) == Decimal(0)
    assert all(stage["count"] == 0 for stage in body["pipeline"])


def test_the_same_user_sees_different_dashboards_per_organization(
    api: ApiSession, dual_member: DualMember, alpha: Tenant, beta: Tenant
) -> None:
    """Identical credentials, identical token — the organization decides.

    A single-organization user cannot distinguish "correctly scoped" from
    "not scoped at all". This one can.
    """
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    _opportunity(api, name="Alpha Deal", value="111000.00", stage="Qualification")

    api.login(beta.admin.email, organization_id=beta.organization_id)
    _opportunity(api, name="Beta Deal", value="222000.00", stage="Qualification")

    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)

    in_alpha = api.get(SUMMARY, organization_id=dual_member.alpha_organization_id).json()
    in_beta = api.get(SUMMARY, organization_id=dual_member.beta_organization_id).json()

    assert Decimal(in_alpha["kpis"]["pipeline_value"]) == Decimal("111000.00")
    assert Decimal(in_beta["kpis"]["pipeline_value"]) == Decimal("222000.00")


def test_a_manipulated_organization_header_is_refused(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """The header names a candidate tenant; membership decides the answer."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    _opportunity(api, name="Alpha Deal", value="900000.00", stage="Qualification")

    response = api.get(SUMMARY, organization_id=beta.organization_id)

    assert response.status_code == 403


def test_an_unknown_organization_header_is_refused(api: ApiSession, alpha: Tenant) -> None:
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    response = api.get(SUMMARY, organization_id=uuid.uuid4())

    assert response.status_code == 403
