"""Stage 3 and 4: the job queue, and the CRM automation running on it.

The queue's guarantees are the ones worth testing hardest, because each of them
is a bug class that is invisible until production: a job that runs twice, a job
that retries forever because its failure rolled back with its work, a job that
reads another tenant's rows, a job orphaned by a killed worker.
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.core.database import create_session_factory
from app.platform.jobs.models import Job, JobStatus
from app.platform.jobs.runner import JobRegistry, JobRunner
from app.platform.jobs.service import Cadence, JobService, Schedule, enqueue_due_schedules
from app.products.crm.automation.handlers import (
    RECOMPUTE_CAMPAIGN_METRICS,
    SCORE_LEADS,
    STALE_OPPORTUNITY_NUDGE,
    get_settings,
)
from app.products.crm.automation.scoring import score_lead
from app.products.crm.leads.models import Lead
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def clean_jobs(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """The jobs table is not in the shared cleanup list; empty it per test."""
    async with session_factory() as session:
        await session.execute(text("DELETE FROM platform.jobs"))
        await session.execute(text("DELETE FROM crm.automation_settings"))
        await session.commit()


#: A role that RLS actually applies to. The suite's own connection is the
#: table owner (the cleanup fixture has to disable an append-only trigger, which
#: needs ownership), and an owner with BYPASSRLS ignores every policy — so
#: proving the runner's isolation guarantee needs a role that does not.
#: ``test_crm_rls.py`` provisions one the same way for the same reason.
RLS_PROBE_ROLE = "s3k_jobs_rls_probe_role"


@pytest_asyncio.fixture
async def rls_session_factory(
    session_factory: async_sessionmaker[AsyncSession], integration_settings: Settings
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory connected as an ordinary, RLS-subject role."""
    # token_hex is [0-9a-f] only, so inlining it into DDL is injection-safe;
    # CREATE ROLE is DDL and cannot take bind parameters.
    password = secrets.token_hex(24)
    owner = create_async_engine(integration_settings.database_url)

    async with owner.begin() as connection:
        await connection.execute(text(f"DROP ROLE IF EXISTS {RLS_PROBE_ROLE}"))
        await connection.execute(
            text(
                f"CREATE ROLE {RLS_PROBE_ROLE} LOGIN NOSUPERUSER NOBYPASSRLS "
                f"PASSWORD '{password}'"
            )
        )
        for schema in ("crm", "platform"):
            await connection.execute(text(f"GRANT USAGE ON SCHEMA {schema} TO {RLS_PROBE_ROLE}"))
            await connection.execute(
                text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                    f"IN SCHEMA {schema} TO {RLS_PROBE_ROLE}"
                )
            )

    url = make_url(integration_settings.database_url).set(
        username=RLS_PROBE_ROLE, password=password
    )
    engine: AsyncEngine = create_async_engine(url)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()
        async with owner.begin() as connection:
            await connection.execute(text(f"DROP OWNED BY {RLS_PROBE_ROLE}"))
            await connection.execute(text(f"DROP ROLE IF EXISTS {RLS_PROBE_ROLE}"))
        await owner.dispose()


def _registry(**handlers: Any) -> JobRegistry:
    registry = JobRegistry()
    for job_type, handler in handlers.items():
        registry.register(job_type, handler)
    return registry


# --- Enqueuing and idempotency -----------------------------------------------


