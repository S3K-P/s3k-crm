"""Next Best Action vocabulary: every action the engine may recommend.

The catalog is data, not behaviour. A rule (``nba_rules.py``) names an
``action_code`` from here; the frontend maps an action's ``execution`` kind to
the existing CRM flow that carries it out (compose email, schedule meeting,
create task, log call, open the record) and its ``copilot`` kind to the draft
the AI Copilot can prepare for review. Nothing here writes anything.

Six categories, matching the sales-guidance model this module implements —
communication, meetings, content, internal, qualification and risk — plus the
account-growth plays (renewal, upgrade, cross-sell), which are communication or
meeting actions and are filed under those categories.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ActionCategory(enum.StrEnum):
    COMMUNICATION = "COMMUNICATION"
    MEETING = "MEETING"
    CONTENT = "CONTENT"
    INTERNAL = "INTERNAL"
    QUALIFICATION = "QUALIFICATION"
    RISK = "RISK"


class ExecutionKind(enum.StrEnum):
    """Which existing CRM flow carries an action out."""

    EMAIL = "EMAIL"  # the CRM email composer
    CALL = "CALL"  # log a call (and dial)
    WHATSAPP = "WHATSAPP"  # copy a message, open WhatsApp, log it
    LINKEDIN = "LINKEDIN"  # copy a message, open LinkedIn, log it
    MEETING = "MEETING"  # schedule a meeting activity
    TASK = "TASK"  # create a task on the record
    NOTE = "NOTE"  # record a note on the record
    RECORD = "RECORD"  # a change made on the record itself (e.g. its stage)


class CopilotKind(enum.StrEnum):
    """The draft the Generative AI Copilot can prepare for an action."""

    EMAIL = "EMAIL"
    MESSAGE = "MESSAGE"
    MEETING_AGENDA = "MEETING_AGENDA"
    CALL_SCRIPT = "CALL_SCRIPT"
    PROPOSAL = "PROPOSAL"


class RecordKind(enum.StrEnum):
    OPPORTUNITY = "OPPORTUNITY"
    LEAD = "LEAD"


BOTH: frozenset[RecordKind] = frozenset({RecordKind.OPPORTUNITY, RecordKind.LEAD})
DEALS: frozenset[RecordKind] = frozenset({RecordKind.OPPORTUNITY})


@dataclass(frozen=True, slots=True)
class ActionDef:
    code: str
    category: ActionCategory
    label: str
    execution: ExecutionKind
    copilot: CopilotKind | None
    applies_to: frozenset[RecordKind] = BOTH


_C = ActionCategory
_E = ExecutionKind
_K = CopilotKind

_ACTIONS: tuple[ActionDef, ...] = (
    # --- Communication ---------------------------------------------------
    ActionDef("CALL_CUSTOMER", _C.COMMUNICATION, "Call the customer", _E.CALL, _K.CALL_SCRIPT),
    ActionDef(
        "SEND_FOLLOW_UP_EMAIL", _C.COMMUNICATION, "Send a follow-up email", _E.EMAIL, _K.EMAIL
    ),
    ActionDef(
        "SEND_WHATSAPP_MESSAGE",
        _C.COMMUNICATION,
        "Send a WhatsApp message",
        _E.WHATSAPP,
        _K.MESSAGE,
    ),
    ActionDef(
        "SEND_LINKEDIN_MESSAGE",
        _C.COMMUNICATION,
        "Send a LinkedIn message",
        _E.LINKEDIN,
        _K.MESSAGE,
    ),
    ActionDef(
        "SEND_MEETING_SUMMARY", _C.COMMUNICATION, "Send the meeting summary", _E.EMAIL, _K.EMAIL
    ),
    ActionDef(
        "SEND_APPROVAL_REMINDER",
        _C.COMMUNICATION,
        "Send a reminder for the pending approval",
        _E.EMAIL,
        _K.EMAIL,
        DEALS,
    ),
    ActionDef(
        "SEND_PROPOSAL_REVISION",
        _C.COMMUNICATION,
        "Send a proposal revision",
        _E.EMAIL,
        _K.PROPOSAL,
        DEALS,
    ),
    ActionDef(
        "SEND_PRICING_CLARIFICATION",
        _C.COMMUNICATION,
        "Send a pricing clarification",
        _E.EMAIL,
        _K.EMAIL,
    ),
    ActionDef(
        "RECOMMEND_CROSS_SELL",
        _C.COMMUNICATION,
        "Recommend relevant additional modules",
        _E.EMAIL,
        _K.EMAIL,
        DEALS,
    ),
    ActionDef(
        "OFFER_PLAN_UPGRADE", _C.COMMUNICATION, "Offer a plan upgrade", _E.EMAIL, _K.EMAIL, DEALS
    ),
    # --- Meetings --------------------------------------------------------
    ActionDef(
        "SCHEDULE_DISCOVERY_CALL",
        _C.MEETING,
        "Schedule a discovery call",
        _E.MEETING,
        _K.MEETING_AGENDA,
    ),
    ActionDef(
        "SCHEDULE_PRODUCT_DEMO",
        _C.MEETING,
        "Schedule a product demo",
        _E.MEETING,
        _K.MEETING_AGENDA,
    ),
    ActionDef(
        "SCHEDULE_TECHNICAL_WORKSHOP",
        _C.MEETING,
        "Schedule a technical workshop",
        _E.MEETING,
        _K.MEETING_AGENDA,
        DEALS,
    ),
    ActionDef(
        "SCHEDULE_STAKEHOLDER_MEETING",
        _C.MEETING,
        "Schedule a stakeholder meeting",
        _E.MEETING,
        _K.MEETING_AGENDA,
        DEALS,
    ),
    ActionDef(
        "SCHEDULE_PRICING_DISCUSSION",
        _C.MEETING,
        "Schedule a pricing / commercial negotiation discussion",
        _E.MEETING,
        _K.MEETING_AGENDA,
    ),
    ActionDef(
        "SCHEDULE_PROCUREMENT_DISCUSSION",
        _C.MEETING,
        "Schedule a procurement discussion",
        _E.MEETING,
        _K.MEETING_AGENDA,
        DEALS,
    ),
    ActionDef(
        "SCHEDULE_EXECUTIVE_ALIGNMENT",
        _C.MEETING,
        "Schedule an executive alignment meeting",
        _E.MEETING,
        _K.MEETING_AGENDA,
        DEALS,
    ),
    ActionDef(
        "INITIATE_RENEWAL",
        _C.MEETING,
        "Initiate the renewal discussion",
        _E.MEETING,
        _K.MEETING_AGENDA,
        DEALS,
    ),
    # --- Content ---------------------------------------------------------
    ActionDef("SEND_BROCHURE", _C.CONTENT, "Send the brochure", _E.EMAIL, _K.EMAIL),
    ActionDef("SEND_CASE_STUDY", _C.CONTENT, "Send a relevant case study", _E.EMAIL, _K.EMAIL),
    ActionDef("SEND_ROI_CALCULATOR", _C.CONTENT, "Send the ROI calculator", _E.EMAIL, _K.EMAIL),
    ActionDef(
        "SEND_IMPLEMENTATION_ROADMAP",
        _C.CONTENT,
        "Send the implementation roadmap",
        _E.EMAIL,
        _K.EMAIL,
        DEALS,
    ),
    ActionDef(
        "SEND_SECURITY_COMPLIANCE_DOC",
        _C.CONTENT,
        "Send the security & compliance document",
        _E.EMAIL,
        _K.EMAIL,
        DEALS,
    ),
    ActionDef(
        "SEND_CUSTOMER_TESTIMONIAL", _C.CONTENT, "Send a customer testimonial", _E.EMAIL, _K.EMAIL
    ),
    ActionDef("SHARE_DEMO_RECORDING", _C.CONTENT, "Share the demo recording", _E.EMAIL, _K.EMAIL),
    ActionDef(
        "SEND_COMPETITIVE_BATTLECARD",
        _C.CONTENT,
        "Send the competitive battlecard",
        _E.EMAIL,
        _K.EMAIL,
        DEALS,
    ),
    # --- Internal --------------------------------------------------------
    ActionDef(
        "INVOLVE_PRESALES_ENGINEER",
        _C.INTERNAL,
        "Involve a pre-sales engineer",
        _E.TASK,
        None,
        DEALS,
    ),
    ActionDef(
        "REQUEST_MANAGEMENT_ESCALATION",
        _C.INTERNAL,
        "Request a management escalation",
        _E.TASK,
        None,
        DEALS,
    ),
    ActionDef(
        "GENERATE_PROPOSAL", _C.INTERNAL, "Generate the proposal", _E.TASK, _K.PROPOSAL, DEALS
    ),
    ActionDef("GENERATE_SOW", _C.INTERNAL, "Generate the SOW", _E.TASK, _K.PROPOSAL, DEALS),
    ActionDef(
        "PREPARE_CUSTOM_PRICING", _C.INTERNAL, "Prepare custom pricing", _E.TASK, None, DEALS
    ),
    ActionDef(
        "ASSIGN_SOLUTION_ARCHITECT",
        _C.INTERNAL,
        "Assign a solution architect",
        _E.TASK,
        None,
        DEALS,
    ),
    ActionDef("INVOLVE_LEGAL_TEAM", _C.INTERNAL, "Involve the legal team", _E.TASK, None, DEALS),
    ActionDef(
        "MOVE_TO_NEGOTIATION",
        _C.INTERNAL,
        "Move the deal to the negotiation stage",
        _E.RECORD,
        None,
        DEALS,
    ),
    # --- Qualification ---------------------------------------------------
    ActionDef(
        "IDENTIFY_DECISION_MAKER",
        _C.QUALIFICATION,
        "Identify the decision makers",
        _E.TASK,
        _K.CALL_SCRIPT,
    ),
    ActionDef("CONFIRM_BUDGET", _C.QUALIFICATION, "Confirm the budget", _E.TASK, _K.CALL_SCRIPT),
    ActionDef(
        "CONFIRM_TIMELINE", _C.QUALIFICATION, "Confirm the timeline", _E.TASK, _K.CALL_SCRIPT
    ),
    ActionDef(
        "IDENTIFY_COMPETITORS",
        _C.QUALIFICATION,
        "Identify competitors in the deal",
        _E.TASK,
        _K.CALL_SCRIPT,
    ),
    ActionDef(
        "CONFIRM_PAIN_POINTS",
        _C.QUALIFICATION,
        "Confirm the business pain points",
        _E.TASK,
        _K.CALL_SCRIPT,
    ),
    ActionDef(
        "VERIFY_PROCUREMENT_PROCESS",
        _C.QUALIFICATION,
        "Verify the procurement process",
        _E.TASK,
        _K.CALL_SCRIPT,
        DEALS,
    ),
    # --- Risk ------------------------------------------------------------
    ActionDef("REENGAGE_INACTIVE", _C.RISK, "Re-engage the inactive record", _E.EMAIL, _K.EMAIL),
    ActionDef("MOVE_TO_NURTURE", _C.RISK, "Move to the nurture pipeline", _E.RECORD, None),
    ActionDef("MARK_HIGH_RISK", _C.RISK, "Mark as a high-risk deal", _E.NOTE, None, DEALS),
    ActionDef(
        "ESCALATE_STALLED_OPPORTUNITY",
        _C.RISK,
        "Escalate the stalled opportunity",
        _E.TASK,
        None,
        DEALS,
    ),
    ActionDef(
        "SCHEDULE_EXECUTIVE_INTERVENTION",
        _C.RISK,
        "Schedule an executive intervention",
        _E.MEETING,
        _K.MEETING_AGENDA,
        DEALS,
    ),
)

ACTIONS: dict[str, ActionDef] = {action.code: action for action in _ACTIONS}

#: Display/sort order for ties at the same priority: what protects the deal
#: first, then talking to the customer, then everything that supports it.
CATEGORY_ORDER: dict[ActionCategory, int] = {
    ActionCategory.RISK: 0,
    ActionCategory.COMMUNICATION: 1,
    ActionCategory.MEETING: 2,
    ActionCategory.QUALIFICATION: 3,
    ActionCategory.INTERNAL: 4,
    ActionCategory.CONTENT: 5,
}


def get_action(code: str) -> ActionDef | None:
    return ACTIONS.get(code)


__all__ = [
    "ACTIONS",
    "CATEGORY_ORDER",
    "ActionCategory",
    "ActionDef",
    "CopilotKind",
    "ExecutionKind",
    "RecordKind",
    "get_action",
]
