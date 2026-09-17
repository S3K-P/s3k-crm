"""Level 2 — predictive recommendations from the organization's own closed deals.

"Deals like this one were won more often when a technical workshop happened
before the proposal — schedule one." That sentence is only honest if it is
measured, so this module measures it: among closed deals in the same value
band (or, when too few exist, every closed deal), it compares the win rate of
deals that followed a practice with the win rate of those that did not, and
recommends the practice to an open deal that has not followed it only when

* both groups have at least ``MIN_GROUP_SIZE`` deals,
* the practice's win rate is at least ``MIN_UPLIFT_POINTS`` higher, and
* a two-proportion z-test puts the difference past ``MIN_Z`` —

and it reports the result as a confidence, with the sample sizes in the reason.
With too little history it recommends nothing, rather than a guess.

Pure: history arrives as plain values (``nba_collect.py`` loads it).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.products.crm.ai_insights.nba_catalog import ACTIONS
from app.products.crm.ai_insights.nba_rules import RecommendedAction, SignalEvidence

MIN_GROUP_SIZE = 5
MIN_UPLIFT_POINTS = 15.0
MIN_Z = 1.28  # ~80% one-sided

#: Currency-agnostic deal-value bands — the same stated simplification the
#: rule-based priority score makes (see ``prioritization.py``).
VALUE_BANDS: tuple[tuple[Decimal, Decimal | None, str], ...] = (
    (Decimal(0), Decimal(500_000), "under 5,00,000"),
    (Decimal(500_000), Decimal(2_000_000), "5,00,000 to 20,00,000"),
    (Decimal(2_000_000), Decimal(10_000_000), "20,00,000 to 1,00,00,000"),
    (Decimal(10_000_000), None, "over 1,00,00,000"),
)


@dataclass(frozen=True, slots=True)
class Practice:
    key: str
    #: Completes "Similar deals that ___ won …".
    phrase: str
    action_code: str
    #: Only meaningful before the proposal goes out.
    before_proposal: bool


PRACTICES: tuple[Practice, ...] = (
    Practice(
        "workshop_before_proposal",
        "held a technical workshop before the proposal",
        "SCHEDULE_TECHNICAL_WORKSHOP",
        True,
    ),
    Practice(
        "demo_before_proposal",
        "held a product demo before the proposal",
        "SCHEDULE_PRODUCT_DEMO",
        True,
    ),
    Practice(
        "executive_meeting",
        "held an executive alignment meeting",
        "SCHEDULE_EXECUTIVE_ALIGNMENT",
        False,
    ),
)


@dataclass(frozen=True, slots=True)
class ClosedDeal:
    won: bool
    band: int | None
    practices: frozenset[str]


def value_band(value: Decimal | float | None) -> int | None:
    if value is None:
        return None
    amount = Decimal(str(value))
    for index, (low, high, _) in enumerate(VALUE_BANDS):
        if amount >= low and (high is None or amount < high):
            return index
    return None


def _pool(band: int | None, history: Sequence[ClosedDeal]) -> tuple[list[ClosedDeal], str]:
    if band is not None:
        similar = [deal for deal in history if deal.band == band]
        if len(similar) >= 2 * MIN_GROUP_SIZE:
            return similar, f"deals of {VALUE_BANDS[band][2]}"
    return list(history), "closed deals"


def similar_win_rate(band: int | None, history: Sequence[ClosedDeal]) -> tuple[int, int] | None:
    """``(win rate %, sample size)`` of the comparable pool, when it is large enough."""
    pool, _ = _pool(band, history)
    if len(pool) < 2 * MIN_GROUP_SIZE:
        return None
    won = sum(1 for deal in pool if deal.won)
    return round(won / len(pool) * 100), len(pool)


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def predict(
    *,
    band: int | None,
    done: frozenset[str],
    past_proposal: bool,
    history: Sequence[ClosedDeal],
) -> list[RecommendedAction]:
    """Practices that measurably raise the win rate and this deal has not followed."""
    pool, pool_label = _pool(band, history)
    recommendations: list[RecommendedAction] = []
    for practice in PRACTICES:
        if practice.key in done or (practice.before_proposal and past_proposal):
            continue
        with_practice = [deal for deal in pool if practice.key in deal.practices]
        without = [deal for deal in pool if practice.key not in deal.practices]
        n1, n2 = len(with_practice), len(without)
        if n1 < MIN_GROUP_SIZE or n2 < MIN_GROUP_SIZE:
            continue
        won1 = sum(1 for deal in with_practice if deal.won)
        won2 = sum(1 for deal in without if deal.won)
        p1, p2 = won1 / n1, won2 / n2
        uplift = (p1 - p2) * 100
        if uplift < MIN_UPLIFT_POINTS:
            continue
        pooled = (won1 + won2) / (n1 + n2)
        se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
        if se == 0:
            continue
        z = (p1 - p2) / se
        if z < MIN_Z:
            continue
        action = ACTIONS[practice.action_code]
        recommendations.append(
            RecommendedAction(
                action_code=action.code,
                category=action.category.value,
                label=action.label,
                execution=action.execution.value,
                copilot=action.copilot.value if action.copilot else None,
                priority="HIGH" if uplift >= 30 else "MEDIUM",
                level="PREDICTIVE",
                reasons=(
                    f"Similar {pool_label} that {practice.phrase} were won {p1:.0%} of the time "
                    f"({n1} deals) versus {p2:.0%} without ({n2} deals).",
                ),
                rule_keys=(f"predictive.{practice.key}",),
                signals=(
                    SignalEvidence("win_rate_with", "Win rate with this practice", f"{p1:.0%}"),
                    SignalEvidence("win_rate_without", "Win rate without it", f"{p2:.0%}"),
                    SignalEvidence("sample_size", "Closed deals compared", str(n1 + n2)),
                ),
                confidence=min(99, round(_normal_cdf(z) * 100)),
                first_position=10_000,
                extra={
                    "win_rate_with": round(p1 * 100),
                    "win_rate_without": round(p2 * 100),
                    "sample_with": n1,
                    "sample_without": n2,
                },
            )
        )
    return recommendations


__all__ = [
    "MIN_GROUP_SIZE",
    "PRACTICES",
    "VALUE_BANDS",
    "ClosedDeal",
    "Practice",
    "predict",
    "similar_win_rate",
    "value_band",
]