async def test_a_job_is_queued_and_claimed_once(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    """The basic contract: enqueue, claim, run, record."""
    seen: list[uuid.UUID] = []

    async def handler(session: AsyncSession, job: Job) -> dict[str, Any]:
        del session
        seen.append(job.organization_id)
        return {"ok": True}

    async with session_factory() as session, session.begin():
        await JobService(session).enqueue(
            organization_id=alpha.organization_id, job_type="test.noop"
        )

    runner = JobRunner(session_factory, _registry(**{"test.noop": handler}))
    outcome = await runner.run_once()

    assert outcome is not None
    assert outcome.status is JobStatus.SUCCEEDED
    assert seen == [alpha.organization_id]
    # The queue is now empty: a second claim finds nothing.
    assert await runner.run_once() is None


async def test_an_idempotency_key_collapses_duplicate_enqueues(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    """The duplicate-execution guarantee, enforced by a unique index."""
    async with session_factory() as session, session.begin():
        service = JobService(session)
        first = await service.enqueue(
            organization_id=alpha.organization_id,
            job_type="test.noop",
            idempotency_key="nightly:2026-09-03",
        )
        second = await service.enqueue(
            organization_id=alpha.organization_id,
            job_type="test.noop",
            idempotency_key="nightly:2026-09-03",
        )

    assert first is not None
    assert second is None, "the second enqueue must collapse into the first"


async def test_the_same_key_may_be_queued_again_once_the_first_finished(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    """The index is partial on QUEUED/RUNNING for exactly this reason.

    Without that predicate a nightly job could be queued once and never again.
    """

    async def handler(session: AsyncSession, job: Job) -> None:
        del session, job
        return None

    async with session_factory() as session, session.begin():
        await JobService(session).enqueue(
            organization_id=alpha.organization_id,
            job_type="test.noop",
            idempotency_key="nightly:2026-09-03",
        )
    await JobRunner(session_factory, _registry(**{"test.noop": handler})).run_once()

    async with session_factory() as session, session.begin():
        again = await JobService(session).enqueue(
            organization_id=alpha.organization_id,
            job_type="test.noop",
            idempotency_key="nightly:2026-09-03",
        )

    assert again is not None


async def test_two_organizations_do_not_share_an_idempotency_key(
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    beta: Tenant,
    clean_jobs: None,
) -> None:
    """The key is scoped per tenant; one tenant's nightly job is not another's."""
    async with session_factory() as session, session.begin():
        service = JobService(session)
        first = await service.enqueue(
            organization_id=alpha.organization_id,
            job_type="test.noop",
            idempotency_key="nightly:2026-09-03",
        )
        second = await service.enqueue(
            organization_id=beta.organization_id,
            job_type="test.noop",
            idempotency_key="nightly:2026-09-03",
        )

    assert first is not None
    assert second is not None


# --- Failure, retry and recovery ---------------------------------------------


async def test_a_failing_job_is_retried_with_its_error_recorded(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    """The classic queue bug: bookkeeping that rolls back with the work.

    The handler here corrupts its own transaction, which is exactly the case
    where recording the attempt inside that transaction would vanish — and the
    job would retry forever having never counted an attempt.
    """

    async def broken(session: AsyncSession, job: Job) -> None:
        del job
        await session.execute(text("SELECT 1 FROM does_not_exist"))

    async with session_factory() as session, session.begin():
        await JobService(session).enqueue(
            organization_id=alpha.organization_id, job_type="test.broken", max_attempts=2
        )

    runner = JobRunner(session_factory, _registry(**{"test.broken": broken}))
    outcome = await runner.run_once()

    assert outcome is not None
    assert outcome.status is JobStatus.QUEUED, "first failure should re-queue"
    assert outcome.attempts == 1

    async with session_factory() as session:
        job = (await session.execute(select(Job))).scalar_one()
        assert job.attempts == 1
        assert job.last_error is not None
        assert job.status is JobStatus.QUEUED
        # Backed off rather than immediately due again.
        assert job.run_at > dt.datetime.now(dt.UTC)


async def test_retries_are_exhausted_into_a_failed_job(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    """A permanently broken handler must stop, and stay visible."""

    async def broken(session: AsyncSession, job: Job) -> None:
        del session, job
        raise RuntimeError("nope")

    async with session_factory() as session, session.begin():
        await JobService(session).enqueue(
            organization_id=alpha.organization_id, job_type="test.broken", max_attempts=1
        )

    runner = JobRunner(session_factory, _registry(**{"test.broken": broken}))
    outcome = await runner.run_once()

    assert outcome is not None
    assert outcome.status is JobStatus.FAILED
    async with session_factory() as session:
        job = (await session.execute(select(Job))).scalar_one()
        assert job.status is JobStatus.FAILED
        assert "nope" in (job.last_error or "")


async def test_an_unknown_job_type_fails_without_retrying(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    """No number of attempts will conjure a handler."""
    async with session_factory() as session, session.begin():
        await JobService(session).enqueue(
            organization_id=alpha.organization_id, job_type="test.missing", max_attempts=5
        )

    outcome = await JobRunner(session_factory, JobRegistry()).run_once()

    assert outcome is not None
    assert outcome.status is JobStatus.FAILED
    assert outcome.attempts == 1


async def test_a_job_orphaned_by_a_dead_worker_is_reclaimed(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    """A worker killed mid-job leaves RUNNING behind; the claim must time out."""
    ran: list[str] = []

    async def handler(session: AsyncSession, job: Job) -> None:
        del session, job
        ran.append("yes")

    async with session_factory() as session, session.begin():
        job = await JobService(session).enqueue(
            organization_id=alpha.organization_id, job_type="test.noop"
        )
        assert job is not None
        # Simulate the crash: claimed long ago, never finished.
        job.status = JobStatus.RUNNING
        job.locked_at = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
        job.locked_by = "dead-worker"

    outcome = await JobRunner(session_factory, _registry(**{"test.noop": handler})).run_once()

    assert outcome is not None
    assert outcome.status is JobStatus.SUCCEEDED
    assert ran == ["yes"]


async def test_a_job_scheduled_for_later_is_not_claimed_yet(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    async def handler(session: AsyncSession, job: Job) -> None:
        del session, job

    async with session_factory() as session, session.begin():
        await JobService(session).enqueue(
            organization_id=alpha.organization_id,
            job_type="test.noop",
            run_at=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        )

    assert await JobRunner(session_factory, _registry(**{"test.noop": handler})).run_once() is None


# --- Tenant context -----------------------------------------------------------


async def test_a_handler_runs_inside_its_own_tenants_scope(
    session_factory: async_sessionmaker[AsyncSession],
    rls_session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    api: ApiSession,
    alpha: Tenant,
    beta: Tenant,
    clean_jobs: None,
) -> None:
    """The runner sets the tenant before calling, so RLS applies to the handler.

    A handler whose own query forgets to filter must still see only its own
    organization's rows. This one deliberately queries without a filter, and
    runs on a role RLS is not bypassed for — otherwise the assertion would pass
    for the wrong reason on any connection.
    """
    as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Alpha", "last_name": "Lead", "company": "A Ltd"}
    )
    api.login(beta.admin.email, organization_id=beta.organization_id)
    api.post(
        "/crm/leads", json={"first_name": "Beta", "last_name": "Lead", "company": "B Ltd"}
    )

    seen: dict[str, list[str]] = {}

    async def unfiltered(session: AsyncSession, job: Job) -> None:
        # No organization_id predicate anywhere. RLS is the only thing
        # standing between this and the other tenant's data.
        result = await session.execute(select(Lead.last_name, Lead.first_name))
        seen[str(job.organization_id)] = sorted(row[1] for row in result.all())

    async with session_factory() as session, session.begin():
        service = JobService(session)
        await service.enqueue(organization_id=alpha.organization_id, job_type="test.scan")
        await service.enqueue(organization_id=beta.organization_id, job_type="test.scan")

    # The queue is claimed by the privileged connection (it must see every
    # tenant's jobs); the handler runs on the RLS-subject one.
    await JobRunner(
        session_factory,
        _registry(**{"test.scan": unfiltered}),
        handler_session_factory=rls_session_factory,
    ).drain()

    assert seen[str(alpha.organization_id)] == ["Alpha"]
    assert seen[str(beta.organization_id)] == ["Beta"]


# --- Schedules ----------------------------------------------------------------


def test_a_daily_schedule_is_not_due_before_its_hour() -> None:
    """Queuing tonight's work at 09:00 would block the real 02:00 run."""
    schedule = Schedule("crm.thing", Cadence.DAILY, hour=2)

    assert not schedule.is_due(dt.datetime(2026, 9, 3, 1, tzinfo=dt.UTC))
    assert schedule.is_due(dt.datetime(2026, 9, 3, 2, tzinfo=dt.UTC))


def test_the_period_key_changes_between_periods() -> None:
    daily = Schedule("crm.thing", Cadence.DAILY)
    hourly = Schedule("crm.thing", Cadence.HOURLY)
    monday = dt.datetime(2026, 9, 3, 5, tzinfo=dt.UTC)
    tuesday = dt.datetime(2026, 9, 4, 5, tzinfo=dt.UTC)

    assert daily.period_key(monday) != daily.period_key(tuesday)
    assert daily.period_key(monday) == daily.period_key(monday.replace(hour=23))
    assert hourly.period_key(monday) != hourly.period_key(monday.replace(hour=6))


async def test_enqueuing_schedules_twice_creates_one_job(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, clean_jobs: None
) -> None:
    """The scheduler is safe to call as often as anybody likes."""
    schedules = [Schedule("test.noop", Cadence.DAILY, hour=0)]
    moment = dt.datetime(2026, 9, 3, 5, tzinfo=dt.UTC)

    async with session_factory() as session, session.begin():
        first = await enqueue_due_schedules(
            session,
            organization_ids=[alpha.organization_id],
            schedules=schedules,
            now=moment,
        )
        second = await enqueue_due_schedules(
            session,
            organization_ids=[alpha.organization_id],
            schedules=schedules,
            now=moment,
        )

    assert first == 1
    assert second == 0


# --- CRM automation handlers --------------------------------------------------


async def test_scoring_is_off_until_an_organization_turns_it_on(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    clean_jobs: None,
) -> None:
    """A wrong score erodes trust faster than a missing one."""
    as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company": "Engines",
            "email": "ada@engines.example",
        },
    )

    async with session_factory() as session, session.begin():
        await JobService(session).enqueue(
            organization_id=alpha.organization_id, job_type=SCORE_LEADS
        )

    from app.products.crm.automation.handlers import HANDLERS

    registry = JobRegistry()
    for job_type, handler in HANDLERS.items():
        registry.register(job_type, handler)
    outcome = await JobRunner(session_factory, registry).run_once()

    assert outcome is not None
    assert outcome.status is JobStatus.SUCCEEDED
    assert outcome.result is not None
    assert "skipped" in outcome.result


async def test_lead_scoring_populates_ai_score_when_enabled(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    clean_jobs: None,
) -> None:
    """The column has existed since the beginning with nothing computing it."""
    as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company": "Engines",
            "email": "ada@engines.example",
            "phone": "555-0100",
        },
    )

    async with session_factory() as session, session.begin():
        settings = await get_settings(session, alpha.organization_id)
        settings.lead_scoring_enabled = True
        await JobService(session).enqueue(
            organization_id=alpha.organization_id, job_type=SCORE_LEADS
        )

    from app.products.crm.automation.handlers import HANDLERS

    registry = JobRegistry()
    for job_type, handler in HANDLERS.items():
        registry.register(job_type, handler)
    outcome = await JobRunner(session_factory, registry).run_once()

    assert outcome is not None, "the job should have been claimed"
    assert outcome.status is JobStatus.SUCCEEDED, outcome.error
    assert outcome.result == {"scored": 1, "changed": 1}

    lead = as_alpha_admin.get("/crm/leads").json()["data"][0]
    assert lead["ai_score"] is not None
    assert lead["ai_score"] > 0


async def test_a_score_is_reproducible_and_explains_itself(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    clean_jobs: None,
) -> None:
    """A number a rep cannot argue with is a number they stop looking at."""
    as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company": "Engines",
            "email": "ada@engines.example",
        },
    )

    async with session_factory() as session:
        lead = (await session.execute(select(Lead))).scalars().first()
        assert lead is not None
        first = await score_lead(session, lead)
        second = await score_lead(session, lead)

    assert first.value == second.value, "the same inputs must give the same score"
    assert "has_email" in first.components
    assert "has_company" in first.components


async def test_a_lead_with_no_contact_details_scores_lower(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    clean_jobs: None,
) -> None:
    """A score that can only go up ranks everything equally after a while."""
    as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Reachable",
            "last_name": "Person",
            "company": "A Ltd",
            "email": "reach@a.example",
            "phone": "555-1",
        },
    )
    as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Unreachable", "last_name": "Person", "company": "B Ltd"},
    )

    async with session_factory() as session:
        leads = (await session.execute(select(Lead))).scalars().all()
        scores = {}
        for lead in leads:
            scores[lead.first_name] = (await score_lead(session, lead)).value

    assert scores["Reachable"] > scores["Unreachable"]


