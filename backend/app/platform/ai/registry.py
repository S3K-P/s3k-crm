"""The one place that knows which vendor is which.

Every other module speaks in terms of a provider *code* and the
:class:`~app.platform.ai.provider.ResearchProvider` Protocol. The gateway asks
for a provider, the Settings routes ask whether a credential works, and neither
contains a branch on the vendor name. That branch lives here, once.

Adding a third vendor is therefore three things and no more: a class
implementing the Protocol, a verifier, and three entries below. Nothing in
``AiGatewayService``, in the router, or in any product feature changes — which
is the property ADR-016 exists to protect.
"""

from __future__ import annotations

from app.core.config import Settings
from app.platform.ai.gemini import GeminiResearchProvider, verify_gemini_credential
from app.platform.ai.models import ANTHROPIC_PROVIDER, GEMINI_PROVIDER
from app.platform.ai.provider import (
    AiNotConfiguredError,
    AnthropicResearchProvider,
    CredentialCheck,
    ResearchProvider,
    verify_anthropic_credential,
)


def model_for(provider: str, settings: Settings) -> str:
    """The model this deployment runs ``provider`` on.

    Each vendor names its own models, so there is no single ``ai_model`` that
    could serve both — using Anthropic's identifier against Gemini would fail
    at the first call with a confusing "model not found".
    """
    if provider == GEMINI_PROVIDER:
        return settings.ai_gemini_model
    return settings.ai_model


def build_provider(provider: str, settings: Settings, api_key: str) -> ResearchProvider:
    """Construct the client for ``provider``.

    Raises:
        AiNotConfiguredError: unknown provider, or an empty key. Unknown is
            folded into "not configured" deliberately: it means the stored row
            names a vendor this build cannot call, which from the caller's side
            is the same condition as having no usable credential, and it is
            reported with the same honest 503 rather than a crash.
    """
    if provider == GEMINI_PROVIDER:
        return GeminiResearchProvider(settings, api_key)
    if provider == ANTHROPIC_PROVIDER:
        return AnthropicResearchProvider(settings, api_key)
    raise AiNotConfiguredError


async def verify_credential(
    *, provider: str, api_key: str, model: str
) -> CredentialCheck:
    """Check a credential against whichever vendor owns it."""
    if provider == GEMINI_PROVIDER:
        return await verify_gemini_credential(api_key=api_key, model=model)
    if provider == ANTHROPIC_PROVIDER:
        return await verify_anthropic_credential(api_key=api_key, model=model)
    return CredentialCheck(ok=False, error="That AI provider is not available here.")


__all__ = ["build_provider", "model_for", "verify_credential"]
