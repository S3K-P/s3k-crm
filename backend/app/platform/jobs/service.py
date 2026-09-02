"""Enqueuing jobs, and the recurring schedule that keeps them coming.

Two things live here:

* :class:`JobService` — put a job on the queue, idempotently.
* :class:`Schedule` and :func:`enqueue_due_schedules` — turn "every night" into
  concrete queued rows.

The recurring design is deliberately not a cron parser. A schedule names a
cadence, and the enqueuer derives a **period key** from the current time — the
day for a daily job, the hour for an hourly one — and uses it as the
idempotency key. Two schedulers ticking at the same moment, or one ticking
twice, therefore produce one job for that period and not two. The partial
unique index in ``jobs`` enforces it in the database, so the guarantee does not
depend on the enqueuer being careful.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.jobs.models import DEFAULT_MAX_ATTEMPTS, Job, JobStatus

logger = structlog.get_logger(__name__)


class Cadence(enum.StrEnum):
    """How often a recurring job runs.

    Coarse on purpose. A CRM's background work is hourly or nightly; the
    minute-level precision a cron expression buys would only add a parser and a
    class of bugs where a job silently never fires.
    """

    HOURLY = "HOURLY"
    DAILY = "DAILY"


@dataclass(frozen=True, slots=True)
class Schedule:
    """One recurring job, declared as data."""

    job_type: str
    cadence: Cadence
    #: Hour of day (UTC) a daily job becomes due. Ignored for hourly jobs.
    #: Default 2am: after the working day everywhere the product is used, so
    #: nightly aggregation does not compete with people using the CRM.
    hour: int = 2
    payload: dict[str, Any] | None = None
    max_attempts: int = DEFAULT_MAX_ATTEMPTS

    def period_key(self, now: dt.datetime) -> str:
        """The identity of the current period.

        Used as the idempotency key, which is what makes "enqueue the nightly
        jobs" safe to call as often as anybody likes.
        """
        if self.cadence is Cadence.HOURLY:
            return f"{self.job_type}:{now:%Y-%m-%dT%H}"
        return f"{self.job_type}:{now:%Y-%m-%d}"

    def is_due(self, now: dt.datetime) -> bool:
        """Whether this period's run should exist yet.

        An hourly job is due as soon as its hour starts. A daily job waits for
        its configured hour, so calling the enqueuer at 09:00 does not queue
        tonight's work eleven hours early — the period key would then block the
        real 02:00 run from ever being created.
        """
        if self.cadence is Cadence.HOURLY:
            return True
        return now.hour >= self.hour


class JobService:
    """Puts work on the queue."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        organization_id: uuid.UUID,
        job_type: str,
        payload: dict[str, Any] | None = None,
        run_at: dt.datetime | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        actor_id: uuid.UUID | None = None,
    ) -> Job | None:
        """Queue one job, or return ``None`` if an identical one is pending.

        The check is done in the database, not by reading first and writing
        after: two callers racing would both read "nothing there" and both
        insert. The unique index refuses the second, and that
        :class:`IntegrityError` is the answer rather than an error — it means
        somebody else already queued this exact work.
        """
        job = Job(
            organization_id=organization_id,
            job_type=job_type,
            payload=payload or {},
            run_at=run_at or dt.datetime.now(dt.UTC),
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            created_by_id=actor_id,
        )
        savepoint = await self._session.begin_nested()
        try:
            self._session.add(job)
            await self._session.flush()
        except IntegrityError:
            await savepoint.rollback()
            logger.debug(
                "job_already_queued",
                job_type=job_type,
                idempotency_key=idempotency_key,
                organization_id=str(organization_id),
            )
            return None
        await savepoint.commit()
        return job

    async def list_jobs(
        self,
        organization_id: uuid.UUID,
        *,
        job_type: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> Sequence[Job]:
        """Recent jobs for this organization, newest first."""
        statement = select(Job).where(Job.organization_id == organization_id)
        if job_type is not None:
            statement = statement.where(Job.job_type == job_type)
        if status is not None:
            statement = statement.where(Job.status == status)
        result = await self._session.execute(
            statement.order_by(Job.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def counts_by_status(self, organization_id: uuid.UUID) -> dict[str, int]:
        """Queue health, for the admin screen and the readiness probe."""
        result = await self._session.execute(
            select(Job.status, func.count())
            .where(Job.organization_id == organization_id)
            .group_by(Job.status)
        )
        counts = {status.value: 0 for status in JobStatus}
        for status, total in result.all():
            counts[status.value] = int(total)
        return counts

    async def purge_finished(self, *, older_than: dt.datetime) -> int:
        """Delete completed jobs beyond the retention horizon.

        Succeeded jobs only. A FAILED row is the record of something that did
        not happen, and deleting it on a timer would remove the evidence
        somebody still needs.
        """
        result = await self._session.execute(
            delete(Job).where(
                Job.status == JobStatus.SUCCEEDED,
                Job.finished_at.is_not(None),
                Job.finished_at < older_than,
            )
        )
        return int(cast("CursorResult[Any]", result).rowcount or 0)


async def enqueue_due_schedules(
    session: AsyncSession,
    *,
    organization_ids: Sequence[uuid.UUID],
    schedules: Sequence[Schedule],
    now: dt.datetime | None = None,
) -> int:
    """Queue this period's run of every due schedule, for every organization.

    Safe to call on any cadence — every minute, or once an hour. The period key
    means repeated calls within one period are no-ops, so the caller does not
    have to track when it last ran.

    Returns:
        How many jobs were actually created.
    """
    moment = now or dt.datetime.now(dt.UTC)
    service = JobService(session)
    created = 0

    for schedule in schedules:
        if not schedule.is_due(moment):
            continue
        for organization_id in organization_ids:
            job = await service.enqueue(
                organization_id=organization_id,
                job_type=schedule.job_type,
                payload=schedule.payload,
                idempotency_key=schedule.period_key(moment),
                max_attempts=schedule.max_attempts,
            )
            if job is not None:
                created += 1

    if created:
        logger.info("schedules_enqueued", created=created, organizations=len(organization_ids))
    return created


__all__ = ["Cadence", "JobService", "Schedule", "enqueue_due_schedules"]
