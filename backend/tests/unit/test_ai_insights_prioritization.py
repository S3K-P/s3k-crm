"""Rule-based prioritization (§12): every score must be explainable from real
CRM fields, never a model's guess. These tests pin the scoring rules
themselves — pure functions, no database — the AI only narrates the result
(see ``test_ai_insights_prompts.py`` for the narration prompt).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from app.products.crm.ai_insights.prioritization import score_lead, score_opportunity

OPP_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
TODAY = dt.date(2026, 9, 19)


def _opportunity(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "opportunity_id": OPP_ID,
        "deal_value": None,
        "currency": "INR",
        "win_probability": None,
        "expected_close_date": None,
        "stage_name": "Negotiation",
        "is_won": False,
        "is_lost": False,
        "days_since_last_activity": 1,
        "overdue_task_count": 0,
        "today": TODAY,
    }
    kwargs.update(overrides)
    return kwargs  # type: ignore[return-value]


def _lead(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "lead_id": LEAD_ID,
        "status": "NEW",
        "crm_priority": None,
        "expected_deal_size": None,
        "days_since_created": 5,
        "days_since_last_activity": 1,
        "has_open_tasks": True,
        "overdue_task_count": 0,
    }
    kwargs.update(overrides)
    return kwargs  # type: ignore[return-value]


# --- Opportunities -----------------------------------------------------


def test_a_closed_opportunity_has_no_score() -> None:
    assert score_opportunity(**_opportunity(is_won=True)) is None
    assert score_opportunity(**_opportunity(is_lost=True)) is None


def test_a_large_deal_past_its_close_date_scores_high() -> None:
    score = score_opportunity(
        **_opportunity(
            deal_value=Decimal(3_000_000),
            expected_close_date=TODAY - dt.timedelta(days=5),
            days_since_last_activity=20,
        )
    )

    assert score is not None
    assert score.level == "HIGH"
    assert score.score >= 70
    labels = {reason.label for reason in score.reasons}
    assert "Large deal" in labels
    assert "Past close date" in labels
    assert "Stalled" in labels


def test_a_quiet_small_deal_with_no_signals_scores_low() -> None:
    score = score_opportunity(**_opportunity(days_since_last_activity=1))

    assert score is not None
    assert score.level == "LOW"


def test_every_reason_names_a_real_crm_fact_not_a_generic_claim() -> None:
    """§10: a priority reason must be a fact the owner can check on the record."""
    score = score_opportunity(
        **_opportunity(deal_value=Decimal(2_500_000), overdue_task_count=2)
    )

    assert score is not None
    reason_by_label = {r.label: r.detail for r in score.reasons}
    assert "2,500,000" in reason_by_label["Large deal"]
    assert "2 overdue task(s)" in reason_by_label["Overdue task(s)"]
    # The stage is always included, even when it contributes no points.
    assert reason_by_label["Stage"] == "Negotiation"


def test_score_never_exceeds_the_declared_bounds() -> None:
    score = score_opportunity(
        **_opportunity(
            deal_value=Decimal(10_000_000),
            expected_close_date=TODAY - dt.timedelta(days=30),
            days_since_last_activity=60,
            overdue_task_count=10,
        )
    )

    assert score is not None
    assert 0 <= score.score <= 100


def test_no_recorded_activity_at_all_is_its_own_reason() -> None:
    """A deal nobody has touched yet is not silently equivalent to a fresh one."""
    score = score_opportunity(**_opportunity(days_since_last_activity=None))

    assert score is not None
    assert any(r.label == "No recorded activity" for r in score.reasons)


# --- Leads ---------------------------------------------------------------


def test_a_converted_or_lost_lead_has_no_score() -> None:
    assert score_lead(**_lead(status="CONVERTED")) is None
    assert score_lead(**_lead(status="LOST")) is None
    assert score_lead(**_lead(status="DISQUALIFIED")) is None


def test_a_never_contacted_high_priority_lead_scores_high() -> None:
    score = score_lead(
        **_lead(
            crm_priority="HIGH",
            expected_deal_size=Decimal(3_000_000),
            days_since_last_activity=None,
        )
    )

    assert score is not None
    assert score.level in {"HIGH", "MEDIUM"}
    labels = {r.label for r in score.reasons}
    assert "Marked high priority" in labels
    assert "Never contacted" in labels


def test_a_worked_lead_with_no_urgency_scores_low() -> None:
    score = score_lead(
        **_lead(crm_priority="LOW", days_since_last_activity=1, days_since_created=100)
    )

    assert score is not None
    assert score.level == "LOW"


def test_lead_score_never_exceeds_the_declared_bounds() -> None:
    score = score_lead(
        **_lead(
            crm_priority="HIGH",
            expected_deal_size=Decimal(5_000_000),
            days_since_last_activity=30,
            overdue_task_count=10,
        )
    )

    assert score is not None
    assert 0 <= score.score <= 100
