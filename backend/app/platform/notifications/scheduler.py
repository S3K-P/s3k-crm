"""In-process reminder scheduler.

Owns one long-lived ``asyncio`` task, started and stopped by
``app.application``'s lifespan alongside the Redis client and the database
engine. See ``service.py`` for why this runs in-process rather than as an ARQ
worker at this stage, and why that is safe under the single-replica
deployment this codebase currently ships.

A missed or slow tick loses timeliness, never correctness: the next tick reads
the same due rows and either creates the notification that never got created,
or finds the dedupe key already present and does nothing — see
``NotificationRepository.create_deduplicated``.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.notifications.service import dispatch_due_reminders_for_all_organizations

logger = structlog.get_logger(__name__)


class ReminderScheduler:
    """Polls every active organization for due reminders on a fixed interval."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        interval_seconds: int,
    ) -> None:
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the background task. A no-op if already running."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="notification-reminder-scheduler")

    async def stop(self) -> None:
        """Cancel the background task and wait for it to unwind.

        Idempotent, and safe to call even if :meth:`start` was never called —
        the lifespan's ``finally`` block calls this unconditionally.
        """
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        logger.info("reminder_scheduler_started", interval_seconds=self._interval_seconds)
        try:
            while True:
                await self._tick()
                await asyncio.sleep(self._interval_seconds)
        except asyncio.CancelledError:
            logger.info("reminder_scheduler_stopped")
            raise

    async def _tick(self) -> None:
        # Broad on purpose: a database blip or a bad row in one organization
        # must end this tick, not the loop. The next tick tries again.
        try:
            created = await dispatch_due_reminders_for_all_organizations(self._session_factory)
            if created:
                logger.info("reminders_dispatched", count=created)
        except Exception:
            logger.exception("reminder_scheduler_tick_failed")


__all__ = ["ReminderScheduler"]
