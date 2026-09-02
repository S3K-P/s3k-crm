"""Claiming, running and retrying background jobs.

The loop is: claim a due job, open a transaction scoped to its organization,
run the handler, record what happened. Everything interesting is in how each of
those steps fails.

**Tenant context is not optional and not the caller's responsibility.**
:meth:`JobRunner.run_once` applies the job's organization to the transaction
before the handler is invoked, so a handler that forgets to filter still sees
only that tenant's rows — RLS is doing the work, exactly as it does for an HTTP
request. A handler cannot opt out, because it never receives an unscoped
session.

**A handler that raises does not lose the job.** The failure is recorded on its
own connection, outside the rolled-back work transaction, so a job whose
handler corrupted its transaction still gets its attempt counted and its error
stored. Getting this wrong is the classic queue bug: the retry bookkeeping
rolls back with the work, the job looks untouched, and it retries forever.

**The queue connection and the work connection have different privileges**, and
the runner keeps them separate on purpose:

* *Claiming* has to look **across** organizations — the whole question is
  "whose job is due next", which cannot be asked from inside one tenant's
  scope. That connection therefore needs to read ``platform.jobs`` unfiltered,
  which in a deployment means a worker role holding ``BYPASSRLS`` or a policy
  admitting it. It touches nothing but the queue table.
* *Running* is scoped to exactly one organization, on a separate session, with
  the tenant setting applied. This is the connection a handler ever sees.

``handler_session_factory`` exists so those can be two different roles. Passing
one factory — the default — means the same role does both, which is what a
single-role development setup does.
"""

from __future__ import annotations

import datetime as dt
import socket
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import apply_tenant_context
from app.core.tenant import TenantContext, reset_tenant_context, set_tenant_context
from app.platform.jobs.contracts import JobContext
from app.platform.jobs.models import (
    CLAIM_TIMEOUT_SECONDS,
    Job,
    JobStatus,
)

logger = structlog.get_logger(__name__)

#: A handler receives a tenant-scoped session and the job's data, and returns
#: a summary stored on the row. Returning ``None`` is fine; it means "nothing
#: worth recording".
#:
#: :class:`JobContext` rather than the ``Job`` row: products may not import
#: Platform models (ADR-003), and a handler has no business touching retry
#: bookkeeping or lock state anyway.
JobHandler = Callable[[AsyncSession, JobContext], Awaitable[dict[str, Any] | None]]


class UnknownJobTypeError(RuntimeError):
    """No handler is registered for this job's type."""


@dataclass(slots=True)
class JobRegistry:
    """Maps ``job_type`` to the coroutine that performs it.

    A registry rather than imports so the Platform queue never has to know a
    product exists (ARCHITECTURE-BOUNDARIES.md rule 1). CRM registers its
    handlers at the composition root, the same inversion
    ``documents_router.register_entity_access`` uses for attachments.
    """

    handlers: dict[str, JobHandler]

    def __init__(self) -> None:
        self.handlers = {}

    def register(self, job_type: str, handler: JobHandler) -> None:
        if job_type in self.handlers:
            raise ValueError(f"A handler for {job_type!r} is already registered.")
        self.handlers[job_type] = handler

    def get(self, job_type: str) -> JobHandler:
        handler = self.handlers.get(job_type)
        if handler is None:
            raise UnknownJobTypeError(job_type)
        return handler

    def known(self) -> tuple[str, ...]:
        return tuple(sorted(self.handlers))


@dataclass(frozen=True, slots=True)
class JobOutcome:
    """What one execution produced, for the caller and the tests."""

    job_id: uuid.UUID
    job_type: str
    status: JobStatus
    attempts: int
    error: str | None = None
    result: dict[str, Any] | None = None


def _context_for(job: Job) -> JobContext:
    """The handler's view of a claimed job."""
    return JobContext(
        job_id=job.id,
        organization_id=job.organization_id,
        job_type=job.job_type,
        payload=dict(job.payload or {}),
        attempt=job.attempts,
    )


def worker_name() -> str:
    """Identifies the process holding a claim, for operators reading the table."""
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


