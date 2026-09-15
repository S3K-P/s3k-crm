"""List/pagination latency baseline for the shared CRM list path (Checkpoint 8, item #72).

Same technique and the same reasoning as ``test_search_performance.py`` — a
**baseline, not a benchmark**: it catches a change of *shape* (an index
stops being used, a join turns into N+1 queries) rather than asserting a
tight SLO that would be flaky across machines. See that file's own
docstring for the full rationale; it is not repeated here.

Accounts specifically, because ``list_accounts`` exercises the identical
``TenantScopedService`` list path (pagination, sorting, the advanced-filter
query builder, custom-field participation) that contacts, leads and
opportunities all share — a regression in that shared code shows up here
the same way it would on any of the four.
"""

from __future__ import annotations

import statistics
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.conftest import ApiSession, Tenant, scope_session_to

pytestmark = pytest.mark.integration

#: Enough rows that pagination and sorting are measured against a real index
#: walk rather than a handful of rows the planner would seq-scan regardless.
SEEDED_ACCOUNTS = 5_000

SAMPLES = 20

#: Ten times a generous 300 ms SLO for a paginated list read — deliberately
#: loose, matching the search baseline's own ceiling philosophy.
STRUCTURAL_CEILING_MS = 3_000.0


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        await scope_session_to(session, organization_id)
        await session.execute(
            text(
                """
                INSERT INTO crm.accounts (organization_id, name, industry, owner_id)
                SELECT :org,
                       'Perf Account ' || g,
                       'Industry ' || (g % 40),
                       NULL
                FROM generate_series(1, :n) g
                """
            ),
            {"org": organization_id, "n": SEEDED_ACCOUNTS},
        )
        await session.commit()

    async with session_factory() as session:
        connection = await session.connection(
            execution_options={"isolation_level": "AUTOCOMMIT"}
        )
        await connection.execute(text("VACUUM ANALYZE crm.accounts"))


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def _measure(session: ApiSession, params: dict[str, object]) -> list[float]:
    durations: list[float] = []
    for _ in range(SAMPLES):
        started = time.perf_counter()
        response = session.get("/crm/accounts", params=params)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        assert response.status_code == 200, response.text
        durations.append(elapsed_ms)
    return durations


#: The three request shapes a real list screen actually makes, and the
#: total each should find — the seed spreads accounts evenly across 40
#: industry buckets, so a filtered shape legitimately sees a fraction of
#: the total rather than all of it.
SHAPES: list[tuple[str, dict[str, object], int]] = [
    ("first-page-default-sort", {"page": 1, "page_size": 25}, SEEDED_ACCOUNTS),
    (
        "deep-page-explicit-sort",
        {"page": 150, "page_size": 25, "sort_by": "name", "sort_dir": "asc"},
        SEEDED_ACCOUNTS,
    ),
    (
        "filtered-by-industry",
        {"page": 1, "page_size": 25, "industry": "Industry 7"},
        SEEDED_ACCOUNTS // 40,
    ),
]


async def test_account_list_latency_baseline(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await _seed(session_factory, alpha.organization_id)

    measurements: list[tuple[str, float, float]] = []
    failures: list[str] = []

    for label, params, expected_total in SHAPES:
        first = as_alpha_admin.get("/crm/accounts", params=params)
        assert first.status_code == 200, first.text
        assert first.json()["pagination"]["total"] == expected_total

        samples = _measure(as_alpha_admin, params)
        p50 = statistics.median(samples)
        p95 = _percentile(samples, 0.95)
        measurements.append((label, p50, p95))

        if p95 >= STRUCTURAL_CEILING_MS:
            failures.append(f"{label} p95={p95:.0f}ms")

    with capsys.disabled():
        for label, p50, p95 in measurements:
            print(
                f"\n[account list latency] {label:<24} n={SEEDED_ACCOUNTS} "
                f"p50={p50:7.1f}ms p95={p95:7.1f}ms "
                f"(structural ceiling {STRUCTURAL_CEILING_MS:.0f}ms)"
            )

    assert not failures, (
        f"far above the {STRUCTURAL_CEILING_MS:.0f}ms structural ceiling: "
        f"{', '.join(failures)}. Likely an unindexed sort/filter column or "
        "an N+1 introduced in the list serializer."
    )
