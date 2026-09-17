"""The Next Best Action rules engine: ``IF conditions THEN action``.

Level 1 of the engine's maturity model. A rule is **data** — conditions in the
same ``{"field_key", "operator", "value"}`` shape layouts and workflows already
use, evaluated by the same function (``layouts.evaluate.evaluate_condition``)
— over a record's signal snapshot (``nba_signals.py``). The built-in rules
below are defaults, not special cases: a tenant can switch any of them off,
re-prioritise it or change its thresholds, and add rules of its own
(``models.NbaRule``), all evaluated by this one engine.

Several rules can recommend the same action — a proposal sitting unanswered
and a pricing-page visit both call for a pricing discussion. The engine merges
them into one recommendation carrying every reason and the highest priority,
so a record gets a coordinated set of distinct actions rather than duplicates.
Actions a rep already executed or dismissed are suppressed for the rule's
cooldown (``models.NbaActionLog``).

Pure: no session, no I/O. Everything here is unit-tested without a database.
"""

from __future__ import annotations

import string
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from app.products.crm.ai_insights.nba_catalog import (
    ACTIONS,
    BOTH,
    CATEGORY_ORDER,
    DEALS,
    ActionDef,
    RecordKind,
)
from app.products.crm.ai_insights.nba_signals import SIGNALS, display_value, is_known_signal
from app.products.crm.layouts.evaluate import OPERATORS, evaluate_condition

PRIORITY_WEIGHT: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
MAX_RULE_CONDITIONS = 10
DEFAULT_COOLDOWN_DAYS = 3

_LEADS = frozenset({RecordKind.LEAD})


@dataclass(frozen=True, slots=True)
class RuleDef:
    key: str
    name: str
    applies_to: frozenset[RecordKind]
    conditions: tuple[Mapping[str, Any], ...]
    action_code: str
    priority: str
    #: A ``str.format`` template over signal keys, e.g. ``"No reply in {days_in_stage} days"``.
    reason: str
    logic: str = "AND"
    #: When to act, in words ("within 48 hours") — shown with the action.
    timing: str | None = None
    #: Suggested due time for the task/meeting that executes the action.
    due_in_hours: int | None = None
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS
    is_active: bool = True
    source: str = "BUILTIN"
    rule_id: uuid.UUID | None = None
    position: int = 0


@dataclass(frozen=True, slots=True)
class SignalEvidence:
    key: str
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class RecommendedAction:
    action_code: str
    category: str
    label: str
    execution: str
    copilot: str | None
    priority: str
    #: ``RULE`` (Level 1) or ``PREDICTIVE`` (Level 2).
    level: str
    reasons: tuple[str, ...]
    rule_keys: tuple[str, ...]
    signals: tuple[SignalEvidence, ...]
    timing: str | None = None
    due_in_hours: int | None = None
    #: 0-100, only where it is actually measured (predictive recommendations).
    confidence: int | None = None
    cooldown_days: int = DEFAULT_COOLDOWN_DAYS
    first_position: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def _c(field_key: str, operator: str, value: Any = None) -> dict[str, Any]:
    return {"field_key": field_key, "operator": operator, "value": value}


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------

