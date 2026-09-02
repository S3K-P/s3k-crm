"""The background worker: composition root for jobs.

This is the only module that may see both the Platform queue and the CRM
handlers, exactly as ``app/api/router.py`` is the only one that may mount both
layers' routers. The queue therefore never imports a product
(ARCHITECTURE-BOUNDARIES.md rule 1) — CRM's handlers are pushed *into* it here.

Run it::

    uv run python -m app.worker            # loop until stopped
    uv run python -m app.worker --once     # drain the queue and exit

``--once`` is what a cron entry or a test uses; the loop is what a long-running
container uses.

**Shutdown is graceful.** SIGTERM sets a flag; the loop finishes the job it is
running and then exits. A job killed mid-flight is not lost either — its claim
goes stale after ``CLAIM_TIMEOUT_SECONDS`` and another worker picks it up — but
finishing cleanly avoids the wait and the duplicated work.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from types import FrameType

import structlog
from sqlalchemy import select

from app.core.config import Settings, load_settings_or_exit
from app.core.database import create_engine, create_session_factory
from app.core.logging import configure_logging
from app.platform.jobs.runner import JobRegistry, JobRunner
from app.platform.jobs.service import enqueue_due_schedules
from app.platform.organizations.models import Organization
from app.products.crm.automation.handlers import HANDLERS, SCHEDULES

logger = structlog.get_logger(__name__)

#: How long the loop sleeps when the queue is empty. Short enough that a job
#: enqueued by a request is picked up promptly, long enough that an idle worker
#: is not a busy poll against the database.
IDLE_SLEEP_SECONDS = 5.0

#: How often the scheduler checks whether a recurring job is due. The period
#: key makes repeated checks free, so this only bounds latency, not correctness.
SCHEDULE_TICK_SECONDS = 60.0


def build_registry() -> JobRegistry:
    """Every job type this worker can run.

    One place to look for "what runs in the background", and the reason an
    unknown ``job_type`` fails fast rather than retrying: the registry is the
    complete list, so a missing handler is a deployment mistake, not a
    transient fault.
    """
    registry = JobRegistry()
    for job_type, handler in HANDLERS.items():
        registry.register(job_type, handler)
    return registry


class Worker:
    """Claims and runs jobs until asked to stop."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine = create_engine(settings)
        self._session_factory = create_session_factory(self._engine)
        self._runner = JobRunner(self._session_factory, build_registry())
        self._stopping = asyncio.Event()

    def request_stop(self) -> None:
        """Ask the loop to finish the current job and exit."""
        logger.info("worker_stop_requested")
        self._stopping.set()

    async def enqueue_schedules(self) -> int:
        """Queue this period's recurring jobs for every organization.

        Organizations are listed rather than joined against: the queue is
        per-tenant, and a job for an organization that no longer exists would
        run against nothing. Cheap — this is a handful of rows, once a minute.
        """
        async with self._session_factory() as session, session.begin():
            result = await session.execute(select(Organization.id))
            organization_ids = list(result.scalars().all())
            if not organization_ids:
                return 0
            return await enqueue_due_schedules(
                session, organization_ids=organization_ids, schedules=SCHEDULES
            )

    async def run_forever(self) -> None:
        """The main loop: schedule, drain, sleep, repeat."""
        logger.info(
            "worker_started",
            handlers=self._runner.known_job_types(),
            schedules=[schedule.job_type for schedule in SCHEDULES],
        )
        last_tick = 0.0
        loop = asyncio.get_running_loop()

        while not self._stopping.is_set():
            now = loop.time()
            if now - last_tick >= SCHEDULE_TICK_SECONDS:
                last_tick = now
                try:
                    await self.enqueue_schedules()
                except Exception as error:
                    logger.error("schedule_tick_failed", error=str(error))

            outcome = await self._runner.run_once()
            if outcome is None:
                # Nothing due. Wait, but wake immediately on shutdown.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=IDLE_SLEEP_SECONDS
                    )

        logger.info("worker_stopped")

    async def run_once(self) -> int:
        """Drain the queue once and return how many jobs ran."""
        await self.enqueue_schedules()
        outcomes = await self._runner.drain()
        return len(outcomes)

    async def aclose(self) -> None:
        await self._engine.dispose()


async def _main(*, once: bool) -> int:
    settings = load_settings_or_exit()
    configure_logging(settings)
    worker = Worker(settings)

    def _handle_signal(signum: int, _frame: FrameType | None) -> None:
        del signum
        worker.request_stop()

    # Windows has no SIGTERM handler support through ``signal.signal`` in every
    # context, so both registrations are best-effort: a worker that cannot
    # install them still runs, it just exits abruptly rather than gracefully.
    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is not None:
            with contextlib.suppress(ValueError, OSError, AttributeError):
                signal.signal(sig, _handle_signal)

    try:
        if once:
            ran = await worker.run_once()
            logger.info("worker_drained", jobs=ran)
            return 0
        await worker.run_forever()
        return 0
    finally:
        await worker.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the S3K background worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Drain the queue and exit, instead of looping.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(once=args.once)))


if __name__ == "__main__":
    main()
