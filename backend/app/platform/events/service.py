"""The event registry and the dispatcher that drains the outbox.

Three rules, each load-bearing.

**A handler declares whether it is tenant-scoped, and the dispatcher enforces
it.** A tenant-scoped handler is run inside ``scope_session_to(organization)``
so every table it touches is still under RLS; it may not be registered without
an organization on the event, and an event that arrives without one
dead-letters rather than running unscoped. That is what keeps the outbox's own
RLS exemption (see ``models.py``) from widening into the tables it points at.

**Handlers must be idempotent.** Delivery is at-least-once by construction:
the claim commits before the work begins, so an event whose handler succeeded
and whose completion was lost will run again. Rather than pretend otherwise,
the contract says so and the tests exercise it.

**Backoff is exponential with jitter.** A provider outage otherwise produces a
retry storm that arrives in lockstep — every failed event in the batch
retrying at the same instant, repeatedly, against a service already in
trouble. The jitter spreads them; the exponent keeps a persistent failure from
consuming the worker.
"""

from __future__ import annotations

import datetime as dt
import random
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import apply_tenant_context
from app.core.tenant import TenantContext
from app.platform.events.models import EventStatus, OutboxEvent
from app.platform.events.repository import EventRepository

logger = structlog.get_logger(__name__)

#: Base of the backoff, in seconds. Attempt *n* waits ``BACKOFF_BASE ** n``
#: plus jitter: 2s, 4s, 8s, 16s, 32s across the default five attempts, which
#: spans a few minutes — long enough to ride out a provider blip, short enough
#: that a person waiting for an invitation is not left wondering.
BACKOFF_BASE: Final = 2
#: Ceiling, so a raised ``max_attempts`` cannot schedule a retry next week.
BACKOFF_MAX_SECONDS: Final = 3600
#: Up to this fraction of the delay is added at random.
BACKOFF_JITTER: Final = 0.25


class PermanentEventError(Exception):
    """The handler knows this event will never succeed.

    Raised for a payload that cannot be satisfied by retrying — a record that
    has since been deleted, a malformed field. Dead-letters immediately rather
    than spending the remaining attempts rediscovering the same answer.
    """


@dataclass(frozen=True, slots=True)
class EventHandler:
    """One registered handler, and the contract it is run under."""

    event_type: str
    handle: Callable[[AsyncSession, OutboxEvent], Awaitable[None]]
    #: When true the dispatcher scopes the session to ``event.organization_id``
    #: before calling, and refuses the event if it has none.
    tenant_scoped: bool


_HANDLERS: dict[str, EventHandler] = {}


def register_handler(
    event_type: str,
    handler: Callable[[AsyncSession, OutboxEvent], Awaitable[None]],
    *,
    tenant_scoped: bool,
) -> None:
    """Register ``handler`` for ``event_type``.

    Called from ``app/api/router.py``, the composition root — the one module
    allowed to see both layers, and therefore the only place a CRM handler can
    be attached to a Platform dispatcher without either importing the other.
    The same seam ``register_entity_access`` and ``register_reminder_source``
    already use.

    Re-registration replaces, so a reload in tests does not accumulate
    duplicate handlers and silently double every delivery.
    """
    _HANDLERS[event_type] = EventHandler(
        event_type=event_type, handle=handler, tenant_scoped=tenant_scoped
    )


def registered_handlers() -> dict[str, EventHandler]:
    """The registry, for tests and for the operator endpoint."""
    return dict(_HANDLERS)


def clear_handlers() -> None:
    """Empty the registry. Tests only."""
    _HANDLERS.clear()


def backoff_delay(attempt: int) -> dt.timedelta:
    """How long to wait before attempt ``attempt + 1``."""
    base = min(BACKOFF_BASE**max(attempt, 1), BACKOFF_MAX_SECONDS)
    # `random` and not `secrets`: this spreads load, it does not protect
    # anything, and a predictable jitter would still spread it.
    jitter = base * BACKOFF_JITTER * random.random()  # noqa: S311
    return dt.timedelta(seconds=base + jitter)


@dataclass(frozen=True, slots=True)
class DrainResult:
    """What one pass of the dispatcher did. Returned for logging and tests."""

    claimed: int
    succeeded: int
    retrying: int
    dead: int