_BUILTIN: tuple[RuleDef, ...] = (
    # --- Core rules -------------------------------------------------------
    RuleDef(
        "no_follow_up_5_days",
        "No follow-up for 5 days → follow-up email",
        BOTH,
        (
            _c("days_since_last_outbound", "greater_than", 4),
            _c("has_follow_up_scheduled", "equals", False),
        ),
        "SEND_FOLLOW_UP_EMAIL",
        "MEDIUM",
        "No follow-up for {days_since_last_outbound} days, and nothing is scheduled.",
        timing="today",
        due_in_hours=24,
    ),
    RuleDef(
        "proposal_opened_3_times",
        "Proposal opened 3+ times → call the customer",
        DEALS,
        (_c("proposal_open_count", "greater_than", 2),),
        "CALL_CUSTOMER",
        "HIGH",
        "The proposal has been opened {proposal_open_count} times — interest is high.",
        timing="today",
        due_in_hours=8,
    ),
    RuleDef(
        "demo_completed_generate_proposal",
        "Demo completed → generate the proposal",
        DEALS,
        (
            _c("demo_completed", "equals", True),
            _c("stage_is_proposal", "equals", False),
            _c("stage_is_negotiation", "equals", False),
        ),
        "GENERATE_PROPOSAL",
        "HIGH",
        "A demo has been held but the deal has not reached the proposal stage.",
        timing="within 2 days",
        due_in_hours=48,
    ),
    RuleDef(
        "proposal_sent_pricing_discussion",
        "Proposal sent → schedule a pricing discussion",
        DEALS,
        (_c("stage_is_proposal", "equals", True), _c("upcoming_meeting_count", "less_than", 1)),
        "SCHEDULE_PRICING_DISCUSSION",
        "MEDIUM",
        "The proposal is out ({days_in_stage} days in stage) and no meeting is booked.",
        timing="within 48 hours",
        due_in_hours=48,
    ),
    RuleDef(
        "inactive_14_days_escalate",
        "Inactive 14 days → escalate to the manager",
        DEALS,
        (_c("days_since_last_interaction", "greater_than", 13),),
        "REQUEST_MANAGEMENT_ESCALATION",
        "HIGH",
        "No interaction on this deal for {days_since_last_interaction} days.",
        due_in_hours=24,
    ),
    RuleDef(
        "competitor_battlecard",
        "Competitor detected → send the battlecard",
        DEALS,
        (_c("has_competitor", "equals", True),),
        "SEND_COMPETITIVE_BATTLECARD",
        "MEDIUM",
        "{competitor} is competing for this deal.",
    ),
    RuleDef(
        "budget_confirmed_negotiation",
        "Budget confirmed → move to negotiation",
        DEALS,
        (_c("budget_confirmed", "equals", True), _c("stage_is_negotiation", "equals", False)),
        "MOVE_TO_NEGOTIATION",
        "MEDIUM",
        "Budget is confirmed but the deal is still at {stage_name}.",
    ),
    RuleDef(
        "no_decision_maker_executive_meeting",
        "No decision maker identified → executive meeting",
        DEALS,
        (_c("decision_maker_count", "less_than", 1), _c("stage_is_early", "equals", False)),
        "SCHEDULE_EXECUTIVE_ALIGNMENT",
        "MEDIUM",
        "No decision maker is recorded among the account's contacts at the {stage_name} stage.",
        timing="this week",
        due_in_hours=120,
    ),
    # --- Advanced patterns ----------------------------------------------
    RuleDef(
        "inactive_7_days_follow_up",
        "No activity for 7 days → follow-up email",
        BOTH,
        (_c("days_since_last_interaction", "greater_than", 6),),
        "SEND_FOLLOW_UP_EMAIL",
        "MEDIUM",
        "No activity for {days_since_last_interaction} days.",
        timing="today",
        due_in_hours=24,
    ),
    RuleDef(
        "proposal_viewed_repeatedly_24h",
        "Proposal viewed 4+ times in 24 hours → call today",
        DEALS,
        (_c("proposal_opens_24h", "greater_than", 3),),
        "CALL_CUSTOMER",
        "HIGH",
        "The proposal was viewed {proposal_opens_24h} times in the last 24 hours.",
        timing="today",
        due_in_hours=4,
    ),
    RuleDef(
        "technical_engaged_no_procurement",
        "Technical stakeholders but no procurement → procurement meeting",
        DEALS,
        (
            _c("technical_contact_count", "greater_than", 0),
            _c("procurement_contact_count", "less_than", 1),
            _c("stage_is_early", "equals", False),
        ),
        "SCHEDULE_PROCUREMENT_DISCUSSION",
        "MEDIUM",
        "{technical_contact_count} technical stakeholder(s) involved, but nobody from procurement.",
        timing="this week",
        due_in_hours=120,
    ),
    RuleDef(
        "single_stakeholder",
        "Only one stakeholder → identify more decision makers",
        DEALS,
        (_c("contact_count", "less_than", 2),),
        "IDENTIFY_DECISION_MAKER",
        "MEDIUM",
        "Only {contact_count} contact on the account — add finance and operations decision makers.",
    ),
    RuleDef(
        "large_deal_stalled",
        "Large deal stalled 14 days → involve senior sales leadership",
        DEALS,
        (
            _c("deal_value", "greater_than", 9_999_999),
            _c("days_since_last_interaction", "greater_than", 13),
        ),
        "ESCALATE_STALLED_OPPORTUNITY",
        "HIGH",
        "A {deal_value} deal has been stalled for {days_since_last_interaction} days.",
        due_in_hours=24,
    ),
    RuleDef(
        "existing_customer_cross_sell",
        "Existing customer → recommend additional modules",
        DEALS,
        (_c("account_is_customer", "equals", True), _c("account_products", "is_not_empty")),
        "RECOMMEND_CROSS_SELL",
        "LOW",
        "The account already bought: {account_products}.",
    ),
    RuleDef(
        "license_limit_upgrade",
        "Approaching the licence limit → offer an upgrade",
        DEALS,
        (_c("license_utilization_pct", "greater_than", 89),),
        "OFFER_PLAN_UPGRADE",
        "MEDIUM",
        "The customer is using {license_utilization_pct}% of their licences.",
    ),
    RuleDef(
        "subscription_expiring_renewal",
        "Subscription expires within 60 days → renewal discussion",
        DEALS,
        (
            _c("days_to_subscription_end", "less_than", 61),
            _c("days_to_subscription_end", "greater_than", -1),
        ),
        "INITIATE_RENEWAL",
        "HIGH",
        "The subscription ends in {days_to_subscription_end} days.",
        timing="this week",
        due_in_hours=72,
    ),
    RuleDef(
        "pricing_page_visits",
        "Repeated pricing-page visits → commercial discussion",
        BOTH,
        (_c("pricing_page_visits_7d", "greater_than", 2),),
        "SCHEDULE_PRICING_DISCUSSION",
        "HIGH",
        "The pricing page was visited {pricing_page_visits_7d} times this week.",
        timing="within 48 hours",
        due_in_hours=48,
    ),
    # --- Proposal follow-through (multi-signal) --------------------------
    RuleDef(
        "proposal_unanswered_call",
        "Proposal out a week with no response → call",
        DEALS,
        (
            _c("stage_is_proposal", "equals", True),
            _c("days_in_stage", "greater_than", 6),
            _c("awaiting_customer_response", "equals", True),
        ),
        "CALL_CUSTOMER",
        "HIGH",
        "The proposal has been out {days_in_stage} days with no customer response.",
        timing="today",
        due_in_hours=8,
    ),
    RuleDef(
        "proposal_unanswered_pricing_discussion",
        "Unanswered proposal → pricing discussion within 48 hours",
        DEALS,
        (
            _c("stage_is_proposal", "equals", True),
            _c("days_in_stage", "greater_than", 6),
            _c("upcoming_meeting_count", "less_than", 1),
        ),
        "SCHEDULE_PRICING_DISCUSSION",
        "HIGH",
        "The proposal is {days_in_stage} days old and no pricing discussion is booked.",
        timing="within 48 hours",
        due_in_hours=48,
    ),
    RuleDef(
        "competitive_proposal_case_study",
        "Competitor at proposal stage → send a case study",
        DEALS,
        (_c("has_competitor", "equals", True), _c("stage_is_proposal", "equals", True)),
        "SEND_CASE_STUDY",
        "MEDIUM",
        "{competitor} is competing at proposal — send a relevant {account_industry} case study.",
    ),
    RuleDef(
        "proposal_no_response_escalation",
        "No response after the proposal → escalate if still silent in 5 days",
        DEALS,
        (
            _c("stage_is_proposal", "equals", True),
            _c("awaiting_customer_response", "equals", True),
            _c("days_in_stage", "greater_than", 6),
        ),
        "REQUEST_MANAGEMENT_ESCALATION",
        "MEDIUM",
        "The customer has not responded since the proposal went out.",
        timing="if there is still no response within 5 days",
        due_in_hours=120,
    ),
    RuleDef(
        "stale_meeting_stakeholders",
        "Last meeting 10+ days ago at a late stage → stakeholder meeting",
        DEALS,
        (
            _c("days_since_last_meeting", "greater_than", 9),
            _c("stage_is_early", "equals", False),
            _c("upcoming_meeting_count", "less_than", 1),
        ),
        "SCHEDULE_STAKEHOLDER_MEETING",
        "MEDIUM",
        "The last meeting was {days_since_last_meeting} days ago and nothing is booked.",
        timing="this week",
        due_in_hours=120,
    ),
    # --- Communication ---------------------------------------------------
    RuleDef(
        "meeting_held_send_summary",
        "Meeting just held → send the summary",
        BOTH,
        (_c("days_since_last_meeting", "less_than", 2),),
        "SEND_MEETING_SUMMARY",
        "MEDIUM",
        "A meeting was held {days_since_last_meeting} day(s) ago.",
        timing="today",
        due_in_hours=24,
    ),
    RuleDef(
        "negotiation_approval_reminder",
        "Waiting on approval in negotiation → send a reminder",
        DEALS,
        (
            _c("stage_is_negotiation", "equals", True),
            _c("awaiting_customer_response", "equals", True),
            _c("days_since_last_outbound", "greater_than", 3),
        ),
        "SEND_APPROVAL_REMINDER",
        "MEDIUM",
        "No reply {days_since_last_outbound} days after the last message during negotiation.",
    ),
    RuleDef(
        "email_unanswered_whatsapp",
        "Emails unanswered for a week → WhatsApp",
        BOTH,
        (
            _c("awaiting_customer_response", "equals", True),
            _c("days_since_last_outbound", "greater_than", 6),
            _c("has_phone", "equals", True),
        ),
        "SEND_WHATSAPP_MESSAGE",
        "LOW",
        "Emails have gone unanswered for {days_since_last_outbound} days.",
    ),
    RuleDef(
        "decision_maker_quiet_linkedin",
        "Decision maker known but quiet → LinkedIn",
        DEALS,
        (
            _c("decision_maker_count", "greater_than", 0),
            _c("days_since_last_interaction", "greater_than", 9),
        ),
        "SEND_LINKEDIN_MESSAGE",
        "LOW",
        "A decision maker is known but quiet for {days_since_last_interaction} days.",
    ),
    RuleDef(
        "pricing_discussed_revision",
        "Pricing discussed at a late stage → send a proposal revision",
        DEALS,
        (_c("pricing_discussed_recently", "equals", True), _c("stage_is_early", "equals", False)),
        "SEND_PROPOSAL_REVISION",
        "MEDIUM",
        "Pricing came up in a recent interaction.",
        timing="within 2 days",
        due_in_hours=48,
    ),
    RuleDef(
        "pricing_discussed_clarification",
        "Pricing raised early → send a pricing clarification",
        BOTH,
        (
            _c("pricing_discussed_recently", "equals", True),
            _c("stage_is_proposal", "not_equals", True),
        ),
        "SEND_PRICING_CLARIFICATION",
        "LOW",
        "Pricing came up in a recent interaction.",
    ),
    # --- Meetings & content ---------------------------------------------
    RuleDef(
        "early_stage_discovery",
        "Early stage with no meeting yet → discovery call",
        BOTH,
        (
            _c("stage_is_early", "equals", True),
            _c("completed_meeting_count", "less_than", 1),
            _c("upcoming_meeting_count", "less_than", 1),
        ),
        "SCHEDULE_DISCOVERY_CALL",
        "MEDIUM",
        "No meeting has been held or booked yet.",
        timing="this week",
        due_in_hours=120,
    ),
    RuleDef(
        "discovery_done_demo",
        "Met but no demo yet → product demo",
        DEALS,
        (
            _c("completed_meeting_count", "greater_than", 0),
            _c("demo_completed", "equals", False),
            _c("stage_is_negotiation", "equals", False),
        ),
        "SCHEDULE_PRODUCT_DEMO",
        "MEDIUM",
        "{completed_meeting_count} meeting(s) held but no demo yet.",
    ),
    RuleDef(
        "technical_stakeholders_workshop",
        "Technical stakeholders, no workshop → technical workshop",
        DEALS,
        (
            _c("technical_contact_count", "greater_than", 0),
            _c("technical_workshop_completed", "equals", False),
            _c("stage_is_negotiation", "equals", False),
        ),
        "SCHEDULE_TECHNICAL_WORKSHOP",
        "LOW",
        "{technical_contact_count} technical stakeholder(s) have not had a technical workshop.",
    ),
    RuleDef(
        "early_stage_brochure",
        "Early stage → send the brochure",
        BOTH,
        (_c("stage_is_early", "equals", True), _c("outbound_emails_30d", "less_than", 1)),
        "SEND_BROCHURE",
        "LOW",
        "No material has been sent in the last 30 days.",
    ),
    RuleDef(
        "demo_held_roi",
        "Demo held → send the ROI calculator",
        DEALS,
        (_c("demo_completed", "equals", True), _c("stage_is_negotiation", "equals", False)),
        "SEND_ROI_CALCULATOR",
        "LOW",
        "A demo has been held — quantify the value.",
    ),
    RuleDef(
        "demo_held_recording",
        "Demo held, customer quiet → share the recording",
        BOTH,
        (_c("demo_completed", "equals", True), _c("awaiting_customer_response", "equals", True)),
        "SHARE_DEMO_RECORDING",
        "LOW",
        "A demo was held and the customer has not responded since.",
    ),
    RuleDef(
        "technical_security_doc",
        "Technical stakeholders at proposal → security & compliance document",
        DEALS,
        (_c("technical_contact_count", "greater_than", 0), _c("stage_is_proposal", "equals", True)),
        "SEND_SECURITY_COMPLIANCE_DOC",
        "LOW",
        "Technical stakeholders are reviewing the proposal.",
    ),
    RuleDef(
        "negotiation_roadmap",
        "Negotiation → send the implementation roadmap",
        DEALS,
        (_c("stage_is_negotiation", "equals", True),),
        "SEND_IMPLEMENTATION_ROADMAP",
        "LOW",
        "The deal is in negotiation — show how delivery will run.",
    ),
    RuleDef(
        "competitive_negotiation_testimonial",
        "Competitor in negotiation → customer testimonial",
        DEALS,
        (_c("has_competitor", "equals", True), _c("stage_is_negotiation", "equals", True)),
        "SEND_CUSTOMER_TESTIMONIAL",
        "LOW",
        "{competitor} is still competing during negotiation.",
    ),
    # --- Internal -------------------------------------------------------
    RuleDef(
        "technical_presales",
        "Technical stakeholders → involve pre-sales",
        DEALS,
        (_c("technical_contact_count", "greater_than", 0), _c("stage_is_early", "equals", True)),
        "INVOLVE_PRESALES_ENGINEER",
        "MEDIUM",
        "{technical_contact_count} technical stakeholder(s) are involved early.",
    ),
    RuleDef(
        "large_deal_architect",
        "Large technical deal → assign a solution architect",
        DEALS,
        (
            _c("deal_value", "greater_than", 4_999_999),
            _c("technical_contact_count", "greater_than", 0),
        ),
        "ASSIGN_SOLUTION_ARCHITECT",
        "LOW",
        "A {deal_value} deal with technical stakeholders.",
    ),
    RuleDef(
        "large_deal_custom_pricing",
        "Large deal at proposal → custom pricing",
        DEALS,
        (_c("deal_value", "greater_than", 4_999_999), _c("stage_is_proposal", "equals", True)),
        "PREPARE_CUSTOM_PRICING",
        "MEDIUM",
        "A {deal_value} deal at the proposal stage.",
    ),
    RuleDef(
        "negotiation_legal",
        "Negotiation → involve legal",
        DEALS,
        (_c("stage_is_negotiation", "equals", True),),
        "INVOLVE_LEGAL_TEAM",
        "LOW",
        "Contract terms are being negotiated.",
    ),
    RuleDef(
        "negotiation_sow",
        "Negotiation → generate the SOW",
        DEALS,
        (_c("stage_is_negotiation", "equals", True),),
        "GENERATE_SOW",
        "LOW",
        "Scope needs to be written down before signature.",
    ),
    # --- Qualification --------------------------------------------------
    RuleDef(
        "budget_unconfirmed",
        "Budget not confirmed at a late stage",
        DEALS,
        (_c("budget_confirmed", "equals", False), _c("stage_is_early", "equals", False)),
        "CONFIRM_BUDGET",
        "MEDIUM",
        "The budget is still unconfirmed at the {stage_name} stage.",
    ),
    RuleDef(
        "timeline_unknown",
        "No expected close date",
        DEALS,
        (_c("days_to_close", "is_empty"), _c("stage_is_early", "equals", False)),
        "CONFIRM_TIMELINE",
        "LOW",
        "No expected close date is recorded at the {stage_name} stage.",
    ),
    RuleDef(
        "competitors_unknown",
        "Competition not identified at proposal",
        DEALS,
        (_c("has_competitor", "equals", False), _c("stage_is_proposal", "equals", True)),
        "IDENTIFY_COMPETITORS",
        "LOW",
        "No competitor is recorded on a deal at the proposal stage.",
    ),
    RuleDef(
        "pain_points_unconfirmed",
        "Pain points not confirmed",
        BOTH,
        (_c("pain_points_confirmed", "equals", False),),
        "CONFIRM_PAIN_POINTS",
        "LOW",
        "The business pain points are not confirmed yet.",
    ),
    RuleDef(
        "procurement_unverified",
        "Negotiation without a verified procurement process",
        DEALS,
        (
            _c("stage_is_negotiation", "equals", True),
            _c("procurement_contact_count", "less_than", 1),
        ),
        "VERIFY_PROCUREMENT_PROCESS",
        "MEDIUM",
        "The deal is in negotiation with no procurement contact recorded.",
    ),
    # --- Risk -----------------------------------------------------------
    RuleDef(
        "inactive_30_days_reengage",
        "Inactive 30 days → re-engage",
        BOTH,
        (_c("days_since_last_interaction", "greater_than", 29),),
        "REENGAGE_INACTIVE",
        "HIGH",
        "No interaction for {days_since_last_interaction} days.",
        timing="today",
        due_in_hours=24,
    ),
    RuleDef(
        "inactive_60_days_nurture",
        "Inactive 60 days with low odds → nurture",
        BOTH,
        (_c("days_since_last_interaction", "greater_than", 59),),
        "MOVE_TO_NURTURE",
        "LOW",
        "No interaction for {days_since_last_interaction} days — consider moving to nurture.",
    ),
    RuleDef(
        "past_close_date_high_risk",
        "Past its close date → mark high risk",
        DEALS,
        (_c("days_to_close", "less_than", 0),),
        "MARK_HIGH_RISK",
        "HIGH",
        "The expected close date passed {days_to_close} days ago.",
    ),
    RuleDef(
        "large_deal_closing_no_executive",
        "Large deal closing soon without a decision maker → executive intervention",
        DEALS,
        (
            _c("deal_value", "greater_than", 9_999_999),
            _c("days_to_close", "less_than", 15),
            _c("days_to_close", "greater_than", -1),
            _c("decision_maker_count", "less_than", 1),
        ),
        "SCHEDULE_EXECUTIVE_INTERVENTION",
        "HIGH",
        "A {deal_value} deal closes in {days_to_close} days with no decision maker engaged.",
        timing="within 48 hours",
        due_in_hours=48,
    ),
    # --- Leads ------------------------------------------------------------
    RuleDef(
        "lead_never_contacted",
        "Lead never contacted → call",
        _LEADS,
        (_c("days_since_last_interaction", "is_empty"),),
        "CALL_CUSTOMER",
        "HIGH",
        "This lead has not been contacted since it was created {days_since_created} day(s) ago.",
        timing="today",
        due_in_hours=8,
    ),
    RuleDef(
        "lead_high_priority_discovery",
        "High-priority lead → discovery call",
        _LEADS,
        (_c("lead_priority", "equals", "HIGH"), _c("upcoming_meeting_count", "less_than", 1)),
        "SCHEDULE_DISCOVERY_CALL",
        "MEDIUM",
        "A high-priority lead with no meeting booked.",
        timing="this week",
        due_in_hours=72,
    ),
    RuleDef(
        "lead_contacted_qualify",
        "Contacted lead → confirm budget and need",
        _LEADS,
        (
            _c("lead_status", "in", ["CONTACTED", "QUALIFIED"]),
            _c("budget_confirmed", "not_equals", True),
        ),
        "CONFIRM_BUDGET",
        "LOW",
        "The lead is {lead_status} but the budget has not been confirmed.",
    ),
)

