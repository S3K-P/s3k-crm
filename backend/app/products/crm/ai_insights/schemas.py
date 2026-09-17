"""Pydantic contracts for ai_insights.

Two kinds of schema live here, and the distinction is the whole of §20
(structured output validation):

**Structured-output schemas** (`AccountIntelligenceOutput`,
`NextBestActionOutput`, ...) are what a model's JSON answer is validated
against before anything downstream ever sees it — see `structured.py`. A
model that returns malformed JSON, an unexpected shape, or an out-of-range
enum value fails Pydantic validation and the caller gets a clear
`ai_invalid_output` error, never a half-parsed object.

**API schemas** (`AiGenerationResponse`, `*Request`) are the ordinary
request/response contracts every router uses, following the same rule as
everywhere else in CRM: `organization_id` never appears in a request body,
because tenancy comes from the authenticated principal.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.products.crm.ai_insights.models import AiFeature, AiFeedbackRating, AiGenerationStatus
from app.products.crm.reports.schemas import CustomReportDefinition, ReportResult

MAX_MEETING_TEXT = 20_000
MAX_QUESTION = 2_000
MAX_EMAIL_INSTRUCTION = 2_000
MAX_FEEDBACK_COMMENT = 2_000

# ---------------------------------------------------------------------------
# Structured model output — validated in structured.py before use anywhere
# ---------------------------------------------------------------------------


class RecordSummaryOutput(BaseModel):
    """A short, factual account/opportunity/lead summary."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4_000)


class RelationshipHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["HEALTHY", "AT_RISK", "UNKNOWN"]
    rationale: str = Field(min_length=1, max_length=1_000)


class AccountIntelligenceOutput(BaseModel):
    """Account Intelligence: facts the caller already has, restated and
    interpreted, plus explicitly-labelled inference — never the reverse.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4_000)
    relationship_health: RelationshipHealth
    risks: list[str] = Field(default_factory=list, max_length=10)
    opportunities: list[str] = Field(default_factory=list, max_length=10)
    recommended_actions: list[str] = Field(default_factory=list, max_length=10)
    missing_information: list[str] = Field(default_factory=list, max_length=10)


class NextBestActionOutput(BaseModel):
    """One recommended next action, with why and how sure the model is."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=300)
    why: str = Field(min_length=1, max_length=1_000)
    urgency: Literal["HIGH", "MEDIUM", "LOW"]
    evidence: list[str] = Field(default_factory=list, max_length=10)
    suggested_actions: list[str] = Field(default_factory=list, max_length=6)


class EmailDraftOutput(BaseModel):
    """An AI-drafted email. Never sent automatically — see ai_insights/service.py."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8_000)


class MeetingActionItem(BaseModel):
    """One extracted, individually-acceptable follow-up (§9)."""

    model_config = ConfigDict(extra="forbid")

    #: Deliberately conservative (§11): a stage change needs a specific target
    #: stage chosen from the tenant's own blueprint-governed pipeline, which
    #: is not something a meeting transcript can name reliably — extraction
    #: offers a task, a note, or an opportunity's deal-value update, never a
    #: stage move. See the module docstring's "Known limitations".
    kind: Literal["TASK", "NOTE", "OPPORTUNITY_AMOUNT"]
    description: str = Field(min_length=1, max_length=500)
    #: Only meaningful for ``OPPORTUNITY_AMOUNT`` — a plain string as the model
    #: wrote it (e.g. "45,00,000" or "450000"); ``apply_meeting_actions``
    #: parses and validates it as a number before writing anything, and
    #: rejects the single item rather than the whole extraction if it cannot.
    amount: str | None = Field(default=None, max_length=40)


class MeetingExtractionOutput(BaseModel):
    """Structured extraction from meeting notes/a transcript (§8)."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2_000)
    participants: list[str] = Field(default_factory=list, max_length=20)
    key_points: list[str] = Field(default_factory=list, max_length=15)
    requirements: list[str] = Field(default_factory=list, max_length=15)
    objections: list[str] = Field(default_factory=list, max_length=15)
    commitments: list[str] = Field(default_factory=list, max_length=15)
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED", "UNKNOWN"] = "UNKNOWN"
    follow_up_actions: list[MeetingActionItem] = Field(default_factory=list, max_length=20)


class NlQueryTranslation(BaseModel):
    """Natural language, translated to the report engine's own safe shape.

    ``understood=False`` is a first-class outcome, not a failure: a query the
    model cannot confidently express as a structured definition must say so
    rather than guess and silently run the wrong report (§11's
    conservatism, applied to reads as well as writes).
    """

    model_config = ConfigDict(extra="forbid")

    understood: bool
    definition: CustomReportDefinition | None = None
    clarification: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _shape_matches_outcome(self) -> NlQueryTranslation:
        if self.understood and self.definition is None:
            msg = "A translation that understood the question must include a definition."
            raise ValueError(msg)
        if not self.understood and self.definition is not None:
            msg = (
                "A translation that could not understand the question must "
                "not include a definition."
            )
            raise ValueError(msg)
        return self