class EventDispatcher:
    """Drains the outbox. One instance per worker process."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        batch_size: int = 20,
        stall_after_seconds: int = 300,
    ) -> None:
        self._session_factory = session_factory
        self._batch_size = batch_size
        self._stall_after = dt.timedelta(seconds=stall_after_seconds)

    async def drain_once(self, *, now: dt.datetime | None = None) -> DrainResult:
        """Claim a batch and run it. Returns without waiting if nothing is due."""
        moment = now or dt.datetime.now(dt.UTC)

        async with self._session_factory() as session:
            repository = EventRepository(session)
            reclaimed = await repository.reclaim_stalled(
                older_than=moment - self._stall_after
            )
            if reclaimed:
                logger.warning("outbox_events_reclaimed", count=reclaimed)
            events = await repository.claim(limit=self._batch_size, now=moment)
            # Committing here is what releases the row locks and publishes the
            # claim to other workers. Everything after this point is done
            # outside the claiming transaction, on purpose — see repository.py.
            await session.commit()

        succeeded = retrying = dead = 0
        for event in events:
            outcome = await self._run(event)
            if outcome is EventStatus.SUCCEEDED:
                succeeded += 1
            elif outcome is EventStatus.DEAD:
                dead += 1
            else:
                retrying += 1

        return DrainResult(
            claimed=len(events), succeeded=succeeded, retrying=retrying, dead=dead
        )

    async def _run(self, event: OutboxEvent) -> EventStatus:
        """Execute one event and record what happened to it."""
        handler = _HANDLERS.get(event.event_type)
        now = dt.datetime.now(dt.UTC)

        if handler is None:
            # A release removed the handler, or an event type was never
            # registered. Retrying cannot help.
            return await self._finish(
                event,
                error=f"No handler registered for '{event.event_type}'.",
                retry_at=None,
                now=now,
            )

        if handler.tenant_scoped and event.organization_id is None:
            return await self._finish(
                event,
                error=(
                    f"'{event.event_type}' is tenant-scoped but the event names "
                    "no organization."
                ),
                retry_at=None,
                now=now,
            )

        try:
            async with self._session_factory() as session:
                if event.organization_id is not None:
                    # The organization comes from the event column, never from
                    # the payload: the payload is data a caller wrote, and this
                    # decides which tenant's rows the handler can reach.
                    #
                    # Applied for untenanted handlers too when the event
                    # happens to name an organization — scoping is never the
                    # wrong direction, and it means a handler declared
                    # untenanted cannot accidentally read across tenants
                    # because somebody later gave its events an organization.
                    await apply_tenant_context(
                        session, TenantContext(organization_id=event.organization_id)
                    )
                await handler.handle(session, event)
                await session.commit()
        except PermanentEventError as failure:
            return await self._finish(
                event, error=str(failure) or repr(failure), retry_at=None, now=now
            )
        except Exception as failure:  # one event must not stop the queue
            logger.warning(
                "outbox_event_failed",
                event_id=str(event.id),
                event_type=event.event_type,
                attempt=event.attempts,
                exc_info=True,
            )
            return await self._finish(
                event,
                error=f"{type(failure).__name__}: {failure}",
                retry_at=now + backoff_delay(event.attempts),
                now=now,
            )

        async with self._session_factory() as session:
            await EventRepository(session).succeed(event.id, at=now)
            await session.commit()
        logger.info(
            "outbox_event_processed",
            event_id=str(event.id),
            event_type=event.event_type,
            attempt=event.attempts,
        )
        return EventStatus.SUCCEEDED

    async def _finish(
        self,
        event: OutboxEvent,
        *,
        error: str,
        retry_at: dt.datetime | None,
        now: dt.datetime,
    ) -> EventStatus:
        async with self._session_factory() as session:
            status = await EventRepository(session).fail(
                event, error=error, retry_at=retry_at, at=now
            )
            await session.commit()
        if status is EventStatus.DEAD:
            logger.error(
                "outbox_event_dead",
                event_id=str(event.id),
                event_type=event.event_type,
                attempts=event.attempts,
                error=error,
            )
        return status


def enqueue(
    session: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
    organization_id: uuid.UUID | None,
) -> OutboxEvent:
    """Add an event to ``session``'s open transaction.

    The seam a caller uses. Kept as a function rather than a service class
    because there is nothing to configure and the whole point is that it joins
    a transaction somebody else owns.
    """
    return EventRepository(session).enqueue(
        event_type=event_type, payload=payload, organization_id=organization_id
    )


__all__ = [
    "BACKOFF_BASE",
    "BACKOFF_JITTER",
    "BACKOFF_MAX_SECONDS",
    "DrainResult",
    "EventDispatcher",
    "EventHandler",
    "PermanentEventError",
    "backoff_delay",
    "clear_handlers",
    "enqueue",
    "register_handler",
    "registered_handlers",
]
