"""Pydantic contracts for the AI gateway.

Nothing here can carry a credential. :class:`AiStatusResponse` reports
*whether* a key is configured and never any part of its value — the frontend's
only legitimate question is whether to render the feature or the "not
connected" state.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import AiConfigurationIssue, AiProvider
from app.platform.ai.provider import AiConnectionState

#: Upper bound on a published prompt. Generous — an administrator writing a
#: detailed research brief needs room — but bounded, because the value is sent
#: to a model on every research turn and an unbounded field is a cost and
#: latency hazard as much as a validation one.
MAX_PROMPT_LENGTH = 20_000


class AiStatusResponse(BaseModel):
    """Whether AI features can run at all, and what is known about the link.

    Answered without calling a model. ``state`` is ``AVAILABLE`` only when a
    real call succeeded recently (``checked_at``); a key alone yields
    ``CONFIGURED``. Provider and model are configuration, not credentials, and
    are reported even when no key is set so the screen can say *which* key is
    missing.
    """

    configured: bool
    provider: AiProvider
    #: The configured model id. Identifies the model, never the key.
    model: str | None = None
    state: AiConnectionState
    #: Why ``configured`` is false; ``None`` when it is true.
    reason: AiConfigurationIssue | None = None
    #: When the verdict in ``state`` was observed, for any state a real call produced.
    checked_at: dt.datetime | None = None
    #: What produced it: an administrator's test or a real feature call.
    check_source: Literal["health_check", "feature_call"] | None = None
    latency_ms: int | None = None
    error_code: str | None = None


class AiHealthResponse(BaseModel):
    """The result of one real connection test (``POST /ai/health``)."""

    provider: AiProvider
    #: The configured model id.
    model: str
    state: AiConnectionState
    checked_at: dt.datetime
    latency_ms: int | None = None
    #: A short fixed code such as ``credential_rejected`` or ``timeout``;
    #: never the provider's own error text.
    error_code: str | None = None
    #: The model the provider reported answering with, when it answered.
    responded_model: str | None = None


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
    "AiHealthResponse",
    "AiStatusResponse",
    "PromptConfigResponse",
    "PromptPublishRequest",
    "PromptSummary",
    "PromptVersionResponse",
]
