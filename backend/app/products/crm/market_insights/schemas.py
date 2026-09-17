"""Pydantic contracts for market_insights.

``organization_id`` is absent from every request model, as everywhere else in
CRM: tenancy comes from the authenticated principal, so accepting it would
invite a client to try setting it.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.products.crm.market_insights.models import MessageRole, ResearchStatus

#: A company name long enough for "Koninklijke Philips Electronics N.V." and
#: bounded well below the column width. Names arriving longer than this are a
#: paste accident or an injection attempt, not a company.
MAX_COMPANY_NAME = 200
#: A follow-up question. Long enough to paste a paragraph of context into.
MAX_QUESTION = 4_000


class ResearchStartRequest(BaseModel):
    """Begin researching a company, CRM-linked or external."""

    #: Free text. Required even when ``account_id`` is given, so the session
    #: still names its subject if the account is later renamed.
    company_name: str = Field(min_length=1, max_length=MAX_COMPANY_NAME)
    #: The CRM account this concerns. Omitted for an external company (§3B).
    account_id: uuid.UUID | None = None

    @field_validator("company_name")
    @classmethod
    def _clean(cls, value: str) -> str:
        """Collapse whitespace and reject a name that is only punctuation.

        A name is what gets embedded in the prompt and stored as the session's
        identity, so a control character or a newline run has no business in
        it.
        """
        cleaned = " ".join(value.split())
        if not any(character.isalnum() for character in cleaned):
            msg = "Enter a company name."
            raise ValueError(msg)
        return cleaned


class FollowUpRequest(BaseModel):
    """Ask a question inside an existing research session."""

    question: str = Field(min_length=1, max_length=MAX_QUESTION)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "Enter a question."
            raise ValueError(msg)
        return cleaned


class SessionRenameRequest(BaseModel):
    """Rename a research session (§10)."""

    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            msg = "Enter a title."
            raise ValueError(msg)
        return cleaned


class LinkAccountRequest(BaseModel):
    """Associate an existing session with a CRM account (§8)."""

    account_id: uuid.UUID


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    url: str
    page_age: str | None
    cited: bool
    retrieved_at: dt.datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    role: MessageRole
    content: str
    truncated: bool
    search_count: int
    author_id: uuid.UUID | None
    created_at: dt.datetime


class SessionSummary(BaseModel):
    """A history row. No conversation body — the list must stay cheap."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_name: str
    title: str
    account_id: uuid.UUID | None
    status: ResearchStatus
    owner_id: uuid.UUID | None
    model: str | None
    prompt_version: int | None
    used_crm_context: bool
    error_code: str | None
    last_activity_at: dt.datetime
    created_at: dt.datetime
    updated_at: dt.datetime


class SessionDetail(SessionSummary):
    """One session with its full conversation and evidence (§10)."""

    messages: list[MessageResponse]
    sources: list[SourceResponse]


__all__ = [
    "MAX_COMPANY_NAME",
    "MAX_QUESTION",
    "FollowUpRequest",
    "LinkAccountRequest",
    "MessageResponse",
    "ResearchStartRequest",
    "SessionDetail",
    "SessionRenameRequest",
    "SessionSummary",
    "SourceResponse",
]