async def test_campaign_metrics_are_recomputed_by_the_job(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    clean_jobs: None,
) -> None:
    """The calculation already existed; nothing called it on a schedule."""
    campaign = as_alpha_admin.post(
        "/crm/campaigns",
        json={"name": "Autumn Webinar", "type": "WEBINAR", "budget": "1000.00"},
    )
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["id"]

    created = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "company": "Engines",
            "campaign_id": campaign_id,
        },
    )
    assert created.status_code == 201, created.text

    async with session_factory() as session, session.begin():
        await JobService(session).enqueue(
            organization_id=alpha.organization_id, job_type=RECOMPUTE_CAMPAIGN_METRICS
        )

    from app.products.crm.automation.handlers import HANDLERS

    registry = JobRegistry()
    for job_type, handler in HANDLERS.items():
        registry.register(job_type, handler)
    outcome = await JobRunner(session_factory, registry).run_once()

    assert outcome is not None
    assert outcome.status is JobStatus.SUCCEEDED, outcome.error
    refreshed = as_alpha_admin.get(f"/crm/campaigns/{campaign_id}").json()
    assert refreshed["leads_generated"] == 1


async def test_the_stale_nudge_does_not_create_a_second_task(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    clean_jobs: None,
) -> None:
    """Run nightly without the guard and a quiet deal grows fourteen tasks."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Quiet Ltd"}).json()
    stages = as_alpha_admin.get("/crm/opportunities/stages").json()
    deal = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Gone quiet",
            "account_id": str(account["id"]),
            "stage_id": str(stages[0]["id"]),
            "expected_close_date": "2026-12-31",
        },
    )
    assert deal.status_code == 201, deal.text

    # Age it past the staleness window.
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE crm.opportunities SET updated_at = now() - interval '30 days' "
                "WHERE id = :id"
            ),
            {"id": deal.json()["id"]},
        )

    from app.products.crm.automation.handlers import HANDLERS

    registry = JobRegistry()
    for job_type, handler in HANDLERS.items():
        registry.register(job_type, handler)
    runner = JobRunner(session_factory, registry)

    for _ in range(2):
        async with session_factory() as session, session.begin():
            await JobService(session).enqueue(
                organization_id=alpha.organization_id, job_type=STALE_OPPORTUNITY_NUDGE
            )
        outcome = await runner.run_once()
        assert outcome is not None
        assert outcome.status is JobStatus.SUCCEEDED, outcome.error

    tasks = as_alpha_admin.get(
        "/crm/tasks",
        params={"related_entity_type": "OPPORTUNITY", "related_entity_id": deal.json()["id"]},
    ).json()["data"]
    nudges = [t for t in tasks if t["title"] == "Follow up: no activity recently"]
    assert len(nudges) == 1, "the second run must not duplicate the nudge"
