"""Notifications: the recipient's own inbox, and the reminder scheduler.

Real PostgreSQL, real RLS — matching every other integration test in this
suite. Grouped by the question each set answers:

**Is a notification actually private to its recipient**, which has no RLS
backstop of its own (a notification's tenant and its intended reader are
different questions — see ``repository.py``). ``dual_member`` — the same
credentials, active in both organizations — is what proves the *tenant* half
is enforced by the database rather than by the query the router happens to
send: reading as beta must return nothing for a notification recorded under
alpha, even though the recipient id is identical.

**Does dispatching due reminders do the right thing**: a meeting inside its
own reminder window is reported, one outside it is not, firing twice for the
same due meeting produces one notification (not two), and one organization's
due reminders never reach another's inbox.

Activities, meetings and tasks have no HTTP surface exercised here beyond
what already has coverage elsewhere (``test_dashboard.py`` seeds them the
same way, for the same reason: "seeding, not verification" — every assertion
below still goes through the real API, with real authentication and real
membership verification, or through
``dispatch_due_reminders_for_all_organizations`` exactly as the production
scheduler calls it).
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.models import TENANT_SETTING
from app.platform.notifications.models import Notification
from app.platform.notifications.service import (
    dispatch_due_reminders_for_all_organizations,
    notifications_for_session,
)
from app.products.crm.activities.models import Activity, ActivityStatus, ActivityType, Meeting
from app.products.crm.tasks.models import Task, TaskStatus
from tests.integration.conftest import (
    ApiSession,
    DualMember,
    SeededUser,
    Tenant,
    scope_session_to,
)

pytestmark = pytest.mark.integration

NOTIFICATIONS = "/notifications"


def _session_as(
    client: TestClient, settings: Settings, user: SeededUser, *, organization_id: uuid.UUID
) -> ApiSession:
    """A second, independently signed-in session — the ``api`` fixture's own
    recipe, repeated where a test needs more than one signed-in user at once.
    """
    session = ApiSession(client, settings.api_prefix)
    session.login(user.email, organization_id=organization_id)
    return session


# --- Seeding helpers ---------------------------------------------------------


async def _seed_meeting(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    subject: str,
    start_time: dt.datetime,
    reminder_minutes: int | None,
    status: ActivityStatus = ActivityStatus.PLANNED,
) -> Activity:
    # The CRM tables are RLS-FORCEd; a session with no tenant scope has its
    # INSERT refused outright — see conftest.scope_session_to.
    await scope_session_to(session, organization_id)
    activity = Activity(
        organization_id=organization_id,
        type=ActivityType.MEETING,
        subject=subject,
        status=status,
        owner_id=owner_id,
        due_date=start_time,
    )
    session.add(activity)
    await session.flush()
    session.add(
        Meeting(
            activity_id=activity.id,
            meeting_type="VIDEO",
            start_time=start_time,
            end_time=start_time + dt.timedelta(minutes=30),
            reminder_minutes=reminder_minutes,
        )
    )
    return activity


async def _seed_task(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    title: str,
    due_date: dt.datetime | None,
    assigned_to_id: uuid.UUID,
    status: TaskStatus = TaskStatus.PENDING,
) -> Task:
    await scope_session_to(session, organization_id)
    task = Task(
        organization_id=organization_id,
        title=title,
        due_date=due_date,
        assigned_to_id=assigned_to_id,
        status=status,
    )
    session.add(task)
    return task


@pytest.fixture
def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --- The recipient's own inbox -----------------------------------------------


async def test_notify_is_readable_by_its_recipient_and_marks_read(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
) -> None:
    async with session_factory() as session, session.begin():
        # notify() writes into an RLS-FORCEd table exactly like every CRM
        # write; a bare seeding session needs the tenant scope a real request
        # gets for free — see conftest.scope_session_to.
        await scope_session_to(session, alpha.organization_id)
        notification = await notifications_for_session(session).notify(
            organization_id=alpha.organization_id,
            recipient_user_id=alpha.admin.user_id,
            kind="RECORD_ASSIGNED",
            title="A lead was assigned to you",
            entity_type="lead",
            entity_id=uuid.uuid4(),
        )
        notification_id = str(notification.id)

    listed = as_alpha_admin.get(NOTIFICATIONS)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == notification_id
    assert body["data"][0]["title"] == "A lead was assigned to you"
    assert body["data"][0]["read_at"] is None

    unread = as_alpha_admin.get(f"{NOTIFICATIONS}/unread-count")
    assert unread.json()["unread_count"] == 1

    marked = as_alpha_admin.post(f"{NOTIFICATIONS}/{notification_id}/read")
    assert marked.status_code == 200, marked.text
    assert marked.json()["read_at"] is not None

    unread_after = as_alpha_admin.get(f"{NOTIFICATIONS}/unread-count")
    assert unread_after.json()["unread_count"] == 0

    # Idempotent: marking an already-read notification read again is not an
    # error, and does not move the read timestamp backwards to "now".
    marked_again = as_alpha_admin.post(f"{NOTIFICATIONS}/{notification_id}/read")
    assert marked_again.status_code == 200
    assert marked_again.json()["read_at"] == marked.json()["read_at"]


async def test_mark_all_read_marks_only_the_callers_own_unread_notifications(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    client: TestClient,
    integration_settings: Settings,
) -> None:
    async with session_factory() as session, session.begin():
        await scope_session_to(session, alpha.organization_id)
        service = notifications_for_session(session)
        for index in range(3):
            await service.notify(
                organization_id=alpha.organization_id,
                recipient_user_id=alpha.admin.user_id,
                kind="RECORD_ASSIGNED",
                title=f"Notification {index}",
            )
        # A different recipient's unread notification must be untouched.
        await service.notify(
            organization_id=alpha.organization_id,
            recipient_user_id=alpha.member.user_id,
            kind="RECORD_ASSIGNED",
            title="Someone else's notification",
        )

    response = as_alpha_admin.post(f"{NOTIFICATIONS}/read-all")
    assert response.status_code == 200
    assert response.json()["unread_count"] == 3
    assert as_alpha_admin.get(f"{NOTIFICATIONS}/unread-count").json()["unread_count"] == 0

    as_alpha_member = _session_as(
        client, integration_settings, alpha.member, organization_id=alpha.organization_id
    )
    assert as_alpha_member.get(f"{NOTIFICATIONS}/unread-count").json()["unread_count"] == 1


async def test_marking_someone_elses_notification_read_returns_404(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
) -> None:
    """Recipient scoping, not just tenant scoping.

    Same organization, different intended reader: an admin must not be able
    to mark a colleague's notification read merely by knowing its id. This is
    the one guarantee RLS does not provide — see repository.py — so it is
    asserted here explicitly rather than assumed from the RLS tests.
    """
    async with session_factory() as session, session.begin():
        await scope_session_to(session, alpha.organization_id)
        notification = await notifications_for_session(session).notify(
            organization_id=alpha.organization_id,
            recipient_user_id=alpha.member.user_id,
            kind="RECORD_ASSIGNED",
            title="For the member only",
        )
        notification_id = notification.id

    response = as_alpha_admin.post(f"{NOTIFICATIONS}/{notification_id}/read")
    assert response.status_code == 404


async def test_a_notification_is_invisible_across_organizations_even_to_the_same_user(
    session_factory: async_sessionmaker[AsyncSession],
    dual_member: DualMember,
    api: ApiSession,
) -> None:
    """The database enforcement, not the query the router happens to send.

    ``dual_member`` holds an ACTIVE membership, as the same user id, in both
    organizations. A notification recorded for them under alpha must not
    appear when the very same credentials request their inbox scoped to
    beta — proving ``organization_id`` on ``platform.notifications`` is what
    is isolating this, not merely "no row exists for that recipient".
    """
    async with session_factory() as session, session.begin():
        await scope_session_to(session, dual_member.alpha_organization_id)
        await notifications_for_session(session).notify(
            organization_id=dual_member.alpha_organization_id,
            recipient_user_id=dual_member.user_id,
            kind="RECORD_ASSIGNED",
            title="Alpha-only notification",
        )

    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)
    as_alpha = api.get(NOTIFICATIONS).json()
    assert as_alpha["pagination"]["total"] == 1

    api.login(dual_member.email, organization_id=dual_member.beta_organization_id)
    as_beta = api.get(NOTIFICATIONS).json()
    assert as_beta["pagination"]["total"] == 0


async def test_row_level_security_hides_another_organizations_notifications(
    session_factory: async_sessionmaker[AsyncSession],
    dual_member: DualMember,
) -> None:
    """The RLS policy itself, read with no application code in between.

    Same shape as ``test_crm_rls.py``: set the tenant setting by hand and
    query the table directly, so a passing app-level test could not be
    hiding a policy that was never actually created.
    """
    async with session_factory() as session, session.begin():
        await scope_session_to(session, dual_member.alpha_organization_id)
        alpha_notification = await notifications_for_session(session).notify(
            organization_id=dual_member.alpha_organization_id,
            recipient_user_id=dual_member.user_id,
            kind="RECORD_ASSIGNED",
            title="Alpha-only notification",
        )
        alpha_notification_id = alpha_notification.id

    async with session_factory() as session:
        await session.execute(
            text(f"SELECT set_config('{TENANT_SETTING}', :value, false)"),
            {"value": str(dual_member.beta_organization_id)},
        )
        result = await session.execute(
            select(Notification).where(Notification.id == alpha_notification_id)
        )
        assert result.scalar_one_or_none() is None


async def test_notify_writes_an_audit_entry(
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
) -> None:
    async with session_factory() as session, session.begin():
        await scope_session_to(session, alpha.organization_id)
        notification = await notifications_for_session(session).notify(
            organization_id=alpha.organization_id,
            recipient_user_id=alpha.admin.user_id,
            kind="RECORD_ASSIGNED",
            title="Audited notification",
            actor_id=alpha.member.user_id,
        )
        notification_id = notification.id

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        row = (
            await session.execute(
                text(
                    "SELECT action, module, entity_id, actor_id FROM platform.audit_logs "
                    "WHERE module = 'notifications' AND entity_id = :entity_id"
                ),
                {"entity_id": notification_id},
            )
        ).one()
    assert row.action == "CREATED"
    assert row.module == "notifications"
    assert str(row.actor_id) == str(alpha.member.user_id)


def test_notifications_require_authentication(
    client: TestClient, integration_settings: Settings
) -> None:
    response = client.get(f"{integration_settings.api_prefix}{NOTIFICATIONS}")
    assert response.status_code == 401


# --- Reminder dispatch --------------------------------------------------------


async def test_a_meeting_inside_its_reminder_window_fires_once(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    now: dt.datetime,
) -> None:
    async with session_factory() as session, session.begin():
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            owner_id=alpha.admin.user_id,
            subject="Quarterly review",
            start_time=now + dt.timedelta(minutes=5),
            reminder_minutes=10,  # window opened 5 minutes ago; still open
        )

    created = await dispatch_due_reminders_for_all_organizations(session_factory, now=now)
    assert created == 1

    body = as_alpha_admin.get(NOTIFICATIONS).json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["kind"] == "MEETING_REMINDER"
    assert "Quarterly review" in body["data"][0]["title"]

    # A second tick for the same due meeting must not duplicate it.
    created_again = await dispatch_due_reminders_for_all_organizations(
        session_factory, now=now + dt.timedelta(minutes=1)
    )
    assert created_again == 0
    assert as_alpha_admin.get(NOTIFICATIONS).json()["pagination"]["total"] == 1


async def test_a_meeting_outside_its_reminder_window_does_not_fire(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    now: dt.datetime,
) -> None:
    async with session_factory() as session, session.begin():
        # Starts in two hours with only a 10-minute reminder: not due yet.
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            owner_id=alpha.admin.user_id,
            subject="Later today",
            start_time=now + dt.timedelta(hours=2),
            reminder_minutes=10,
        )
        # A meeting with no reminder configured never fires, regardless of
        # how close ``start_time`` is.
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            owner_id=alpha.admin.user_id,
            subject="No reminder wanted",
            start_time=now + dt.timedelta(minutes=1),
            reminder_minutes=None,
        )

    created = await dispatch_due_reminders_for_all_organizations(session_factory, now=now)
    assert created == 0
    assert as_alpha_admin.get(NOTIFICATIONS).json()["pagination"]["total"] == 0


async def test_a_due_task_fires_a_reminder_for_its_assignee(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    now: dt.datetime,
) -> None:
    async with session_factory() as session, session.begin():
        await _seed_task(
            session,
            organization_id=alpha.organization_id,
            title="Send the contract",
            due_date=now - dt.timedelta(hours=1),
            assigned_to_id=alpha.admin.user_id,
        )
        # Not open, so must not fire even though it is overdue.
        await _seed_task(
            session,
            organization_id=alpha.organization_id,
            title="Already done",
            due_date=now - dt.timedelta(hours=1),
            assigned_to_id=alpha.admin.user_id,
            status=TaskStatus.COMPLETED,
        )

    created = await dispatch_due_reminders_for_all_organizations(session_factory, now=now)
    assert created == 1

    body = as_alpha_admin.get(NOTIFICATIONS).json()
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["kind"] == "TASK_DUE"
    assert "Send the contract" in body["data"][0]["title"]


async def test_dispatch_is_isolated_per_organization(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    beta: Tenant,
    now: dt.datetime,
    client: TestClient,
    integration_settings: Settings,
) -> None:
    """A due reminder in one organization must never reach another's inbox."""
    async with session_factory() as session, session.begin():
        await _seed_meeting(
            session,
            organization_id=alpha.organization_id,
            owner_id=alpha.admin.user_id,
            subject="Alpha-only meeting",
            start_time=now + dt.timedelta(minutes=1),
            reminder_minutes=5,
        )

    created = await dispatch_due_reminders_for_all_organizations(session_factory, now=now)
    assert created == 1
    assert as_alpha_admin.get(NOTIFICATIONS).json()["pagination"]["total"] == 1

    as_beta_admin = _session_as(
        client, integration_settings, beta.admin, organization_id=beta.organization_id
    )
    assert as_beta_admin.get(NOTIFICATIONS).json()["pagination"]["total"] == 0
