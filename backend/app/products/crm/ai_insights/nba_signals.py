"""Next Best Action signals: what the engine knows about a record, and from where.

A *signal* is one named value in a record's snapshot — ``days_in_stage``,
``awaiting_customer_response``, ``decision_maker_count`` — that rules
(``nba_rules.py``) test with the shared condition vocabulary
(``layouts.evaluate``). This module holds the catalog and the pure derivation
helpers; ``nba_collect.py`` reads the database.

**Every signal names its source, and nothing is guessed.** Signals the CRM
records natively (stages, activities, meetings, emails, tasks, contacts,
won/lost history) are computed from those rows. Signals it has no tracking for
— proposal opens, email opens/clicks, pricing-page visits, licence usage,
subscription dates, budget confirmation — are read *only* from a custom field
of the same ``api_name`` on the record (or its account), which is how a
tenant's own tracking integration or a rep's own qualification feeds the
engine. A tenant without that field gets ``None``, and a rule condition on
``None`` never matches, so no recommendation is ever built on data that does
not exist.

Two derivations are keyword classifications and are stated as such: a
contact's buying role from their job title/department, and a meeting's
purpose from its subject. Both are deterministic, visible in the signal
evidence, and conservative (word-boundary matches).
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.products.crm.ai_insights.nba_catalog import BOTH, DEALS, RecordKind
from app.products.crm.currency import format_money


@dataclass(frozen=True, slots=True)
class SignalDef:
    key: str
    label: str
    #: ``number`` | ``boolean`` | ``text``
    kind: str
    applies_to: frozenset[RecordKind]
    source: str
    #: Shown with the recommendation as supporting evidence when a rule cites it.
    evidence: bool = True


_LEADS: frozenset[RecordKind] = frozenset({RecordKind.LEAD})

_SIGNALS: tuple[SignalDef, ...] = (
    # --- Stage & deal ----------------------------------------------------
    SignalDef("stage_name", "Stage", "text", DEALS, "Opportunity stage"),
    SignalDef(
        "stage_is_proposal",
        "Proposal stage",
        "boolean",
        BOTH,
        "Stage name contains 'proposal' (a lead with status Proposal Sent)",
    ),
    SignalDef(
        "stage_is_negotiation",
        "Negotiation stage",
        "boolean",
        BOTH,
        "Stage name contains 'negotiation' or 'contract' (a lead with status Negotiation)",
    ),
    SignalDef(
        "stage_is_early",
        "Early stage",
        "boolean",
        BOTH,
        "Stage is before the proposal stage in pipeline order (any other active lead)",
    ),
    SignalDef("days_in_stage", "Days in current stage", "number", DEALS, "Stage history"),
    SignalDef("deal_value", "Deal value", "number", DEALS, "Opportunity deal value"),
    SignalDef(
        "win_probability", "Win probability (%)", "number", DEALS, "Opportunity win probability"
    ),
    SignalDef(
        "days_to_close",
        "Days to expected close",
        "number",
        DEALS,
        "Expected close date (negative when past)",
    ),
    SignalDef(
        "has_competitor", "Competitor identified", "boolean", DEALS, "Opportunity competitor field"
    ),
    SignalDef("competitor", "Competitor", "text", DEALS, "Opportunity competitor field"),
    SignalDef(
        "account_industry", "Account industry", "text", DEALS, "Account industry", evidence=False
    ),
    # --- Lead ------------------------------------------------------------
    SignalDef("lead_status", "Lead status", "text", _LEADS, "Lead status"),
    SignalDef("lead_priority", "Lead priority", "text", _LEADS, "Lead priority field"),
    SignalDef(
        "expected_deal_size", "Expected deal size", "number", _LEADS, "Lead expected deal size"
    ),
    SignalDef("days_since_created", "Days since created", "number", _LEADS, "Lead created date"),
    SignalDef("has_email", "Has email address", "boolean", _LEADS, "Lead email", evidence=False),
    SignalDef(
        "has_phone",
        "Has phone number",
        "boolean",
        BOTH,
        "Lead phone / primary contact phone",
        evidence=False,
    ),
    # --- Interaction -----------------------------------------------------
    SignalDef(
        "days_since_last_interaction",
        "Days since last interaction",
        "number",
        BOTH,
        "Most recent activity, meeting or email in either direction",
    ),
    SignalDef(
        "days_since_last_outbound",
        "Days since last follow-up",
        "number",
        BOTH,
        "Most recent sent email, completed call or held meeting",
    ),
    SignalDef(
        "days_since_last_customer_response",
        "Days since customer last responded",
        "number",
        BOTH,
        "Most recent inbound email",
    ),
    SignalDef(
        "awaiting_customer_response",
        "Awaiting customer response",
        "boolean",
        BOTH,
        "An email was sent and no inbound email has arrived since",
    ),
    SignalDef("outbound_emails_30d", "Emails sent (30 days)", "number", BOTH, "Sent emails"),
    SignalDef(
        "inbound_emails_30d", "Customer emails received (30 days)", "number", BOTH, "Inbound emails"
    ),
    SignalDef(
        "days_since_last_meeting", "Days since last meeting", "number", BOTH, "Held meetings"
    ),
    SignalDef("completed_meeting_count", "Meetings held", "number", BOTH, "Held meetings"),
    SignalDef("upcoming_meeting_count", "Upcoming meetings", "number", BOTH, "Planned meetings"),
    SignalDef(
        "demo_completed",
        "Demo held",
        "boolean",
        BOTH,
        "A held meeting whose subject mentions a demo",
    ),
    SignalDef(
        "technical_workshop_completed",
        "Technical workshop held",
        "boolean",
        DEALS,
        "A held meeting whose subject mentions a workshop / technical session / PoC",
    ),
    SignalDef(
        "pricing_discussed_recently",
        "Pricing discussed recently",
        "boolean",
        BOTH,
        "An activity or meeting in the last 14 days mentions pricing / commercials",
    ),
    SignalDef(
        "recent_interaction_text",
        "Recent interaction text",
        "text",
        BOTH,
        "Subjects and notes of the last 30 days' activities, for 'contains' rules",
        evidence=False,
    ),
    # --- Follow-up -------------------------------------------------------
    SignalDef("open_task_count", "Open tasks", "number", BOTH, "Open tasks"),
    SignalDef(
        "overdue_task_count", "Overdue tasks", "number", BOTH, "Open tasks past their due date"
    ),
    SignalDef(
        "has_follow_up_scheduled",
        "Follow-up scheduled",
        "boolean",
        BOTH,
        "An open task or an upcoming meeting exists",
    ),
    # --- Stakeholders ----------------------------------------------------
    SignalDef("contact_count", "Contacts on the account", "number", DEALS, "Account contacts"),
    SignalDef(
        "decision_maker_count",
        "Decision makers",
        "number",
        DEALS,
        "Account contacts whose title reads as an executive / director / owner",
    ),
    SignalDef(
        "technical_contact_count",
        "Technical stakeholders",
        "number",
        DEALS,
        "Account contacts whose title or department reads as technical / IT",
    ),
    SignalDef(
        "procurement_contact_count",
        "Procurement stakeholders",
        "number",
        DEALS,
        "Account contacts whose title or department reads as procurement / purchasing",
    ),
    SignalDef(
        "finance_contact_count",
        "Finance stakeholders",
        "number",
        DEALS,
        "Account contacts whose title or department reads as finance",
    ),
    SignalDef(
        "engaged_contact_count_30d",
        "Contacts engaged (30 days)",
        "number",
        DEALS,
        "Account contacts with an activity or email in the last 30 days",
    ),
    # --- History ---------------------------------------------------------
    SignalDef(
        "account_won_deals", "Account deals won", "number", DEALS, "Closed-won deals on the account"
    ),
    SignalDef(
        "account_lost_deals",
        "Account deals lost",
        "number",
        DEALS,
        "Closed-lost deals on the account",
    ),
    SignalDef(
        "account_is_customer", "Existing customer", "boolean", DEALS, "The account has a won deal"
    ),
    SignalDef(
        "account_products",
        "Products already bought",
        "text",
        DEALS,
        "Products on the account's won deals",
    ),
    SignalDef(
        "similar_deal_win_rate",
        "Similar-deal win rate (%)",
        "number",
        DEALS,
        "Closed deals in the same value band",
    ),
    # --- Tracked through custom fields (see module docstring) -------------
    SignalDef(
        "proposal_open_count", "Proposal opens", "number", DEALS, "Custom field proposal_open_count"
    ),
    SignalDef(
        "proposal_opens_24h",
        "Proposal opens (24 h)",
        "number",
        DEALS,
        "Custom field proposal_opens_24h",
    ),
    SignalDef("email_open_count", "Email opens", "number", BOTH, "Custom field email_open_count"),
    SignalDef(
        "email_click_count", "Email clicks", "number", BOTH, "Custom field email_click_count"
    ),
    SignalDef(
        "pricing_page_visits_7d",
        "Pricing-page visits (7 days)",
        "number",
        BOTH,
        "Custom field pricing_page_visits_7d",
    ),
    SignalDef(
        "budget_confirmed", "Budget confirmed", "boolean", BOTH, "Custom field budget_confirmed"
    ),
    SignalDef(
        "timeline_confirmed",
        "Timeline confirmed",
        "boolean",
        BOTH,
        "Custom field timeline_confirmed",
    ),
    SignalDef(
        "pain_points_confirmed",
        "Pain points confirmed",
        "boolean",
        BOTH,
        "Custom field pain_points_confirmed",
    ),
    SignalDef(
        "procurement_verified",
        "Procurement process verified",
        "boolean",
        DEALS,
        "Custom field procurement_verified",
    ),
    SignalDef(
        "license_utilization_pct",
        "Licence utilisation (%)",
        "number",
        DEALS,
        "Account custom fields active_users / licensed_users",
    ),
    SignalDef(
        "days_to_subscription_end",
        "Days to subscription end",
        "number",
        DEALS,
        "Account custom field subscription_end_date",
    ),
)

SIGNALS: dict[str, SignalDef] = {signal.key: signal for signal in _SIGNALS}

#: Signals read from a same-named custom field, record first, then account.
CUSTOM_FIELD_SIGNALS: tuple[str, ...] = (
    "proposal_open_count",
    "proposal_opens_24h",
    "email_open_count",
    "email_click_count",
    "pricing_page_visits_7d",
    "budget_confirmed",
    "timeline_confirmed",
    "pain_points_confirmed",
    "procurement_verified",
)

#: Prefixes a custom rule may reference beyond the catalog: any custom field on
#: the record (``custom.<api_name>``) or its account (``account_custom.<api_name>``).
DYNAMIC_PREFIXES: tuple[str, ...] = ("custom.", "account_custom.")


def is_known_signal(key: str) -> bool:
    return key in SIGNALS or any(
        key.startswith(prefix) and len(key) > len(prefix) for prefix in DYNAMIC_PREFIXES
    )


# ---------------------------------------------------------------------------
# Keyword classifications
# ---------------------------------------------------------------------------

DECISION_MAKER_TERMS: tuple[str, ...] = (
    "ceo", "cfo", "coo", "cto", "cio", "cmo", "chief", "founder", "co-founder", "owner",
    "president", "vp", "vice president", "director", "head of", "managing director",
    "general manager", "partner", "principal",
)  # fmt: skip
TECHNICAL_TERMS: tuple[str, ...] = (
    "cto", "cio", "it", "engineer", "engineering", "architect", "technical", "technology",
    "developer", "devops", "infrastructure", "security", "systems", "data",
)  # fmt: skip
PROCUREMENT_TERMS: tuple[str, ...] = (
    "procurement", "purchasing", "purchase", "buyer", "sourcing", "vendor management",
    "supply chain",
)  # fmt: skip
FINANCE_TERMS: tuple[str, ...] = (
    "cfo", "finance", "financial", "accounts", "accounting", "controller", "treasury",
)  # fmt: skip

DEMO_TERMS: tuple[str, ...] = ("demo", "demonstration")
WORKSHOP_TERMS: tuple[str, ...] = (
    "workshop", "technical session", "technical deep dive", "poc", "proof of concept",
)  # fmt: skip
EXECUTIVE_TERMS: tuple[str, ...] = ("executive", "leadership", "ceo", "cxo", "c-level", "board")
PRICING_TERMS: tuple[str, ...] = (
    "pricing", "price", "commercial", "commercials", "negotiation", "quote", "quotation",
    "discount",
)  # fmt: skip


def _pattern(terms: Iterable[str]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(term) for term in terms)
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?![a-z0-9])", re.IGNORECASE)


_DECISION = _pattern(DECISION_MAKER_TERMS)
_TECHNICAL = _pattern(TECHNICAL_TERMS)
_PROCUREMENT = _pattern(PROCUREMENT_TERMS)
_FINANCE = _pattern(FINANCE_TERMS)
_DEMO = _pattern(DEMO_TERMS)
_WORKSHOP = _pattern(WORKSHOP_TERMS)
_EXECUTIVE = _pattern(EXECUTIVE_TERMS)
_PRICING = _pattern(PRICING_TERMS)


def contact_roles(job_title: str | None, department: str | None) -> set[str]:
    """Buying roles a contact's title/department reads as — possibly several."""
    text = " ".join(part for part in (job_title, department) if part)
    if not text:
        return set()
    roles: set[str] = set()
    if _DECISION.search(text):
        roles.add("decision_maker")
    if _TECHNICAL.search(text):
        roles.add("technical")
    if _PROCUREMENT.search(text):
        roles.add("procurement")
    if _FINANCE.search(text):
        roles.add("finance")
    return roles


