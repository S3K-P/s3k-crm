"""Claiming, completing and failing outbox events.

Everything correctness-critical about running more than one worker is in
:meth:`EventRepository.claim`, and it is one clause: ``FOR UPDATE SKIP
LOCKED``. Two workers issuing the same query take disjoint sets of rows —
the second skips what the first has locked rather than blocking on it — so
scaling out is adding processes, with no coordinator, no leases in Redis and
no partitioning scheme to get wrong. It is also what makes the reminder
scheduler's single-replica constraint go away.

The claim and the work are **not** in one transaction, deliberately. Holding a
row lock for the duration of an HTTP call to an email provider would keep a
PostgreSQL connection open for the provider's entire latency, and a slow
provider would exhaust the pool. So a claim commits immediately, marking the
row PROCESSING with a timestamp, and a worker that dies mid-attempt leaves a
row that :meth:`reclaim_stalled` returns to PENDING. The cost of that choice
is at-least-once delivery: an event whose handler succeeded but whose
completion was never written will run again. Handlers are therefore required
to be idempotent, which is stated on the registry and tested.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.events.models import MAX_ERROR_LENGTH, EventStatus, OutboxEvent


class EventRepository:
    """Data access for the outbox. The only place its statements are built."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Writing ------------------------------------------------------------

    def enqueue(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        organization_id: uuid.UUID | None,
        available_at: dt.datetime | None = None,
        max_attempts: int = 5,
    ) -> OutboxEvent:
        """Add an event to the caller's **open transaction**.

        Deliberately not ``async`` and deliberately does not flush: it adds to
        the session and returns. The event becomes real when the caller's
        transaction commits, which is the entire guarantee this module exists
        to provide — a caller that wanted to commit the event separately would
        have to work at it.
        """
        event = OutboxEvent(
            event_type=event_type,
            payload=payload,
            organization_id=organization_id,
            available_at=available_at or dt.datetime.now(dt.UTC),
            max_attempts=max_attempts,
            status=EventStatus.PENDING,
        )
        self._session.add(event)
        return event

    # --- Claiming -----------------------------------------------------------

    async def claim(self, *, limit: int, now: dt.datetime) -> list[OutboxEvent]:
        """Take up to ``limit`` due events, exclusively.

        ``SKIP LOCKED`` is what makes concurrent workers safe. ``ORDER BY
        available_at`` keeps delivery roughly fair rather than starving old
        events behind a steady arrival of new ones.

        The caller must commit: until it does, the rows are locked and another
        worker sees none of them.
        """
        due = (
            select(OutboxEvent.id)
            .where(
                OutboxEvent.status == EventStatus.PENDING,
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.available_at.asc(), OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        ids = list((await self._session.execute(due)).scalars().all())
        if not ids:
            return []

        claimed = await self._session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id.in_(ids))
            .values(
                status=EventStatus.PROCESSING,
                claimed_at=now,
                attempts=OutboxEvent.attempts + 1,
            )
            .returning(OutboxEvent)
        )
        return list(claimed.scalars().all())

    async def reclaim_stalled(self, *, older_than: dt.datetime) -> int:
        """Return abandoned PROCESSING rows to the queue.

        A worker killed mid-attempt — a deploy, an OOM, a lost connection —
        leaves its claim behind. Without this the event would sit PROCESSING
        for ever and its email would never arrive, which is the failure mode
        an outbox exists to prevent.

        The attempt it was killed during is *not* refunded: it already counted,
        and a handler that reliably kills its worker should reach the
        dead-letter state rather than looping until someone notices.
        """
        result = await self._session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.status == EventStatus.PROCESSING,
                OutboxEvent.claimed_at < older_than,
            )
            .values(status=EventStatus.PENDING, claimed_at=None)
        )
        return int(cast("CursorResult[Any]", result).rowcount or 0)

    # --- Finishing ----------------------------------------------------------

    async def succeed(self, event_id: uuid.UUID, *, at: dt.datetime) -> None:
        await self._session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status=EventStatus.SUCCEEDED,
                processed_at=at,
                last_error=None,
                claimed_at=None,
            )
        )

    async def fail(
        self,
        event: OutboxEvent,
        *,
        error: str,
        retry_at: dt.datetime | None,
        at: dt.datetime,
    ) -> EventStatus:
        """Record a failed attempt, and either schedule a retry or dead-letter.

        ``retry_at`` of ``None`` means the caller has decided this event will
        never succeed — an unknown event type, a malformed payload — and there
        is no value in spending four more attempts to find that out again.
        """
        out_of_attempts = event.attempts >= event.max_attempts
        status = (
            EventStatus.DEAD if out_of_attempts or retry_at is None else EventStatus.PENDING
        )
        await self._session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event.id)
            .values(
                status=status,
                last_error=error[:MAX_ERROR_LENGTH],
                claimed_at=None,
                available_at=retry_at or event.available_at,
                processed_at=at if status is EventStatus.DEAD else None,
            )
        )
        return status

    # --- Reading ------------------------------------------------------------

    async def get(self, event_id: uuid.UUID) -> OutboxEvent | None:
        return await self._session.get(OutboxEvent, event_id)

    async def list_by_status(
        self, status: EventStatus, *, limit: int = 100
    ) -> Sequence[OutboxEvent]:
        result = await self._session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status == status)
            .order_by(OutboxEvent.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def count_pending(self, *, now: dt.datetime) -> int:
        """Depth of the queue. The number an operator watches."""
        result = await self._session.execute(
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.status == EventStatus.PENDING,
                OutboxEvent.available_at <= now,
            )
        )
        return int(result.scalar_one())


__all__ = ["EventRepository"]
