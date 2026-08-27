"""Search latency baseline (`P3-W20-QA-02`).

Doc 10 sets the revisit trigger for a dedicated search engine at ">1M
searchable records or p95 > 200 ms". This records the second number, so the
trigger is measured rather than assumed.

It is a **baseline, not a benchmark**. It runs on whatever machine the suite
runs on, against a few thousand rows rather than a million, so the absolute
number is not comparable between a laptop and CI. What it catches is a change
of *shape*: a query that stops using its index goes from single-digit to
hundreds of milliseconds, and no plausible hardware difference explains that.
The assertion threshold is therefore far above the SLO — a failure here means
something structural broke, not that the machine was busy. The measured p95 is
printed for recording in the plan.

The seeding is worth a note of its own. Rows are inserted with raw SQL, and
their ``search_vector`` is populated anyway, because it is a generated column
rather than something a trigger or the application fills in. That is the
property that makes bulk imports searchable without a reindex step, and this
file exercises it incidentally.
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

#: Enough rows that a sequential scan is measurably slower than an index
#: lookup, but not so many that seeding dominates the suite's runtime.
SEEDED_ACCOUNTS = 4_000

#: Requests per query shape. The first call pays for connection warm-up and
#: plan caching that later ones do not, which is why p95 rather than max is
#: the reported figure.
SAMPLES = 20

#: Ten times doc 10's 200 ms SLO. Deliberately loose: this asserts "the index
#: is being used", not "this laptop is fast".
STRUCTURAL_CEILING_MS = 2_000.0

#: The one distinctive record every query shape is aimed at, so a match is
#: never accidental.
NEEDLE = "Zephyrine Holdings"


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        # `crm.accounts` is RLS-FORCEd, so the bulk INSERT is refused outright
        # without a tenant scope on the session.
        await scope_session_to(session, organization_id)
        await session.execute(
            text(
                """
                INSERT INTO crm.accounts (organization_id, name, industry, description)
                SELECT :org,
                       'Benchmark Firm ' || g || ' ' || md5(g::text),
                       'Industry ' || (g % 40),
                       'Filler description for row ' || g
                FROM generate_series(1, :n) g
                """
            ),
            {"org": organization_id, "n": SEEDED_ACCOUNTS},
        )
        await session.execute(
            text("INSERT INTO crm.accounts (organization_id, name) VALUES (:org, :name)"),
            {"org": organization_id, "name": NEEDLE},
        )
        await session.commit()

    # VACUUM cannot run inside a transaction, hence the separate AUTOCOMMIT
    # connection. It is not optional: a freshly bulk-loaded GIN index still has
    # its entries in the pending list, and the planner costs a scan of that
    # list highly enough to decline the index altogether. Skipping this
    # measures the seeding strategy rather than the query.
    async with session_factory() as session:
        connection = await session.connection(
            execution_options={"isolation_level": "AUTOCOMMIT"}
        )
        await connection.execute(text("VACUUM ANALYZE crm.accounts"))


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def _measure(session: ApiSession, query: str) -> list[float]:
    durations: list[float] = []
    for _ in range(SAMPLES):
        started = time.perf_counter()
        response = session.get("/crm/search", params={"q": query})
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        assert response.status_code == 200, response.text
        durations.append(elapsed_ms)
    return durations


#: The three query shapes, and whether each should find :data:`NEEDLE`.
#: Correctness is asserted beside the timing because a query matching nothing
#: is fast for uninteresting reasons.
SHAPES: list[tuple[str, str, bool]] = [
    # Whole-word match, served by the GIN index on search_vector.
    ("full-text", "zephyrine", True),
    # Prefix, served by the trigram index — the branch full-text cannot do.
    ("fuzzy-prefix", "zephyrin", True),
    # Matches nothing: both indexes must return early rather than fall back to
    # a scan.
    ("no-match", "qqqzzzxxx", False),
]


async def test_search_latency_baseline(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """All three shapes in one test, against one seeding.

    Deliberately not parametrized. ``clean_database`` truncates between tests,
    so a parametrized version re-inserts 4 000 rows and re-runs ``VACUUM
    ANALYZE`` for each case — three times the setup to measure three queries
    that share it. With no CI, this suite is the project's only gate, and
    minutes spent here are minutes nobody waits for it.
    """
    await _seed(session_factory, alpha.organization_id)

    measurements: list[tuple[str, float, float]] = []
    failures: list[str] = []

    for label, query, expect_hit in SHAPES:
        first = as_alpha_admin.get("/crm/search", params={"q": query})
        assert first.status_code == 200, first.text
        titles = [hit["title"] for hit in first.json()["hits"]]
        assert (NEEDLE in titles) is expect_hit, f"{label}: {titles}"

        samples = _measure(as_alpha_admin, query)
        p50 = statistics.median(samples)
        p95 = _percentile(samples, 0.95)
        measurements.append((label, p50, p95))

        if p95 >= STRUCTURAL_CEILING_MS:
            failures.append(f"{label} p95={p95:.0f}ms")

    with capsys.disabled():
        for label, p50, p95 in measurements:
            print(
                f"\n[search latency] {label:<13} n={SEEDED_ACCOUNTS} "
                f"p50={p50:7.1f}ms p95={p95:7.1f}ms "
                f"(SLO 200ms, structural ceiling {STRUCTURAL_CEILING_MS:.0f}ms)"
            )

    # Reported together so one slow shape does not hide another: a failure
    # here is diagnostic, and knowing whether it is one index or both is the
    # first question anyone asks.
    assert not failures, (
        f"far above the {STRUCTURAL_CEILING_MS:.0f}ms structural ceiling: "
        f"{', '.join(failures)}. The query has most likely stopped using its "
        "index — check that the trigram index expression still matches "
        "_display_name()."
    )