def meeting_purposes(subject: str | None) -> set[str]:
    """What a meeting was for, read from its subject."""
    if not subject:
        return set()
    purposes: set[str] = set()
    if _DEMO.search(subject):
        purposes.add("demo")
    if _WORKSHOP.search(subject):
        purposes.add("workshop")
    if _EXECUTIVE.search(subject):
        purposes.add("executive")
    if _PRICING.search(subject):
        purposes.add("pricing")
    return purposes


def mentions_pricing(text: str | None) -> bool:
    return bool(text) and bool(_PRICING.search(text or ""))


# ---------------------------------------------------------------------------
# Pure value helpers
# ---------------------------------------------------------------------------


def days_since(moment: dt.datetime | None, now: dt.datetime) -> int | None:
    """Whole days elapsed, counted the way the priority score counts them."""
    if moment is None:
        return None
    return (now - moment).days


def to_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def to_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "confirmed"}:
        return True
    if text in {"false", "no", "n", "0", "unconfirmed"}:
        return False
    return None


def to_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def custom_field_signals(
    record_fields: Mapping[str, Any], account_fields: Mapping[str, Any], *, today: dt.date
) -> dict[str, Any]:
    """The custom-field-sourced signals, plus every custom field under its prefix."""
    signals: dict[str, Any] = {}

    def pick(name: str) -> Any:
        if name in record_fields and record_fields[name] not in (None, ""):
            return record_fields[name]
        return account_fields.get(name)

    for name in CUSTOM_FIELD_SIGNALS:
        kind = SIGNALS[name].kind
        raw = pick(name)
        signals[name] = to_bool(raw) if kind == "boolean" else to_number(raw)

    licensed = to_number(account_fields.get("licensed_users"))
    active = to_number(account_fields.get("active_users"))
    signals["license_utilization_pct"] = (
        round(active / licensed * 100) if licensed and active is not None and licensed > 0 else None
    )
    end = to_date(account_fields.get("subscription_end_date"))
    signals["days_to_subscription_end"] = (end - today).days if end else None

    for key, value in record_fields.items():
        signals[f"custom.{key}"] = value
    for key, value in account_fields.items():
        signals[f"account_custom.{key}"] = value
    return signals


def display_value(key: str, value: Any) -> str:
    """How a signal's value reads as evidence."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    number = to_number(value)
    if number is not None and SIGNALS.get(key) is not None and SIGNALS[key].kind == "number":
        if key == "deal_value" or key == "expected_deal_size":
            return format_money(Decimal(str(number)))
        return f"{number:.0f}"
    return str(value)


__all__ = [
    "CUSTOM_FIELD_SIGNALS",
    "DYNAMIC_PREFIXES",
    "SIGNALS",
    "SignalDef",
    "contact_roles",
    "custom_field_signals",
    "days_since",
    "display_value",
    "is_known_signal",
    "meeting_purposes",
    "mentions_pricing",
    "to_bool",
    "to_number",
]