class PriorityExplanationOutput(BaseModel):
    """An AI narration of an already-computed rule-based priority score."""

    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(min_length=1, max_length=1_500)


# ---------------------------------------------------------------------------
# API request/response contracts
# ---------------------------------------------------------------------------


class AiGenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    feature: AiFeature
    entity_type: str | None
    entity_id: uuid.UUID | None
    status: AiGenerationStatus
    model: str | None
    error_code: str | None
    content: dict[str, Any]
    used_crm_context: bool
    created_by_id: uuid.UUID | None
    created_at: dt.datetime
    feedback_rating: AiFeedbackRating | None
    feedback_comment: str | None
    feedback_at: dt.datetime | None


class AiFeedbackRequest(BaseModel):
    rating: AiFeedbackRating
    comment: str | None = Field(default=None, max_length=MAX_FEEDBACK_COMMENT)


class EmailDraftRequest(BaseModel):
    """Ask for an AI-drafted email about one CRM record.

    Exactly one of ``contact_id``/``account_id``/``opportunity_id``/``lead_id``
    must be given — the record the draft is written for and the source of the
    CRM context (§7).
    """

    contact_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    tone: Literal["PROFESSIONAL", "FRIENDLY", "CONCISE", "FORMAL"] = "PROFESSIONAL"
    #: What the email should do, e.g. "follow up after our last meeting" or
    #: "introduce the Q3 renewal proposal". Free text, sent as delimited data
    #: — never as an instruction that could override the system prompt.
    instruction: str = Field(min_length=1, max_length=MAX_EMAIL_INSTRUCTION)
    #: A previous draft's body, for "regenerate" / "make it shorter" / "make
    #: it more formal" — sent back as context, not reused verbatim.
    previous_draft: str | None = Field(default=None, max_length=8_000)

    @model_validator(mode="after")
    def _exactly_one_subject(self) -> EmailDraftRequest:
        given = [self.contact_id, self.account_id, self.opportunity_id, self.lead_id]
        if sum(1 for value in given if value is not None) != 1:
            msg = "Give exactly one of contact_id, account_id, opportunity_id or lead_id."
            raise ValueError(msg)
        return self


class MeetingExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MEETING_TEXT)
    account_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "Paste the meeting notes or transcript."
            raise ValueError(msg)
        return cleaned


class MeetingApplyRequest(BaseModel):
    """Which extracted items the user confirmed — never all of them by default."""

    indexes: list[int] = Field(min_length=1, max_length=20)


class MeetingAppliedItem(BaseModel):
    index: int
    kind: str
    description: str
    outcome: Literal["CREATED", "SKIPPED", "FAILED"]
    reason: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None


class MeetingApplyResponse(BaseModel):
    generation: AiGenerationResponse
    results: list[MeetingAppliedItem]


class NlQueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            msg = "Enter a question."
            raise ValueError(msg)
        return cleaned


class NlQueryResponse(BaseModel):
    generation_id: uuid.UUID
    understood: bool
    clarification: str | None
    definition: CustomReportDefinition | None
    result: ReportResult | None


class PriorityReason(BaseModel):
    """One fact behind a priority score — always grounded, never invented."""

    label: str
    detail: str


class PriorityScoreResponse(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    entity_label: str
    level: Literal["HIGH", "MEDIUM", "LOW"]
    score: int = Field(ge=0, le=100)
    reasons: list[PriorityReason]


class PriorityListResponse(BaseModel):
    items: list[PriorityScoreResponse]


class InsightItem(BaseModel):
    """One rule-based, evidence-grounded insight (§13)."""

    kind: str
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    title: str
    detail: str
    entity_type: str
    entity_id: uuid.UUID
    entity_label: str


class InsightsDigest(BaseModel):
    generated_at: dt.datetime
    deals_at_risk: list[InsightItem]
    stale_opportunities: list[InsightItem]
    neglected_leads: list[InsightItem]
    accounts_needing_attention: list[InsightItem]
    overdue_tasks: list[InsightItem]


__all__ = [
    "MAX_EMAIL_INSTRUCTION",
    "MAX_FEEDBACK_COMMENT",
    "MAX_MEETING_TEXT",
    "MAX_QUESTION",
    "AccountIntelligenceOutput",
    "AiFeedbackRequest",
    "AiGenerationResponse",
    "EmailDraftOutput",
    "EmailDraftRequest",
    "InsightItem",
    "InsightsDigest",
    "MeetingActionItem",
    "MeetingAppliedItem",
    "MeetingApplyRequest",
    "MeetingApplyResponse",
    "MeetingExtractRequest",
    "MeetingExtractionOutput",
    "NextBestActionOutput",
    "NlQueryRequest",
    "NlQueryResponse",
    "NlQueryTranslation",
    "PriorityExplanationOutput",
    "PriorityListResponse",
    "PriorityReason",
    "PriorityScoreResponse",
    "RecordSummaryOutput",
    "RelationshipHealth",
]
