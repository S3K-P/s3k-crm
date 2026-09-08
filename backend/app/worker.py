"""The background worker (ADR-013).

A second process, started from the same image as the API:

    uv run arq app.worker.WorkerSettings

It does two things on a schedule — drain the outbox, and dispatch due
reminders — and both are safe to run in as many copies as you like. That is
the point of the phase. Until now the reminder poll lived inside the API
process, which is why ``railway.json`` pins ``numReplicas`` to 1: a second API
replica would have produced a second poller and, without the outbox's claim,
two of every reminder.

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
from typing import Any, ClassVar

import structlog
from arq import cron
from arq.connections import RedisSettings

from app.core.config import Settings, get_settings
from app.core.database import create_engine, create_session_factory, dispose_engine
from app.platform.events.service import EventDispatcher
from app.platform.notifications.service import (
    dispatch_due_reminders_for_all_organizations,
)

logger = structlog.get_logger(__name__)

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

    functions: ClassVar[list[Any]] = [drain_outbox, dispatch_reminders]
    cron_jobs: ClassVar[list[Any]] = [
        # `set(...)`: arq's signature asks for a mutable set and does not copy
        # it, so a frozenset is rejected by the type checker even though it
        # would work.
        cron(drain_outbox, second=set(DRAIN_SECONDS), run_at_startup=True),
        # Once a minute is the resolution reminders are configured at; polling
        # faster would find the same rows and dedupe them away.
        cron(dispatch_reminders, second={5}, run_at_startup=True),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    # A tick that overruns must not stack up behind itself. Both jobs are
    # idempotent, so the safe behaviour is to skip rather than queue.
    max_jobs = 4
    job_timeout = 300
    keep_result = 60


__all__ = ["WorkerSettings", "dispatch_reminders", "drain_outbox"]
