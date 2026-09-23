"""The Next Best Action engine's pure parts: catalog, signals, rules, predictions.

No database. The integration suite (``tests/integration/test_ai_insights.py``)
covers the collector, permissions, persistence and the API.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from app.products.crm.ai_insights import nba_predictive, nba_rules
from app.products.crm.ai_insights.nba_catalog import ACTIONS, ActionCategory, RecordKind
from app.products.crm.ai_insights.nba_signals import (
    SIGNALS,
    contact_roles,
    custom_field_signals,
    is_known_signal,
    meeting_purposes,
)
from app.products.crm.layouts.evaluate import OPERATORS

DEAL = RecordKind.OPPORTUNITY
LEAD = RecordKind.LEAD
ALL_RULES = list(nba_rules.BUILTIN_RULES.values())


def _codes(actions: list[nba_rules.RecommendedAction]) -> list[str]:
    return [action.action_code for action in actions]


def _deal(**signals: Any) -> dict[str, Any]:
    """A quiet, well-covered open deal: nothing should fire unless a test adds it."""
    base: dict[str, Any] = {
        "stage_name": "Discovery",
        "stage_is_proposal": False,
        "stage_is_negotiation": False,
        "stage_is_early": False,
        "days_in_stage": 2,
        "deal_value": 100_000.0,
        "days_to_close": 40,
        "has_competitor": False,
        "days_since_last_interaction": 1,
        "days_since_last_outbound": 1,
        "awaiting_customer_response": False,
        "outbound_emails_30d": 3,
        "days_since_last_meeting": 5,
        "completed_meeting_count": 2,
        "upcoming_meeting_count": 1,
        "demo_completed": False,
        "technical_workshop_completed": True,
        "pricing_discussed_recently": False,
        "has_follow_up_scheduled": True,
        "contact_count": 4,
        "decision_maker_count": 1,
        "technical_contact_count": 0,
        "procurement_contact_count": 1,
    }
    base.update(signals)
    return base


# --- Catalog ---------------------------------------------------------------


def test_every_category_offers_actions() -> None:
    categories = {action.category for action in ACTIONS.values()}
    assert categories == set(ActionCategory)


@pytest.mark.parametrize("rule", ALL_RULES, ids=lambda rule: rule.key)
def test_every_builtin_rule_is_valid(rule: nba_rules.RuleDef) -> None:
    nba_rules.validate_rule(
        applies_to=rule.applies_to,
        logic=rule.logic,
        conditions=rule.conditions,
        action_code=rule.action_code,
        priority=rule.priority,
    )
    for condition in rule.conditions:
        assert condition["field_key"] in SIGNALS
        assert condition["operator"] in OPERATORS


def test_custom_field_signals_are_referenceable_but_unknown_keys_are_not() -> None:
    assert is_known_signal("custom.renewal_owner")
    assert is_known_signal("account_custom.plan")
    assert not is_known_signal("custom.")
    assert not is_known_signal("made_up_signal")


# --- The worked example ------------------------------------------------------


def test_the_multi_signal_proposal_example_produces_coordinated_actions() -> None:
    """Proposal out 8 days, opened 5 times, no reply, 25L, Zoho competing, met 12 days ago."""
    snapshot = _deal(
        stage_name="Proposal",
        stage_is_proposal=True,
        days_in_stage=8,
        proposal_open_count=5,
        awaiting_customer_response=True,
        deal_value=2_500_000.0,
        has_competitor=True,
        competitor="Zoho",
        account_industry="Manufacturing",
        days_since_last_meeting=12,
        upcoming_meeting_count=0,
        has_follow_up_scheduled=False,
        days_since_last_outbound=8,
        days_since_last_interaction=8,
    )

    actions = nba_rules.evaluate(DEAL, snapshot, ALL_RULES)
    codes = _codes(actions)

    for expected in (
        "CALL_CUSTOMER",
        "SCHEDULE_PRICING_DISCUSSION",
        "SEND_CASE_STUDY",
        "REQUEST_MANAGEMENT_ESCALATION",
        "SEND_COMPETITIVE_BATTLECARD",
        "SEND_FOLLOW_UP_EMAIL",
    ):
        assert expected in codes
    assert len(codes) == len(set(codes)), "one recommendation per action"

    by_code = {action.action_code: action for action in actions}
    pricing = by_code["SCHEDULE_PRICING_DISCUSSION"]
    assert pricing.priority == "HIGH"
    assert pricing.timing == "within 48 hours"
    assert len(pricing.rule_keys) >= 2  # merged from several rules
    call = by_code["CALL_CUSTOMER"]
    assert "5 times" in " ".join(call.reasons)
    assert any(
        signal.key == "proposal_open_count" and signal.value == "5" for signal in call.signals
    )
    assert "Manufacturing" in by_code["SEND_CASE_STUDY"].reasons[0]
    assert by_code["REQUEST_MANAGEMENT_ESCALATION"].timing is not None

    weights = [nba_rules.PRIORITY_WEIGHT[action.priority] for action in actions]
    assert weights == sorted(weights, reverse=True)


# --- The rules table ----------------------------------------------------------


@pytest.mark.parametrize(
    ("signals", "action"),
    [
        ({"days_since_last_outbound": 5, "has_follow_up_scheduled": False}, "SEND_FOLLOW_UP_EMAIL"),
        ({"proposal_open_count": 3}, "CALL_CUSTOMER"),
        ({"demo_completed": True, "stage_is_early": True}, "GENERATE_PROPOSAL"),
        ({"stage_is_proposal": True, "upcoming_meeting_count": 0}, "SCHEDULE_PRICING_DISCUSSION"),
        ({"days_since_last_interaction": 14}, "REQUEST_MANAGEMENT_ESCALATION"),
        ({"has_competitor": True, "competitor": "Salesforce"}, "SEND_COMPETITIVE_BATTLECARD"),
        ({"budget_confirmed": True}, "MOVE_TO_NEGOTIATION"),
        ({"decision_maker_count": 0}, "SCHEDULE_EXECUTIVE_ALIGNMENT"),
        ({"proposal_opens_24h": 4}, "CALL_CUSTOMER"),
        (
            {"technical_contact_count": 2, "procurement_contact_count": 0},
            "SCHEDULE_PROCUREMENT_DISCUSSION",
        ),
        ({"contact_count": 1}, "IDENTIFY_DECISION_MAKER"),
        (
            {"deal_value": 12_000_000.0, "days_since_last_interaction": 15},
            "ESCALATE_STALLED_OPPORTUNITY",
        ),
        ({"account_is_customer": True, "account_products": "CRM"}, "RECOMMEND_CROSS_SELL"),
        ({"license_utilization_pct": 95}, "OFFER_PLAN_UPGRADE"),
        ({"days_to_subscription_end": 45}, "INITIATE_RENEWAL"),
        ({"pricing_page_visits_7d": 3}, "SCHEDULE_PRICING_DISCUSSION"),
        ({"days_since_last_interaction": 30}, "REENGAGE_INACTIVE"),
        ({"days_to_close": -2}, "MARK_HIGH_RISK"),
    ],
)
def test_each_condition_recommends_its_action(signals: dict[str, Any], action: str) -> None:
    assert action in _codes(nba_rules.evaluate(DEAL, _deal(**signals), ALL_RULES))


def test_a_quiet_well_covered_deal_gets_no_urgent_actions() -> None:
    actions = nba_rules.evaluate(DEAL, _deal(), ALL_RULES)
    assert all(action.priority != "HIGH" for action in actions)


def test_signals_that_are_not_tracked_never_fire_a_rule() -> None:
    """No proposal-tracking custom field means no 'opened 3+ times' guess."""
    snapshot = _deal(
        proposal_open_count=None, pricing_page_visits_7d=None, license_utilization_pct=None
    )
    codes = _codes(nba_rules.evaluate(DEAL, snapshot, ALL_RULES))
    assert "OFFER_PLAN_UPGRADE" not in codes
    assert not any(
        "proposal_opened_3_times" in action.rule_keys
        for action in nba_rules.evaluate(DEAL, snapshot, ALL_RULES)
    )


def test_a_never_contacted_lead_is_called_first() -> None:
    lead = {
        "lead_status": "NEW",
        "lead_priority": "HIGH",
        "days_since_created": 1,
        "days_since_last_interaction": None,
        "upcoming_meeting_count": 0,
        "stage_is_early": True,
        "stage_is_proposal": False,
        "stage_is_negotiation": False,
        "has_follow_up_scheduled": False,
        "completed_meeting_count": 0,
        "outbound_emails_30d": 0,
    }
    actions = nba_rules.evaluate(LEAD, lead, ALL_RULES)
    assert actions[0].action_code == "CALL_CUSTOMER"
    assert all(ACTIONS[action.action_code].applies_to >= {LEAD} for action in actions)


def test_suppressed_actions_are_dropped() -> None:
    snapshot = _deal(has_competitor=True, competitor="Zoho")
    codes = _codes(
        nba_rules.evaluate(DEAL, snapshot, ALL_RULES, suppressed=["SEND_COMPETITIVE_BATTLECARD"])
    )
    assert "SEND_COMPETITIVE_BATTLECARD" not in codes


def test_a_tenant_can_disable_or_retune_a_builtin() -> None:
    snapshot = _deal(has_competitor=True, competitor="Zoho")
    disabled = nba_rules.effective_rules({"competitor_battlecard": {"is_active": False}}, [])
    assert "SEND_COMPETITIVE_BATTLECARD" not in _codes(nba_rules.evaluate(DEAL, snapshot, disabled))

    quiet = _deal(days_since_last_interaction=10)
    assert "REQUEST_MANAGEMENT_ESCALATION" not in _codes(nba_rules.evaluate(DEAL, quiet, ALL_RULES))
    retuned = nba_rules.effective_rules(
        {
            "inactive_14_days_escalate": {
                "conditions": [
                    {
                        "field_key": "days_since_last_interaction",
                        "operator": "greater_than",
                        "value": 9,
                    }
                ]
            }
        },
        [],
    )
    assert "REQUEST_MANAGEMENT_ESCALATION" in _codes(nba_rules.evaluate(DEAL, quiet, retuned))


def test_a_custom_rule_uses_the_same_engine() -> None:
    custom = nba_rules.RuleDef(
        key="custom.1",
        name="Mentioned Salesforce",
        applies_to=frozenset({DEAL}),
        conditions=(
            {"field_key": "recent_interaction_text", "operator": "contains", "value": "salesforce"},
        ),
        action_code="SEND_COMPETITIVE_BATTLECARD",
        priority="HIGH",
        reason="The customer mentioned Salesforce recently.",
        source="CUSTOM",
    )
    rules = nba_rules.effective_rules({}, [custom])
    snapshot = _deal(recent_interaction_text="Call notes: they are also evaluating Salesforce")
    actions = nba_rules.evaluate(DEAL, snapshot, rules)
    battlecard = next(a for a in actions if a.action_code == "SEND_COMPETITIVE_BATTLECARD")
    assert battlecard.priority == "HIGH"
    assert "custom.1" in battlecard.rule_keys


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {"conditions": [{"field_key": "nope", "operator": "equals", "value": 1}]},
            "Unknown signal",
        ),
        (
            {"conditions": [{"field_key": "deal_value", "operator": "approx", "value": 1}]},
            "Unknown operator",
        ),
        ({"action_code": "DO_MAGIC"}, "Unknown action"),
        ({"applies_to": frozenset({LEAD}), "action_code": "INVOLVE_LEGAL_TEAM"}, "does not apply"),
        ({"conditions": []}, "at least one condition"),
        ({"priority": "URGENT"}, "Priority"),
    ],
)
def test_invalid_rules_are_refused(kwargs: dict[str, Any], message: str) -> None:
    rule: dict[str, Any] = {
        "applies_to": frozenset({DEAL}),
        "logic": "AND",
        "conditions": [{"field_key": "deal_value", "operator": "greater_than", "value": 1}],
        "action_code": "CALL_CUSTOMER",
        "priority": "HIGH",
    }
    rule.update(kwargs)
    with pytest.raises(nba_rules.RuleValidationError, match=message):
        nba_rules.validate_rule(**rule)


def test_reasons_render_known_values_and_blank_unknown_ones() -> None:
    text = nba_rules.render_reason(
        "A {deal_value} deal, {days_to_close} days past, {missing}",
        {"deal_value": 2_500_000.0, "days_to_close": -3},
    )
    assert text == "A ₹25,00,000 deal, 3 days past, —"


# --- Signal derivations -------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "department", "roles"),
    [
        ("Chief Financial Officer", None, {"decision_maker", "finance"}),
        ("VP Sales", None, {"decision_maker"}),
        ("CFO", None, {"decision_maker", "finance"}),
        ("Head of IT", None, {"decision_maker", "technical"}),
        ("Procurement Manager", None, {"procurement"}),
        ("Solutions Architect", "Engineering", {"technical"}),
        ("Digital Marketing Executive", None, set()),
        (None, None, set()),
    ],
)
def test_contact_roles_are_read_from_title_and_department(
    title: str | None, department: str | None, roles: set[str]
) -> None:
    assert contact_roles(title, department) == roles


def test_meeting_purposes_are_read_from_the_subject() -> None:
    assert meeting_purposes("Product demo for ops team") == {"demo"}
    assert meeting_purposes("Technical workshop / PoC scoping") == {"workshop"}
    assert meeting_purposes("Pricing & commercials") == {"pricing"}
    assert meeting_purposes("Weekly sync") == set()


def test_custom_field_signals_derive_licence_and_renewal_values() -> None:
    signals = custom_field_signals(
        {"proposal_open_count": "5", "budget_confirmed": "yes"},
        {"licensed_users": 50, "active_users": 47, "subscription_end_date": "2026-11-01"},
        today=dt.date(2026, 9, 17),
    )
    assert signals["proposal_open_count"] == 5.0
    assert signals["budget_confirmed"] is True
    assert signals["license_utilization_pct"] == 94
    assert signals["days_to_subscription_end"] == 45
    assert signals["pricing_page_visits_7d"] is None
    assert signals["custom.proposal_open_count"] == "5"


# --- Predictive (Level 2) ---------------------------------------------------------


def _history(
    with_won: int, with_lost: int, without_won: int, without_lost: int
) -> list[nba_predictive.ClosedDeal]:
    practice = frozenset({"workshop_before_proposal"})
    return (
        [nba_predictive.ClosedDeal(True, None, practice)] * with_won
        + [nba_predictive.ClosedDeal(False, None, practice)] * with_lost
        + [nba_predictive.ClosedDeal(True, None, frozenset())] * without_won
        + [nba_predictive.ClosedDeal(False, None, frozenset())] * without_lost
    )


def test_a_practice_that_measurably_wins_more_is_recommended() -> None:
    history = _history(7, 1, 1, 7)
    predictions = nba_predictive.predict(
        band=None, done=frozenset(), past_proposal=False, history=history
    )
    workshop = next(p for p in predictions if p.action_code == "SCHEDULE_TECHNICAL_WORKSHOP")
    assert workshop.level == "PREDICTIVE"
    assert workshop.confidence is not None and workshop.confidence >= 80
    assert "88%" in workshop.reasons[0] and "12%" in workshop.reasons[0]


def test_no_prediction_without_enough_history_or_a_real_difference() -> None:
    assert (
        nba_predictive.predict(
            band=None, done=frozenset(), past_proposal=False, history=_history(3, 1, 1, 3)
        )
        == []
    )
    assert (
        nba_predictive.predict(
            band=None, done=frozenset(), past_proposal=False, history=_history(5, 5, 5, 5)
        )
        == []
    )


def test_a_practice_already_followed_or_too_late_is_not_recommended() -> None:
    history = _history(7, 1, 1, 7)
    assert (
        nba_predictive.predict(
            band=None,
            done=frozenset({"workshop_before_proposal"}),
            past_proposal=False,
            history=history,
        )
        == []
    )
    assert (
        nba_predictive.predict(band=None, done=frozenset(), past_proposal=True, history=history)
        == []
    )


def test_predictions_merge_with_rules_without_duplicating() -> None:
    history = _history(7, 1, 1, 7)
    predicted = nba_predictive.predict(
        band=None, done=frozenset(), past_proposal=False, history=history
    )
    snapshot = _deal(
        technical_contact_count=2, technical_workshop_completed=False, stage_is_early=True
    )
    actions = nba_rules.evaluate(DEAL, snapshot, ALL_RULES, extra=predicted)
    workshops = [a for a in actions if a.action_code == "SCHEDULE_TECHNICAL_WORKSHOP"]
    assert len(workshops) == 1
    assert workshops[0].confidence is not None
    assert len(workshops[0].reasons) == 2
