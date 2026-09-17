"""Dashboard summary aggregation latency baseline (Checkpoint 8, item #72).

Same "baseline, not benchmark" technique as ``test_search_performance.py``.
``GET /crm/dashboard/summary`` is the highest-risk aggregate endpoint in the
product: it computes pipeline-by-stage, a 6-month revenue trend,
pipeline-by-owner and lead-source performance in one response, each its own
query — exactly the shape that quietly grows an N+1 (one query per stage, per
owner, per month) as the feature accretes without anyone noticing on a
lightly-seeded dev database.
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

SEEDED_ACCOUNTS = 500
#: Deals per account, so the pipeline/owner/source aggregates all have real
#: volume to group over rather than a handful of rows.
SEEDED_OPPORTUNITIES = 3_000

SAMPLES = 15

#: Generous relative to a single-page read: this endpoint does several
#: aggregate queries in one response, so its own honest baseline is higher
#: than a plain list — the ceiling stays proportionally generous, not tight.
STRUCTURAL_CEILING_MS = 4_000.0


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        await scope_session_to(session, organization_id)

        await session.execute(
            text(
                """
                INSERT INTO crm.accounts (organization_id, name)
                SELECT :org, 'Dashboard Perf Account ' || g
                FROM generate_series(1, :n) g
                """
            ),
            {"org": organization_id, "n": SEEDED_ACCOUNTS},
        )

        stage_id = (
            await session.execute(
                text(
                    "SELECT id FROM crm.pipeline_stages "
                    "WHERE organization_id = :org ORDER BY sort_order LIMIT 1"
                ),
                {"org": organization_id},
            )
        ).scalar_one()

        # Every opportunity needs a real account_id; spreading them evenly
        # across the seeded accounts (rather than one shared account) is what
        # makes pipeline-by-owner and revenue-trend actually have many
        # distinct groups to aggregate over.
        await session.execute(
            text(
                """
                INSERT INTO crm.opportunities
                    (organization_id, name, account_id, stage_id, deal_value,
                     expected_close_date)
                SELECT :org,
                       'Perf Deal ' || g,
                       (SELECT id FROM crm.accounts
                        WHERE organization_id = :org
                        ORDER BY id OFFSET (g % :n_accounts) LIMIT 1),
                       :stage_id,
                       (1000 + g % 500000)::numeric,
                       CURRENT_DATE + ((g % 90) || ' days')::interval
                FROM generate_series(1, :n_deals) g
                """
            ),
            {
                "org": organization_id,
                "n_accounts": SEEDED_ACCOUNTS,
                "stage_id": stage_id,
                "n_deals": SEEDED_OPPORTUNITIES,
            },
        )
        await session.commit()

    async with session_factory() as session:
        connection = await session.connection(
            execution_options={"isolation_level": "AUTOCOMMIT"}
        )
        await connection.execute(text("VACUUM ANALYZE crm.accounts"))
        await connection.execute(text("VACUUM ANALYZE crm.opportunities"))


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


async def test_dashboard_summary_latency_baseline(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    capsys: pytest.CaptureFixture[str],
) -> None:
    await _seed(session_factory, alpha.organization_id)

    first = as_alpha_admin.get("/crm/dashboard/summary")
    assert first.status_code == 200, first.text
    body = first.json()
    assert sum(stage["count"] for stage in body["pipeline"]) >= SEEDED_OPPORTUNITIES

    durations: list[float] = []
    for _ in range(SAMPLES):
        started = time.perf_counter()
        response = as_alpha_admin.get("/crm/dashboard/summary")
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        assert response.status_code == 200, response.text
        durations.append(elapsed_ms)

    p50 = statistics.median(durations)
    p95 = _percentile(durations, 0.95)

    with capsys.disabled():
        print(
            f"\n[dashboard summary latency] accounts={SEEDED_ACCOUNTS} "
            f"deals={SEEDED_OPPORTUNITIES} p50={p50:7.1f}ms p95={p95:7.1f}ms "
            f"(structural ceiling {STRUCTURAL_CEILING_MS:.0f}ms)"
        )

    assert p95 < STRUCTURAL_CEILING_MS, (
        f"dashboard summary p95={p95:.0f}ms is far above the "
        f"{STRUCTURAL_CEILING_MS:.0f}ms structural ceiling — likely one of "
        "the per-stage/per-owner/per-month aggregates turned into a "
        "per-row query instead of a single grouped one."
    )