BUILTIN_RULES: dict[str, RuleDef] = {
    rule.key: replace(rule, position=index) for index, rule in enumerate(_BUILTIN)
}


# ---------------------------------------------------------------------------
# Validation of tenant-authored rules
# ---------------------------------------------------------------------------


class RuleValidationError(ValueError):
    pass


def validate_rule(
    *,
    applies_to: Iterable[RecordKind],
    logic: str,
    conditions: Sequence[Mapping[str, Any]],
    action_code: str,
    priority: str,
) -> None:
    """Refuse a rule the engine could not evaluate meaningfully."""
    kinds = set(applies_to)
    if not kinds:
        raise RuleValidationError("A rule must apply to deals, leads or both.")
    if logic.upper() not in {"AND", "OR"}:
        raise RuleValidationError("Logic must be AND or OR.")
    if not conditions:
        raise RuleValidationError("A rule needs at least one condition.")
    if len(conditions) > MAX_RULE_CONDITIONS:
        raise RuleValidationError(f"A rule may have at most {MAX_RULE_CONDITIONS} conditions.")
    for condition in conditions:
        key = str(condition.get("field_key", ""))
        if not is_known_signal(key):
            raise RuleValidationError(f"Unknown signal '{key}'.")
        if condition.get("operator") not in OPERATORS:
            raise RuleValidationError(f"Unknown operator '{condition.get('operator')}'.")
    action = ACTIONS.get(action_code)
    if action is None:
        raise RuleValidationError(f"Unknown action '{action_code}'.")
    if not kinds <= set(action.applies_to):
        raise RuleValidationError(f"'{action.label}' does not apply to every record type chosen.")
    if priority not in PRIORITY_WEIGHT:
        raise RuleValidationError("Priority must be HIGH, MEDIUM or LOW.")


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class _Blank(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "—"


def render_reason(template: str, signals: Mapping[str, Any]) -> str:
    values = _Blank()
    for _, name, _, _ in string.Formatter().parse(template):
        if name:
            value = signals.get(name)
            if name == "days_to_close" and isinstance(value, (int, float)) and value < 0:
                value = -value
            values[name] = display_value(name, value)
    try:
        return template.format_map(values)
    except (ValueError, KeyError, IndexError):
        return template


def _evidence(rule: RuleDef, signals: Mapping[str, Any]) -> list[SignalEvidence]:
    evidence: list[SignalEvidence] = []
    for condition in rule.conditions:
        key = str(condition.get("field_key", ""))
        signal = SIGNALS.get(key)
        if signal is not None and not signal.evidence:
            continue
        label = signal.label if signal else key.split(".", 1)[-1].replace("_", " ").capitalize()
        evidence.append(SignalEvidence(key, label, display_value(key, signals.get(key))))
    return evidence


def rule_matches(rule: RuleDef, signals: Mapping[str, Any]) -> bool:
    if not rule.conditions:
        return False
    results = [evaluate_condition(condition, signals) for condition in rule.conditions]
    return all(results) if rule.logic.upper() == "AND" else any(results)


def evaluate(
    kind: RecordKind,
    signals: Mapping[str, Any],
    rules: Iterable[RuleDef],
    *,
    suppressed: Iterable[str] = (),
    extra: Iterable[RecommendedAction] = (),
) -> list[RecommendedAction]:
    """Every distinct action the matching rules (and ``extra``) recommend, best first."""
    suppressed_codes = set(suppressed)
    merged: dict[str, RecommendedAction] = {}

    def add(candidate: RecommendedAction) -> None:
        current = merged.get(candidate.action_code)
        if current is None:
            merged[candidate.action_code] = candidate
            return
        primary, secondary = (
            (candidate, current)
            if PRIORITY_WEIGHT[candidate.priority] > PRIORITY_WEIGHT[current.priority]
            else (current, candidate)
        )
        seen_keys = {item.key for item in primary.signals}
        merged[candidate.action_code] = replace(
            primary,
            level="RULE" if "RULE" in (primary.level, secondary.level) else primary.level,
            reasons=tuple(dict.fromkeys((*primary.reasons, *secondary.reasons))),
            rule_keys=tuple(dict.fromkeys((*primary.rule_keys, *secondary.rule_keys))),
            signals=(
                *primary.signals,
                *(item for item in secondary.signals if item.key not in seen_keys),
            ),
            timing=primary.timing or secondary.timing,
            due_in_hours=min(
                (
                    hours
                    for hours in (primary.due_in_hours, secondary.due_in_hours)
                    if hours is not None
                ),
                default=None,
            ),
            confidence=primary.confidence
            if primary.confidence is not None
            else secondary.confidence,
            cooldown_days=max(primary.cooldown_days, secondary.cooldown_days),
            first_position=min(primary.first_position, secondary.first_position),
            extra={**secondary.extra, **primary.extra},
        )

    for rule in sorted(rules, key=lambda item: item.position):
        if not rule.is_active or kind not in rule.applies_to:
            continue
        action: ActionDef | None = ACTIONS.get(rule.action_code)
        if action is None or kind not in action.applies_to:
            continue
        if not rule_matches(rule, signals):
            continue
        add(
            RecommendedAction(
                action_code=action.code,
                category=action.category.value,
                label=action.label,
                execution=action.execution.value,
                copilot=action.copilot.value if action.copilot else None,
                priority=rule.priority,
                level="RULE",
                reasons=(render_reason(rule.reason, signals),),
                rule_keys=(rule.key,),
                signals=tuple(_evidence(rule, signals)),
                timing=rule.timing,
                due_in_hours=rule.due_in_hours,
                cooldown_days=rule.cooldown_days,
                first_position=rule.position,
            )
        )
    for candidate in extra:
        add(candidate)

    actions = [action for code, action in merged.items() if code not in suppressed_codes]
    actions.sort(
        key=lambda item: (
            -PRIORITY_WEIGHT[item.priority],
            CATEGORY_ORDER.get(ACTIONS[item.action_code].category, 9),
            item.first_position,
        )
    )
    return actions


def effective_rules(
    overrides: Mapping[str, Mapping[str, Any]], custom: Iterable[RuleDef]
) -> list[RuleDef]:
    """Built-ins with a tenant's overrides applied, then the tenant's own rules.

    ``overrides`` maps a built-in key to any of ``is_active``, ``priority``,
    ``conditions``, ``logic``, ``cooldown_days`` — the parts of a built-in a
    tenant may tune. Its action and applicability stay the built-in's own.
    """
    rules: list[RuleDef] = []
    for key, rule in BUILTIN_RULES.items():
        override = overrides.get(key)
        if override:
            conditions = override.get("conditions") or None
            rule = replace(
                rule,
                is_active=bool(override.get("is_active", rule.is_active)),
                priority=str(override.get("priority") or rule.priority),
                conditions=tuple(conditions) if conditions else rule.conditions,
                logic=str(override.get("logic") or rule.logic),
                cooldown_days=int(override.get("cooldown_days") or rule.cooldown_days),
            )
        rules.append(rule)
    offset = len(BUILTIN_RULES)
    rules.extend(replace(rule, position=offset + rule.position) for rule in custom)
    return rules


__all__ = [
    "BUILTIN_RULES",
    "DEFAULT_COOLDOWN_DAYS",
    "PRIORITY_WEIGHT",
    "RecommendedAction",
    "RuleDef",
    "RuleValidationError",
    "SignalEvidence",
    "effective_rules",
    "evaluate",
    "render_reason",
    "rule_matches",
    "validate_rule",
]
