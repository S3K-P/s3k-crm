"""Pydantic contracts for the AI gateway.

Nothing here can carry a credential. :class:`AiStatusResponse` reports
*whether* a key is configured and never any part of its value — the frontend's
only legitimate question is whether to render the feature or the "not
connected" state.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

#: Upper bound on a published prompt. Generous — an administrator writing a
#: detailed research brief needs room — but bounded, because the value is sent
#: to a model on every research turn and an unbounded field is a cost and
#: latency hazard as much as a validation one.
MAX_PROMPT_LENGTH = 20_000


class AiStatusResponse(BaseModel):
    """Whether AI features can run at all, and under what model."""

    configured: bool
    #: Present only when configured. Identifies the model, never the key.
    model: str | None = None


class PromptVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    version: int
    prompt: str
    change_note: str | None
    is_active: bool
    created_at: dt.datetime
    created_by_id: uuid.UUID | None


class PromptSummary(BaseModel):
    """A version without its body, for the history list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version: int
    change_note: str | None
    is_active: bool
    created_at: dt.datetime
    created_by_id: uuid.UUID | None


class PromptConfigResponse(BaseModel):
    """The Settings screen's whole payload for one prompt key."""

    key: str
    active: PromptVersionResponse
    history: list[PromptSummary]


class PromptPublishRequest(BaseModel):
    """Publish new wording. The previous version is kept, never overwritten."""

    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    change_note: str | None = Field(default=None, max_length=255)


__all__ = [
    "MAX_PROMPT_LENGTH",
    "AiStatusResponse",
    "PromptConfigResponse",
    "PromptPublishRequest",
    "PromptSummary",
    "PromptVersionResponse",
]
