"""The transactional outbox and its dispatcher.

Real PostgreSQL, because every guarantee here is a database guarantee. The
transactional property is a transaction; the concurrency property is ``FOR
UPDATE SKIP LOCKED``; the tenant property is RLS. A fake would assert my idea
of all three.

Grouped by the promise each set holds:

**An event is exactly as real as the change it describes.** Rolled back with
it, committed with it. This is the whole reason the outbox exists rather than
publishing to Redis inside a request, and it is the first thing that would
quietly stop being true.

**A worker that dies does not lose work.** Claims are abandoned, reclaimed and
retried, and an event that will never succeed stops rather than looping.

**Two workers do not do the same work twice.** The property that lets the
deployment scale past one replica, which is the operational reason this phase
exists at all.

**A handler cannot read another tenant's rows**, even though the outbox itself
is RLS-exempt.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.events.models import EventStatus, OutboxEvent
from app.platform.events.repository import EventRepository
from app.platform.events.service import (
    EventDispatcher,
    PermanentEventError,
    backoff_delay,
    clear_handlers,
    enqueue,
    register_handler,
    registered_handlers,
)
from app.products.crm.accounts.models import Account
from tests.integration.conftest import Tenant, scope_session_to

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _isolate_handlers() -> Iterator[None]:
    """Every test registers its own handlers and leaves none behind.

    The registry is module state; without this the third test in the file
    inherits the first one's handler and passes for the wrong reason.
    """
    existing = registered_handlers()
    clear_handlers()
    yield
    clear_handlers()
    for handler in existing.values():
        register_handler(
            handler.event_type, handler.handle, tenant_scoped=handler.tenant_scoped
        )


@pytest_asyncio.fixture
async def outbox(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    """Empty the outbox around each test.

    Not in ``conftest``'s cleanup list because the table is RLS-exempt: the
    tenant-scoped DELETEs there would match every row of it once per
    organization, which works but reads as though the table were tenant-scoped
    when the point of it is that it is not.
    """
    async with session_factory() as session:
        await session.execute(text("DELETE FROM platform.outbox_events"))
        await session.commit()
    yield
    async with session_factory() as session:
        await session.execute(text("DELETE FROM platform.outbox_events"))
        await session.commit()


def _dispatcher(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch_size: int = 20,
    stall_after_seconds: int = 300,
) -> EventDispatcher:
    return EventDispatcher(
        session_factory, batch_size=batch_size, stall_after_seconds=stall_after_seconds
    )


async def _statuses(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[EventStatus, int]]:
    async with session_factory() as session:
        rows = await session.execute(select(OutboxEvent.status, OutboxEvent.attempts))
        return [(status, attempts) for status, attempts in rows.all()]


# --- The transactional promise ----------------------------------------------


async def test_an_event_rolled_back_with_its_transaction_is_never_delivered(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    """The reason this is an outbox and not a queue publish.

    A publish inside a request succeeds whether or not the transaction
    commits, so a failed write can still send "your invitation is ready" for
    an invitation nobody has.
    """
    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        enqueue(
            session,
            event_type="test.rolled_back",
            payload={"id": str(uuid.uuid4())},
            organization_id=alpha.organization_id,
        )
        await session.rollback()

    assert await _statuses(session_factory) == []


async def test_an_event_committed_with_its_transaction_is_delivered(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    """And the other half: a committed change always has its event.

    The account is created and the event enqueued in one transaction, which is
    how a caller is meant to use this.
    """
    seen: list[str] = []

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        account = await session.get(Account, uuid.UUID(event.payload["account_id"]))
        assert account is not None, "the handler must see the row its event describes"
        seen.append(account.name)

    register_handler("test.account_created", handler, tenant_scoped=True)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        account = Account(name="Outbox Ltd", organization_id=alpha.organization_id)
        session.add(account)
        await session.flush()
        enqueue(
            session,
            event_type="test.account_created",
            payload={"account_id": str(account.id)},
            organization_id=alpha.organization_id,
        )
        await session.commit()

    result = await _dispatcher(session_factory).drain_once()

    assert result.claimed == 1
    assert result.succeeded == 1
    assert seen == ["Outbox Ltd"]


# --- Failure, retry and the dead-letter state -------------------------------


async def test_a_failing_handler_is_retried_with_a_growing_delay(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    attempts: list[int] = []

    async def flaky(session: AsyncSession, event: OutboxEvent) -> None:
        attempts.append(event.attempts)
        raise RuntimeError("the provider is unwell")

    register_handler("test.flaky", flaky, tenant_scoped=True)
    await _enqueue_one(session_factory, alpha, "test.flaky")

    first = await _dispatcher(session_factory).drain_once()

    assert first.retrying == 1
    async with session_factory() as session:
        event = (await session.execute(select(OutboxEvent))).scalar_one()
        assert event.status is EventStatus.PENDING
        assert event.attempts == 1
        assert "the provider is unwell" in (event.last_error or "")
        # Scheduled into the future, so the next poll does not pick it up
        # immediately and turn a provider outage into a tight loop.
        assert event.available_at > dt.datetime.now(dt.UTC)


async def test_an_event_out_of_attempts_is_dead_lettered(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    """Stops, and keeps its payload and its last error where an operator looks."""

    async def always_fails(session: AsyncSession, event: OutboxEvent) -> None:
        raise RuntimeError("still unwell")

    register_handler("test.doomed", always_fails, tenant_scoped=True)
    await _enqueue_one(session_factory, alpha, "test.doomed", max_attempts=2)

    dispatcher = _dispatcher(session_factory)
    # Each pass runs with `now` pushed forward so the backoff has elapsed.
    later = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    await dispatcher.drain_once()
    second = await dispatcher.drain_once(now=later)

    assert second.dead == 1
    async with session_factory() as session:
        event = (await session.execute(select(OutboxEvent))).scalar_one()
        assert event.status is EventStatus.DEAD
        assert event.attempts == 2
        assert event.payload != {}, "the payload survives, or the failure is unreadable"
        assert "still unwell" in (event.last_error or "")


async def test_a_permanent_failure_stops_immediately(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    """No value in four more attempts to rediscover the same answer."""

    async def gone(session: AsyncSession, event: OutboxEvent) -> None:
        raise PermanentEventError("the record was deleted")

    register_handler("test.gone", gone, tenant_scoped=True)
    await _enqueue_one(session_factory, alpha, "test.gone", max_attempts=5)

    result = await _dispatcher(session_factory).drain_once()

    assert result.dead == 1
    async with session_factory() as session:
        event = (await session.execute(select(OutboxEvent))).scalar_one()
        assert event.attempts == 1, "dead after one attempt, not five"


async def test_an_unregistered_event_type_dead_letters_rather_than_looping(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    """A release removed the handler; the event must not retry for ever."""
    await _enqueue_one(session_factory, alpha, "test.no_such_handler")

    result = await _dispatcher(session_factory).drain_once()

    assert result.dead == 1
    async with session_factory() as session:
        event = (await session.execute(select(OutboxEvent))).scalar_one()
        assert "No handler registered" in (event.last_error or "")


def test_backoff_grows_and_is_jittered() -> None:
    """Lockstep retries are how a struggling provider gets a thundering herd."""
    first = [backoff_delay(1).total_seconds() for _ in range(20)]
    later = backoff_delay(5).total_seconds()

    assert min(first) >= 2
    assert len(set(first)) > 1, "identical delays would arrive in lockstep"
    assert later > max(first)


# --- Crash recovery ---------------------------------------------------------


async def test_a_claim_abandoned_by_a_dead_worker_is_reclaimed(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    """The failure an outbox exists to survive.

    A worker killed mid-attempt leaves its row PROCESSING. Without reclaim the
    event sits there for ever and its email never arrives — silently, which is
    the worst version.
    """
    delivered: list[str] = []

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        delivered.append(event.event_type)

    register_handler("test.abandoned", handler, tenant_scoped=True)
    await _enqueue_one(session_factory, alpha, "test.abandoned")

    # Claim it and then vanish, exactly as a killed worker does.
    async with session_factory() as session:
        claimed = await EventRepository(session).claim(
            limit=10, now=dt.datetime.now(dt.UTC)
        )
        await session.commit()
    assert len(claimed) == 1

    # Nothing to do: the row is PROCESSING, not PENDING.
    assert (await _dispatcher(session_factory).drain_once()).claimed == 0

    # Once past the stall window it comes back and is delivered.
    recovered = await _dispatcher(session_factory, stall_after_seconds=0).drain_once()

    assert recovered.claimed == 1
    assert delivered == ["test.abandoned"]


async def test_a_reclaimed_event_does_not_get_its_attempt_back(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    """A handler that reliably kills its worker must still reach the DLQ.

    Refunding the attempt would let such an event loop for ever, which is the
    thing the attempt limit exists to prevent.
    """

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        return None

    register_handler("test.stalled", handler, tenant_scoped=True)
    await _enqueue_one(session_factory, alpha, "test.stalled")

    async with session_factory() as session:
        await EventRepository(session).claim(limit=10, now=dt.datetime.now(dt.UTC))
        await session.commit()

    await _dispatcher(session_factory, stall_after_seconds=0).drain_once()

    async with session_factory() as session:
        event = (await session.execute(select(OutboxEvent))).scalar_one()
        assert event.attempts == 2, "the abandoned attempt still counted"


# --- Concurrency: the reason the deployment can scale -----------------------


async def test_two_workers_never_claim_the_same_event(
    session_factory: async_sessionmaker[AsyncSession], alpha: Tenant, outbox: None
) -> None:
    """``FOR UPDATE SKIP LOCKED``, which is the whole horizontal-scaling story.

    Two dispatchers drain concurrently. Every event must be handled exactly
    once across both — if this failed, raising `numReplicas` would double every
    email the product sends.
    """
    handled: list[str] = []

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        handled.append(str(event.id))

    register_handler("test.concurrent", handler, tenant_scoped=True)
    for _ in range(12):
        await _enqueue_one(session_factory, alpha, "test.concurrent")

    left = _dispatcher(session_factory, batch_size=5)
    right = _dispatcher(session_factory, batch_size=5)
    await asyncio.gather(
        left.drain_once(), right.drain_once(), left.drain_once(), right.drain_once()
    )

    assert len(handled) == len(set(handled)), "an event was handled twice"

    statuses = await _statuses(session_factory)
    assert all(attempts <= 1 for _, attempts in statuses), (
        "an event was claimed more than once"
    )


# --- Tenant isolation -------------------------------------------------------


async def test_a_tenant_scoped_handler_cannot_read_another_organization(
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
    beta: Tenant,
    outbox: None,
) -> None:
    """The outbox is RLS-exempt; the tables a handler touches are not.

    The handler is given beta's account id on an event that names *alpha*. It
    must see nothing — the session is scoped from the event's organization
    column, and the account table's policy does the rest.
    """
    async with session_factory() as session:
        await scope_session_to(session, beta.organization_id)
        secret = Account(name="Beta Secrets", organization_id=beta.organization_id)
        session.add(secret)
        await session.commit()
        secret_id = secret.id

    found: list[Account | None] = []

    async def peeker(session: AsyncSession, event: OutboxEvent) -> None:
        found.append(await session.get(Account, uuid.UUID(event.payload["account_id"])))

    register_handler("test.peek", peeker, tenant_scoped=True)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        enqueue(
            session,
            event_type="test.peek",
            payload={"account_id": str(secret_id)},
            organization_id=alpha.organization_id,
        )
        await session.commit()

    await _dispatcher(session_factory).drain_once()

    assert found == [None], "a handler reached across the tenant boundary"


async def test_a_tenant_scoped_handler_refuses_an_event_with_no_organization(
    session_factory: async_sessionmaker[AsyncSession], outbox: None
) -> None:
    """Running it unscoped would read every tenant's rows at once.

    Dead-lettered rather than retried: the event is malformed and no number of
    attempts changes that.
    """
    ran = False

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        nonlocal ran
        ran = True

    register_handler("test.needs_tenant", handler, tenant_scoped=True)

    async with session_factory() as session:
        enqueue(
            session,
            event_type="test.needs_tenant",
            payload={},
            organization_id=None,
        )
        await session.commit()

    result = await _dispatcher(session_factory).drain_once()

    assert result.dead == 1
    assert ran is False


async def test_an_untenanted_handler_runs_without_an_organization(
    session_factory: async_sessionmaker[AsyncSession], outbox: None
) -> None:
    """Password reset is the real case: no tenant has been chosen yet."""
    ran = False

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        nonlocal ran
        ran = True

    register_handler("test.untenanted", handler, tenant_scoped=False)

    async with session_factory() as session:
        enqueue(
            session, event_type="test.untenanted", payload={}, organization_id=None
        )
        await session.commit()

    result = await _dispatcher(session_factory).drain_once()

    assert result.succeeded == 1
    assert ran is True


# --- Helpers ----------------------------------------------------------------


async def _enqueue_one(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: Tenant,
    event_type: str,
    *,
    max_attempts: int = 5,
) -> None:
    async with session_factory() as session:
        await scope_session_to(session, tenant.organization_id)
        EventRepository(session).enqueue(
            event_type=event_type,
            payload={"marker": event_type},
            organization_id=tenant.organization_id,
            max_attempts=max_attempts,
        )
        await session.commit()
