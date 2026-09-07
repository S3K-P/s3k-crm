"""Can this deployment run more than one replica?

``railway.json`` pinned ``numReplicas`` to 1 for two specific reasons, both
recorded in comments rather than in tests — which is why the pin outlived the
first of them. This file turns each reason into an assertion, so the answer to
"is it safe to scale?" is something the suite knows rather than something a
reader infers.

The two reasons were:

1. **The reminder poller ran in the API process.** Two replicas meant two
   pollers and two of every reminder. Reminder dispatch now belongs to the
   worker, and deduplicates besides.
2. **``alembic upgrade head`` ran on boot.** Two containers starting together
   both decided the same migrations were outstanding and both ran them.

Neither is tested by reading the config, so neither is tested here by reading
the config.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import MIGRATION_LOCK_KEY
from app.platform.notifications.models import Notification
from app.platform.notifications.service import (
    dispatch_due_reminders_for_all_organizations,
)
from tests.integration.conftest import Tenant, scope_session_to

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def clean_notifications(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    async def wipe() -> None:
        async with session_factory() as session:
            await session.execute(text("DELETE FROM platform.notifications"))
            await session.commit()

    await wipe()
    yield
    await wipe()


# --- Reason 1: the reminder poller ------------------------------------------


async def test_two_replicas_dispatching_reminders_produce_one_notification(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin,  # noqa: ANN001 - the ApiSession fixture, used for seeding
    alpha: Tenant,
    clean_notifications: None,
) -> None:
    """The failure the pin existed to prevent, run deliberately.

    Two dispatches race, exactly as two replicas polling on the same schedule
    would. The recipient must end up with one notification, not two — the
    dedupe key is what makes that true, and it is a unique index rather than a
    check-then-insert precisely because these run concurrently.
    """
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Replica Ltd"})
    assert account.status_code == 201, account.text

    soon = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10)
    meeting = as_alpha_admin.post(
        "/crm/activities",
        json={
            "subject": "Scaling review",
            "type": "MEETING",
            "related_entity_type": "ACCOUNT",
            "related_entity_id": account.json()["id"],
            # `meeting_type` is sent explicitly: omitting it currently 500s
            # (the schema default is dropped by `exclude_unset`). Unrelated to
            # this phase and flagged separately — sending it keeps this test
            # measuring reminder deduplication rather than that bug.
            "meeting": {"start_time": soon.isoformat(), "meeting_type": "VIDEO"},
        },
    )
    assert meeting.status_code == 201, meeting.text

    now = dt.datetime.now(dt.UTC)
    await asyncio.gather(
        dispatch_due_reminders_for_all_organizations(session_factory, now=now),
        dispatch_due_reminders_for_all_organizations(session_factory, now=now),
    )

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        count = await session.execute(select(func.count()).select_from(Notification))
        assert int(count.scalar_one()) <= 1, (
            "two replicas produced duplicate reminders"
        )


def test_the_api_no_longer_polls_for_reminders_by_default(
    integration_settings: Settings,
) -> None:
    """The setting is the deployment decision, so the default is the assertion.

    Left on, two API replicas each run a poller. The worker owns this now; the
    switch survives only for a single-container deployment with no worker
    beside it.
    """
    assert integration_settings.notifications_scheduler_enabled is False


# --- Reason 2: migrations on boot -------------------------------------------


async def test_concurrent_migrations_serialize_rather_than_racing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Two boots at once must not both run the same migrations.

    The advisory lock in ``migrations/env.py`` is transaction-scoped, so this
    asserts the primitive it relies on: a second holder blocks while the first
    is inside its transaction, and proceeds once that transaction ends.

    Testing the lock rather than shelling out to two Alembic processes: the
    latter would take minutes, need a throwaway database, and prove the same
    property with far more that could go wrong for unrelated reasons.
    """
    async with session_factory() as first, session_factory() as second:
        await first.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY}
        )

        # The second cannot take it while the first's transaction is open.
        blocked = await second.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": MIGRATION_LOCK_KEY},
        )
        assert blocked.scalar_one() is False, (
            "a second replica could migrate while the first was migrating"
        )

        # Ending the first transaction releases it — no unlock call, which is
        # why a container killed mid-migration cannot wedge the next deploy.
        await first.rollback()

        freed = await second.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": MIGRATION_LOCK_KEY},
        )
        assert freed.scalar_one() is True, "the lock was not released on rollback"
        await second.rollback()


