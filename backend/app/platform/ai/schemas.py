"""Pydantic contracts for the AI gateway.

Nothing here can carry a credential. :class:`AiStatusResponse` reports
*whether* a key is configured and never any part of its value — the frontend's
only legitimate question is whether to render the feature or the "not
connected" state.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, SecretStr

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


class ProviderResponse(BaseModel):
    """One provider as the Settings screen sees it.

    **Nothing here can reconstruct a credential.** ``masked_key`` is the last
    four characters behind dots, written at store time so that serving this
    list never needs the decryption key at all. There is deliberately no field
    that could carry the value, not even a write-only one — the request schema
    below is the only place a key appears, and it travels one way.
    """

    #: Machine identifier, e.g. ``anthropic``.
    provider: str
    #: Human name for the card heading.
    label: str
    #: Whether this organization has stored a credential for it.
    configured: bool
    #: ``••••••••AB9f``, or ``None`` when nothing is stored.
    masked_key: str | None = None
    #: ``UNVERIFIED`` / ``CONNECTED`` / ``INVALID``; ``None`` when unconfigured.
    status: str | None = None
    last_tested_at: dt.datetime | None = None
    #: Why the last test failed, safe to display. Never the provider's raw text.
    last_test_error: str | None = None
    #: Whether the gateway reaches for this one.
    is_default: bool = False
    #: The model this provider runs on. Per-provider rather than one field for
    #: the deployment, because each vendor names its own models and there is no
    #: identifier both would accept.
    model: str


class AiProvidersResponse(BaseModel):
    """The Providers screen's whole payload."""

    providers: list[ProviderResponse]
    #: Whether credentials can be *saved* on this deployment at all — false
    #: when no encryption key is configured. Distinct from a provider being
    #: unconfigured, and the screen says something different for each.
    storage_available: bool
    #: True when AI currently runs on the deployment-wide environment key
    #: rather than on anything this organization stored. Administrators need to
    #: see this, or "connected with nothing configured" looks like a bug.
    using_environment_fallback: bool


class ProviderCredentialRequest(BaseModel):
    """Submit or replace a provider API key.

    The only schema in the module that carries a secret, and it travels in one
    direction. ``SecretStr`` keeps it out of ``repr()``, structured logs and
    tracebacks — the same treatment ``LoginRequest`` gives a password.
    """

    api_key: SecretStr = Field(min_length=1, max_length=512)


class ProviderTestResponse(BaseModel):
    """The outcome of a connectivity check, plus the refreshed provider row."""

    ok: bool
    #: Safe explanation when ``ok`` is false.
    error: str | None = None
    provider: ProviderResponse


__all__ = [
    "MAX_PROMPT_LENGTH",
    "AiProvidersResponse",
    "AiStatusResponse",
    "PromptConfigResponse",
    "PromptPublishRequest",
    "PromptSummary",
    "PromptVersionResponse",
    "ProviderCredentialRequest",
    "ProviderResponse",
    "ProviderTestResponse",
]
