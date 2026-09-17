"""Rule-based lead/deal prioritization (§12) — deliberately not an AI call.

The checkpoint brief is explicit that a priority score must separate "CRM
factors" from "AI-interpreted signals" and must not present a made-up
"objective" score. The only way to make that true rather than merely claimed
is to compute the score from real, named CRM fields in ordinary Python —
never from a model's guess — and to make every one of its reasons a fact a
caller could check by opening the record.

This also keeps the feature cheap (§15, §23): scoring a page of leads or
deals costs the same handful of SQL queries a list screen already pays, no
provider call at all. An AI call only enters at ``explain`` — a short
narration of a score already computed here, "rules first, AI explanation
second" exactly as the checkpoint's own audit of item #10 describes.

Every function here is pure: given the facts, compute the score. No session,
no I/O, so the logic is exercised directly by unit tests without a database.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

PriorityLevel = str  # "HIGH" | "MEDIUM" | "LOW"

HIGH_THRESHOLD = 70
MEDIUM_THRESHOLD = 40

#: Deal-value tiers, currency-agnostic by design (a real cross-currency
#: comparison would need FX rates this codebase does not maintain — see the
#: progress doc's own note on `won_revenue_currency`). Treating every
#: currency's numeral the same is a stated simplification, not a silent one.
LARGE_DEAL_VALUE = Decimal(2_000_000)
MEDIUM_DEAL_VALUE = Decimal(500_000)


@dataclass(frozen=True, slots=True)
class PriorityReason:
    label: str
    detail: str


@dataclass(frozen=True, slots=True)
class PriorityScore:
    entity_type: str
    entity_id: uuid.UUID
    level: PriorityLevel
    score: int
    reasons: list[PriorityReason] = field(default_factory=list)


def _level_for(score: int) -> PriorityLevel:
    if score >= HIGH_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def score_opportunity(
    *,
    opportunity_id: uuid.UUID,
    deal_value: Decimal | None,
    currency: str,
    win_probability: int | None,
    expected_close_date: dt.date | None,
    stage_name: str,
    is_won: bool,
    is_lost: bool,
    days_since_last_activity: int | None,
    overdue_task_count: int,
    today: dt.date | None = None,
) -> PriorityScore | None:
    """Score one open opportunity. ``None`` for a closed deal — nothing to
    prioritize about a deal that is already won or lost.
    """
    if is_won or is_lost:
        return None
    today = today or dt.date.today()
    score = 0
    reasons: list[PriorityReason] = []

    if deal_value is not None:
        if deal_value >= LARGE_DEAL_VALUE:
            score += 25
            reasons.append(
                PriorityReason("Large deal", f"{currency} {deal_value:,.0f} in this opportunity")
            )
        elif deal_value >= MEDIUM_DEAL_VALUE:
            score += 12
            reasons.append(
                PriorityReason("Mid-size deal", f"{currency} {deal_value:,.0f} in this opportunity")
            )

    if expected_close_date is not None:
        days_to_close = (expected_close_date - today).days
        if days_to_close < 0:
            score += 25
            reasons.append(
                PriorityReason(
                    "Past close date", f"Expected close date was {-days_to_close} day(s) ago"
                )
            )
        elif days_to_close <= 7:
            score += 22
            reasons.append(
                PriorityReason("Closing soon", f"Close date within {days_to_close} day(s)")
            )
        elif days_to_close <= 30:
            score += 12
            reasons.append(
                PriorityReason("Closing this month", f"Close date within {days_to_close} days")
            )

    if win_probability is not None and win_probability >= 60:
        score += 10
        reasons.append(PriorityReason("High win probability", f"{win_probability}% to win"))

    if days_since_last_activity is not None:
        if days_since_last_activity >= 14:
            score += 20
            reasons.append(
                PriorityReason(
                    "Stalled", f"No recorded activity in {days_since_last_activity} days"
                )
            )
        elif days_since_last_activity >= 7:
            score += 10
            reasons.append(
                PriorityReason(
                    "Going quiet", f"No recorded activity in {days_since_last_activity} days"
                )
            )
    else:
        score += 8
        reasons.append(
            PriorityReason("No recorded activity", "Nothing logged against this deal yet")
        )

    if overdue_task_count > 0:
        score += min(15, overdue_task_count * 8)
        reasons.append(
            PriorityReason("Overdue task(s)", f"{overdue_task_count} overdue task(s) on this deal")
        )

    reasons.append(PriorityReason("Stage", stage_name))

    score = max(0, min(100, score))
    return PriorityScore(
        entity_type="OPPORTUNITY",
        entity_id=opportunity_id,
        level=_level_for(score),
        score=score,
        reasons=reasons,
    )


def score_lead(
    *,
    lead_id: uuid.UUID,
    status: str,
    crm_priority: str | None,
    expected_deal_size: Decimal | None,
    days_since_created: int,
    days_since_last_activity: int | None,
    has_open_tasks: bool,
    overdue_task_count: int,
) -> PriorityScore | None:
    """Score one active lead. ``None`` for a converted or lost/disqualified lead."""
    if status in {"CONVERTED", "DISQUALIFIED", "LOST"}:
        return None
    score = 0
    reasons: list[PriorityReason] = []

    if crm_priority == "HIGH":
        score += 20
        reasons.append(PriorityReason("Marked high priority", "Priority field is set to High"))
    elif crm_priority == "MEDIUM":
        score += 8

    if expected_deal_size is not None:
        if expected_deal_size >= LARGE_DEAL_VALUE:
            score += 20
            reasons.append(
                PriorityReason("Large expected deal", f"{expected_deal_size:,.0f} expected")
            )
        elif expected_deal_size >= MEDIUM_DEAL_VALUE:
            score += 10

    if days_since_last_activity is not None:
        if days_since_last_activity >= 14:
            score += 25
            reasons.append(
                PriorityReason(
                    "Not contacted recently",
                    f"No recorded activity in {days_since_last_activity} days",
                )
            )
        elif days_since_last_activity >= 7:
            score += 12
            reasons.append(
                PriorityReason(
                    "Going quiet", f"No recorded activity in {days_since_last_activity} days"
                )
            )
    else:
        score += 20
        reasons.append(PriorityReason("Never contacted", "No activity has been logged yet"))

    if days_since_created <= 2 and days_since_last_activity is None:
        score += 15
        reasons.append(
            PriorityReason("New lead", f"Created {days_since_created} day(s) ago, not yet worked")
        )

    if overdue_task_count > 0:
        score += min(15, overdue_task_count * 8)
        reasons.append(
            PriorityReason("Overdue task(s)", f"{overdue_task_count} overdue task(s) on this lead")
        )
    elif not has_open_tasks:
        reasons.append(
            PriorityReason("No follow-up scheduled", "No open task exists for this lead")
        )

    reasons.append(PriorityReason("Status", status.replace("_", " ").title()))

    score = max(0, min(100, score))
    return PriorityScore(
        entity_type="LEAD",
        entity_id=lead_id,
        level=_level_for(score),
        score=score,
        reasons=reasons,
    )


__all__ = [
    "HIGH_THRESHOLD",
    "LARGE_DEAL_VALUE",
    "MEDIUM_DEAL_VALUE",
    "MEDIUM_THRESHOLD",
    "PriorityLevel",
    "PriorityReason",
    "PriorityScore",
    "score_lead",
    "score_opportunity",
]