class JobRunner:
    """Executes queued jobs one at a time."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: JobRegistry,
        *,
        worker: str | None = None,
        handler_session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory
        #: Where handlers run. Defaults to the queue's own factory; supply a
        #: separate one to run handlers under a less privileged role than the
        #: one that claims (see the module docstring).
        self._handler_session_factory = handler_session_factory or session_factory
        self._registry = registry
        self._worker = worker or worker_name()

    def known_job_types(self) -> tuple[str, ...]:
        """What this worker can run, for the startup log."""
        return self._registry.known()

    async def claim(self, *, now: dt.datetime | None = None) -> Job | None:
        """Take one due job, or return ``None``.

        ``FOR UPDATE SKIP LOCKED`` is what makes concurrent workers safe: the
        row is locked for the length of this short transaction, and a second
        worker running the same query skips it rather than blocking or
        double-claiming.

        A job left ``RUNNING`` past :data:`CLAIM_TIMEOUT_SECONDS` is reclaimed.
        That is the only way a job orphaned by a killed worker ever runs again,
        and it is why the claim is time-boxed rather than permanent.
        """
        moment = now or dt.datetime.now(dt.UTC)
        stale_before = moment - dt.timedelta(seconds=CLAIM_TIMEOUT_SECONDS)

        async with self._session_factory() as session, session.begin():
            statement = (
                select(Job)
                .where(
                    Job.run_at <= moment,
                    (Job.status == JobStatus.QUEUED)
                    | (
                        (Job.status == JobStatus.RUNNING)
                        & (Job.locked_at.is_not(None))
                        & (Job.locked_at < stale_before)
                    ),
                )
                .order_by(Job.run_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = (await session.execute(statement)).scalar_one_or_none()
            if job is None:
                return None

            job.status = JobStatus.RUNNING
            job.locked_at = moment
            job.locked_by = self._worker
            job.started_at = job.started_at or moment
            job.attempts += 1
            await session.flush()
            session.expunge(job)
            return job

    async def run_once(self, *, now: dt.datetime | None = None) -> JobOutcome | None:
        """Claim and execute one job. Returns ``None`` when the queue is idle."""
        job = await self.claim(now=now)
        if job is None:
            return None
        return await self.execute(job)

    async def execute(self, job: Job) -> JobOutcome:
        """Run one already-claimed job inside its tenant's scope."""
        context = TenantContext(organization_id=job.organization_id)
        token = set_tenant_context(context)
        log = logger.bind(
            job_id=str(job.id),
            job_type=job.job_type,
            organization_id=str(job.organization_id),
            attempt=job.attempts,
        )
        try:
            handler = self._registry.get(job.job_type)
        except UnknownJobTypeError:
            reset_tenant_context(token)
            # Not retryable: no number of attempts will conjure a handler. Fail
            # it immediately so it stops occupying the queue, and say why.
            await self._finish(
                job,
                status=JobStatus.FAILED,
                error=f"No handler registered for {job.job_type!r}.",
            )
            log.error("job_handler_missing")
            return JobOutcome(
                job_id=job.id,
                job_type=job.job_type,
                status=JobStatus.FAILED,
                attempts=job.attempts,
                error="handler not registered",
            )

        try:
            async with self._handler_session_factory() as session, session.begin():
                # The whole point of the runner: the handler cannot see another
                # tenant's rows even if its own query forgets to filter.
                await apply_tenant_context(session, context)
                result = await handler(session, _context_for(job))
            await self._finish(job, status=JobStatus.SUCCEEDED, result=result)
            log.info("job_succeeded")
            return JobOutcome(
                job_id=job.id,
                job_type=job.job_type,
                status=JobStatus.SUCCEEDED,
                attempts=job.attempts,
                result=result,
            )
        except Exception as error:
            detail = "".join(
                traceback.format_exception_only(type(error), error)
            ).strip()
            exhausted = job.attempts >= job.max_attempts
            if exhausted:
                await self._finish(job, status=JobStatus.FAILED, error=detail)
                log.error("job_failed", error=detail)
                status = JobStatus.FAILED
            else:
                await self._requeue(job, error=detail)
                log.warning("job_retrying", error=detail, next_in=job.next_backoff())
                status = JobStatus.QUEUED
            return JobOutcome(
                job_id=job.id,
                job_type=job.job_type,
                status=status,
                attempts=job.attempts,
                error=detail,
            )
        finally:
            reset_tenant_context(token)

    async def _finish(
        self,
        job: Job,
        *,
        status: JobStatus,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Record a terminal outcome on a fresh transaction.

        Fresh on purpose. If the handler's transaction was rolled back — which
        is exactly the case when it raised — writing the outcome inside it
        would roll back too, and the job would look as though it had never
        been attempted.
        """
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(
                    status=status,
                    finished_at=dt.datetime.now(dt.UTC),
                    last_error=error,
                    result=result,
                    locked_at=None,
                    locked_by=None,
                )
            )

    async def _requeue(self, job: Job, *, error: str) -> None:
        """Schedule the next attempt after a backoff."""
        delay = job.next_backoff()
        async with self._session_factory() as session, session.begin():
            await session.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(
                    status=JobStatus.QUEUED,
                    run_at=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=delay),
                    last_error=error,
                    locked_at=None,
                    locked_by=None,
                )
            )

    async def drain(self, *, limit: int = 100) -> list[JobOutcome]:
        """Run due jobs until the queue is empty or ``limit`` is reached.

        The test entry point, and what a one-shot worker invocation uses. The
        limit stops a handler that enqueues its own successor from looping
        forever inside a single call.
        """
        outcomes: list[JobOutcome] = []
        for _ in range(limit):
            outcome = await self.run_once()
            if outcome is None:
                break
            outcomes.append(outcome)
        return outcomes


__all__ = [
    "JobContext",
    "JobHandler",
    "JobOutcome",
    "JobRegistry",
    "JobRunner",
    "UnknownJobTypeError",
    "worker_name",
]
