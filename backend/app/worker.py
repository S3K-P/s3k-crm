"""The background worker (ADR-013).

A second process, started from the same image as the API:

    uv run arq app.worker.WorkerSettings

It does three things on a schedule — drain the outbox, dispatch due
reminders, and fire due workflow rules (Checkpoint 6) — and all three are
safe to run in as many copies as you like. That is the point of the phase.
Until now the reminder poll lived inside the API process, which is why
``railway.json`` pins ``numReplicas`` to 1: a second API replica would have
produced a second poller and, without the outbox's claim, two of every
reminder.

**Why ARQ is used for scheduling and not for queueing.** The queue is
PostgreSQL, because only PostgreSQL can enrol an event in the same transaction
as the change that caused it — a Redis publish succeeds whether or not the
transaction commits, which is the failure this whole design exists to remove.
ARQ contributes the process supervisor and the cron: the parts that are about
*when* work runs rather than *whether it is real*. Redis holding the schedule
is fine, because a lost tick loses timeliness and never work — the next tick
reads the same rows.

**Every job here is idempotent and safe to overlap.** The outbox drain claims
with ``FOR UPDATE SKIP LOCKED``; the reminder dispatch deduplicates on a
natural key. Two workers, or one worker running a slow tick into the next
one, produce the same result as one.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

import structlog
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory, dispose_engine
from app.platform.events.service import EventDispatcher
from app.platform.notifications.service import (
    dispatch_due_reminders_for_all_organizations,
)

logger = structlog.get_logger(__name__)

#: A CRM-provided periodic scan, registered by the composition root
#: (``app/api/router.py``'s ``register_event_handlers``) exactly the way a
#: CRM outbox handler is — this file must not import ``app.products``
#: directly (``pyproject.toml``'s ``TID251`` has no exemption for it, unlike
#: ``app/api/router.py``/``app/schema.py``/``app/bootstrap.py``), so the
#: dependency runs the other way: the composition root already imports this
#: module to build the FastAPI dependency graph, and calls
#: :func:`register_scheduled_workflow_scanner` from the same function that
#: registers every outbox handler. The worker's own ``startup()`` hook
#: already imports that composition-root function for exactly this reason.
ScheduledWorkflowScanner = Callable[[async_sessionmaker[AsyncSession], dt.datetime], Awaitable[int]]

_scheduled_workflow_scanner: ScheduledWorkflowScanner | None = None


def register_scheduled_workflow_scanner(scanner: ScheduledWorkflowScanner) -> None:
    """Register the CRM implementation of the periodic workflow scan.

    Re-registration replaces, matching ``platform.events.service.register_handler``'s
    own reasoning — a test reload must not accumulate duplicate scanners.
    """
    global _scheduled_workflow_scanner
    _scheduled_workflow_scanner = scanner

#: How often the outbox is drained. Every ten seconds rather than every
#: minute: an invitation email that takes a minute to leave feels broken to
#: the person who just clicked "invite", and an empty poll is one indexed
#: query against a partial index.
DRAIN_SECONDS = frozenset(range(0, 60, 10))


async def drain_outbox(ctx: dict[str, Any]) -> str:
    """Process whatever is due. Returns a summary for ARQ's job log."""
    dispatcher: EventDispatcher = ctx["dispatcher"]
    result = await dispatcher.drain_once()
    if result.claimed:
        logger.info(
            "outbox_drained",
            claimed=result.claimed,
            succeeded=result.succeeded,
            retrying=result.retrying,
            dead=result.dead,
        )
    return (
        f"claimed={result.claimed} succeeded={result.succeeded} "
        f"retrying={result.retrying} dead={result.dead}"
    )


async def dispatch_reminders(ctx: dict[str, Any]) -> str:
    """Create notifications for meetings and tasks coming due.

    Moved here from the API process. The work is unchanged — the same
    ``dispatch_due_reminders_for_all_organizations`` — but running it in the
    worker is what lets the API scale horizontally.
    """
    created = await dispatch_due_reminders_for_all_organizations(
        ctx["session_factory"], now=dt.datetime.now(dt.UTC)
    )
    if created:
        logger.info("reminders_dispatched", created=created)
    return f"created={created}"


async def run_scheduled_workflows(ctx: dict[str, Any]) -> str:
    """Fire ``SCHEDULED``/``TASK_DUE`` workflow rules (Checkpoint 6, Step 11).

    A no-op, logged once, if nothing has registered a scanner yet — it should
    always be registered by the time this fires (see
    :data:`_scheduled_workflow_scanner`'s docstring), so this is a startup-
    ordering guard, not an expected steady state.
    """
    if _scheduled_workflow_scanner is None:
        logger.warning("scheduled_workflow_scanner_not_registered")
        return "fired=0 (no scanner registered)"

    fired = await _scheduled_workflow_scanner(ctx["session_factory"], dt.datetime.now(dt.UTC))
    if fired:
        logger.info("scheduled_workflows_fired", fired=fired)
    return f"fired={fired}"


async def startup(ctx: dict[str, Any]) -> None:
    """Build the engine and the dispatcher once per worker process."""
    settings: Settings = get_settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    ctx["settings"] = settings
    ctx["engine"] = engine
    ctx["session_factory"] = session_factory
    ctx["dispatcher"] = EventDispatcher(
        session_factory,
        batch_size=settings.outbox_batch_size,
        stall_after_seconds=settings.outbox_stall_seconds,
    )

    # Handlers live in the composition root, which is also what mounts the
    # routers. Importing it here rather than at module scope keeps this file
    # free of both layers — and means the worker and the API register exactly
    # the same set, from one place, rather than drifting.
    from app.api.router import register_event_handlers

    register_event_handlers()

    logger.info("worker_started", drain_every_seconds=sorted(DRAIN_SECONDS)[:2])


async def shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine(ctx["engine"])
    logger.info("worker_stopped")


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    """ARQ entry point. ``arq app.worker.WorkerSettings``."""

    functions: ClassVar[list[Any]] = [drain_outbox, dispatch_reminders, run_scheduled_workflows]
    cron_jobs: ClassVar[list[Any]] = [
        # `set(...)`: arq's signature asks for a mutable set and does not copy
        # it, so a frozenset is rejected by the type checker even though it
        # would work.
        cron(drain_outbox, second=set(DRAIN_SECONDS), run_at_startup=True),
        # Once a minute is the resolution reminders are configured at; polling
        # faster would find the same rows and dedupe them away.
        cron(dispatch_reminders, second={5}, run_at_startup=True),
        # Every 15 minutes: a scheduled workflow's own dedupe key (one fire
        # per rule/record/day) makes a faster tick pointless and a slower one
        # would make "3 days before close date" arrive up to an hour late.
        cron(run_scheduled_workflows, minute={0, 15, 30, 45}, run_at_startup=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    # A tick that overruns must not stack up behind itself. Both jobs are
    # idempotent, so the safe behaviour is to skip rather than queue.
    max_jobs = 4
    job_timeout = 300
    keep_result = 60


__all__ = [
    "ScheduledWorkflowScanner",
    "WorkerSettings",
    "dispatch_reminders",
    "drain_outbox",
    "register_scheduled_workflow_scanner",
    "run_scheduled_workflows",
]
