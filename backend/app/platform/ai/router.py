"""AI gateway routes: status, provider credentials, and prompt configuration.

Two access levels, and the split is the point of §13:

``GET /ai/status``
    Any authenticated member of the organization. It answers one boolean — is
    AI connected — which every screen in the AI section needs in order to
    choose between the feature and the "not connected" state. It exposes no
    credential and no prompt.

``/ai/providers/*``, ``/ai/prompts/*``
    ``ai.ADMIN``. No system role template grants it, so only the wildcard
    ``Admin`` role holds it: a Manager with every CRM permission still gets
    403 here. Editing the prompt changes what the AI researches for the whole
    organization, and the provider routes write the credential its whole spend
    runs on — both administrative acts, not sales ones.

**No route here returns an API key.** A credential enters through
``PUT /ai/providers/{provider}`` and is answered for thereafter only in masked
form. There is no read path back to plaintext, which is why the write and read
routes share one response model instead of the write echoing its input.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.core.config import Settings
from app.core.database import DbSession
from app.core.exceptions import NotFoundError
from app.platform.ai.credentials import AiCredentialService, require_supported
from app.platform.ai.models import (
    ANTHROPIC_PROVIDER,
    GEMINI_PROVIDER,
    MARKET_INSIGHTS_PROMPT_KEY,
    SUPPORTED_PROVIDERS,
    AiProviderCredential,
)
from app.platform.ai.registry import model_for, verify_credential
from app.platform.ai.schemas import (
    AiProvidersResponse,
    AiStatusResponse,
    PromptConfigResponse,
    PromptPublishRequest,
    PromptSummary,
    PromptVersionResponse,
    ProviderCredentialRequest,
    ProviderResponse,
    ProviderTestResponse,
)
from app.platform.ai.service import DEFAULT_MARKET_INSIGHTS_PROMPT, AiPromptService
from app.platform.auth.dependencies import (
    CurrentPrincipal,
    Principal,
    require_permission,
)
from app.platform.authorization.service import Action as PermissionAction

router = APIRouter()

MODULE = "ai"

#: Prompt keys this API will serve, mapped to the wording a fresh organization
#: starts from. An allow-list rather than a free string: the key reaches a
#: database lookup and a seeding path, and letting a caller invent one would
#: let them fill the table with junk versions nothing ever reads.
PROMPT_DEFAULTS: dict[str, str] = {
    MARKET_INSIGHTS_PROMPT_KEY: DEFAULT_MARKET_INSIGHTS_PROMPT,
}

PromptKey = Annotated[str, Path(pattern="^[a-z_]{3,64}$")]


def get_prompt_service(session: DbSession) -> AiPromptService:
    return AiPromptService(session)


PromptServiceDep = Annotated[AiPromptService, Depends(get_prompt_service)]


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(_settings)]


def get_credential_service(session: DbSession, settings: SettingsDep) -> AiCredentialService:
    return AiCredentialService(session, settings)


CredentialServiceDep = Annotated[AiCredentialService, Depends(get_credential_service)]

#: Display names for the providers this deployment implements.
PROVIDER_LABELS: dict[str, str] = {
    ANTHROPIC_PROVIDER: "Anthropic (Claude)",
    GEMINI_PROVIDER: "Google (Gemini)",
}

ProviderName = Annotated[str, Path(pattern="^[a-z0-9_-]{2,32}$")]


@router.get("/status", response_model=AiStatusResponse)
async def ai_status(
    principal: CurrentPrincipal,
    service: CredentialServiceDep,
    settings: SettingsDep,
) -> AiStatusResponse:
    """Whether AI can run **for this organization**.

    Tenant-aware since credentials became per-organization: an organization
    that stored its own key is connected even where the environment has none,
    and one that has not is still connected if the deployment supplies a
    fallback. Reading ``settings.ai_configured`` alone would answer the wrong
    question and would tell a configured tenant it has no AI.

    Deliberately not gated on an ``ai`` permission: a sales user with no
    administrative rights still needs to be told why the research screen is
    empty, and "you may not ask whether AI exists" is not a useful answer. It
    exposes one boolean and the model name — never a credential, nor even
    whether the key is the organization's or the deployment's, which is
    administrators' business.
    """
    resolved = await service.resolve(principal.organization_id)
    return AiStatusResponse(
        configured=resolved is not None,
        # The model of whichever provider actually resolved, not a deployment
        # default: an organization running on Gemini must not be told it is on
        # Claude.
        model=model_for(resolved.provider, settings) if resolved is not None else None,
    )


# --- Providers --------------------------------------------------------------
#
# ``ai.ADMIN``, exactly like the prompt routes above and for a stronger reason:
# these write the credential the whole organization's AI spend runs on. No
# system role template grants ``ai.ADMIN``, so only the wildcard ``Admin`` role
# reaches them — a Manager with every CRM permission gets 403.
#
# No route in this section returns a key. ``PUT`` accepts one and answers with
# the same masked shape as ``GET``; there is no read path back to plaintext,
# which is why the response model is shared rather than special-cased.

def _describe(
    provider: str, credential: AiProviderCredential | None, settings: Settings
) -> ProviderResponse:
    """One catalogue entry, merged with whatever the organization stored."""
    common = {
        "provider": provider,
        "label": PROVIDER_LABELS.get(provider, provider.title()),
        "model": model_for(provider, settings),
    }
    if credential is None:
        return ProviderResponse(**common, configured=False)
    return ProviderResponse(
        **common,
        configured=True,
        masked_key=credential.masked_key,
        status=credential.status.value,
        last_tested_at=credential.last_tested_at,
        last_test_error=credential.last_test_error,
        is_default=credential.is_default,
    )


async def _providers_payload(
    *, organization_id: uuid.UUID, service: AiCredentialService, settings: Settings
) -> AiProvidersResponse:
    """The whole Providers screen, assembled once and reused by every route."""
    stored = {row.provider: row for row in await service.list_for(organization_id)}
    resolved = await service.resolve(organization_id)
    return AiProvidersResponse(
        providers=[
            _describe(name, stored.get(name), settings) for name in SUPPORTED_PROVIDERS
        ],
        storage_available=service.storage_available,
        using_environment_fallback=resolved is not None and resolved.source == "environment",
    )


@router.get("/providers", response_model=AiProvidersResponse)
async def list_providers(
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))
    ],
    service: CredentialServiceDep,
    settings: SettingsDep,
) -> AiProvidersResponse:
    """Every provider this deployment supports, and what is configured for it."""
    return await _providers_payload(
        organization_id=principal.organization_id, service=service, settings=settings
    )


@router.put("/providers/{provider}", response_model=ProviderTestResponse)
async def put_provider_credential(
    provider: ProviderName,
    payload: ProviderCredentialRequest,
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))
    ],
    service: CredentialServiceDep,
    settings: SettingsDep,
) -> ProviderTestResponse:
    """Store a credential, then immediately verify it.

    Saving and testing are one action because a credential that has been
    accepted but never checked is the state most likely to be discovered by a
    user, minutes later, as a failed research run. The row is written
    ``UNVERIFIED`` first and promoted only by a real provider response, so a
    network failure during the check leaves an honest record rather than a
    false ``CONNECTED``.

    Answers with the masked provider row. The submitted key is never echoed.

    Raises:
        UnsupportedProviderError: 404, no implementation for this provider.
        InvalidCredentialError: 422, the value cannot be a key.
        SecretsNotConfiguredError: 503, this deployment cannot store secrets.
    """
    secret = payload.api_key.get_secret_value()
    credential = await service.store(
        organization_id=principal.organization_id,
        provider=provider,
        secret=secret,
        actor_id=principal.user_id,
    )

    check = await verify_credential(
        provider=provider, api_key=secret, model=model_for(provider, settings)
    )
    await service.record_test_result(
        credential=credential, ok=check.ok, error=check.error
    )
    return ProviderTestResponse(
        ok=check.ok, error=check.error, provider=_describe(provider, credential, settings)
    )


@router.post("/providers/{provider}/test", response_model=ProviderTestResponse)
async def test_provider_credential(
    provider: ProviderName,
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))
    ],
    service: CredentialServiceDep,
    settings: SettingsDep,
) -> ProviderTestResponse:
    """Re-check a stored credential against the provider.

    Decrypts only in memory, for the length of one call. Nothing about the key
    reaches the response.

    Raises:
        NotFoundError: nothing is stored for this provider.
    """
    require_supported(provider)
    credential = await service.get(
        organization_id=principal.organization_id, provider=provider
    )
    if credential is None:
        raise NotFoundError("No credential is configured for that provider.")

    secret = service.reveal(credential)
    check = await verify_credential(
        provider=provider, api_key=secret, model=model_for(provider, settings)
    )
    await service.record_test_result(
        credential=credential, ok=check.ok, error=check.error
    )
    return ProviderTestResponse(
        ok=check.ok, error=check.error, provider=_describe(provider, credential, settings)
    )


@router.post("/providers/{provider}/default", response_model=AiProvidersResponse)
async def make_provider_default(
    provider: ProviderName,
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))
    ],
    service: CredentialServiceDep,
    settings: SettingsDep,
) -> AiProvidersResponse:
    """Choose which stored credential the gateway calls with."""
    await service.set_default(
        organization_id=principal.organization_id,
        provider=provider,
        actor_id=principal.user_id,
    )
    return await _providers_payload(
        organization_id=principal.organization_id, service=service, settings=settings
    )


@router.delete("/providers/{provider}", response_model=AiProvidersResponse)
async def delete_provider_credential(
    provider: ProviderName,
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))
    ],
    service: CredentialServiceDep,
    settings: SettingsDep,
) -> AiProvidersResponse:
    """Remove a credential.

    The organization falls back to the deployment's environment key if one
    exists, and to "AI is not connected" if not — both honest states, and the
    response says which by way of ``using_environment_fallback``.
    """
    await service.delete(
        organization_id=principal.organization_id,
        provider=provider,
        actor_id=principal.user_id,
    )
    return await _providers_payload(
        organization_id=principal.organization_id, service=service, settings=settings
    )


@router.get("/prompts/{key}", response_model=PromptConfigResponse)
async def get_prompt(
    key: PromptKey,
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))
    ],
    service: PromptServiceDep,
) -> PromptConfigResponse:
    """The active prompt for ``key`` plus its version history.

    Publishes the built-in default as version 1 the first time it is read, so
    the screen always opens on a real, editable version.
    """
    default = _default_for(key)
    active = await service.ensure_active(
        organization_id=principal.organization_id,
        key=key,
        default=default,
        actor_id=principal.user_id,
    )
    history = await service.list_versions(principal.organization_id, key)
    return PromptConfigResponse(
        key=key,
        active=PromptVersionResponse.model_validate(active),
        history=[PromptSummary.model_validate(version) for version in history],
    )


@router.put("/prompts/{key}", response_model=PromptConfigResponse)
async def publish_prompt(
    key: PromptKey,
    payload: PromptPublishRequest,
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))
    ],
    service: PromptServiceDep,
) -> PromptConfigResponse:
    """Publish new wording as the next version.

    The previous version is retained and stays resolvable, so research already
    performed under it is unaffected (§12).
    """
    _default_for(key)  # rejects an unknown key before anything is written
    active = await service.publish(
        organization_id=principal.organization_id,
        key=key,
        prompt=payload.prompt,
        actor_id=principal.user_id,
        change_note=payload.change_note,
    )
    history = await service.list_versions(principal.organization_id, key)
    return PromptConfigResponse(
        key=key,
        active=PromptVersionResponse.model_validate(active),
        history=[PromptSummary.model_validate(version) for version in history],
    )


def _default_for(key: str) -> str:
    default = PROMPT_DEFAULTS.get(key)
    if default is None:
        raise NotFoundError("Unknown prompt.")
    return default


__all__ = ["router"]
