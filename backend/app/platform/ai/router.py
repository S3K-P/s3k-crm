"""AI gateway routes: status, and the administrator's prompt configuration.

Two access levels, and the split is the point of §13:

``GET /ai/status``
    Any authenticated member of the organization. It answers one boolean — is
    AI connected — which every screen in the AI section needs in order to
    choose between the feature and the "not connected" state. It exposes no
    credential and no prompt.

``/ai/prompts/*``
    ``ai.ADMIN``. No system role template grants it, so only the wildcard
    ``Admin`` role holds it: a Manager with every CRM permission still gets
    403 here. Editing the prompt changes what the AI researches for the whole
    organization, which is an administrative act, not a sales one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.core.config import Settings
from app.core.database import DbSession
from app.core.exceptions import NotFoundError
from app.platform.ai.models import MARKET_INSIGHTS_PROMPT_KEY
from app.platform.ai.schemas import (
    AiStatusResponse,
    PromptConfigResponse,
    PromptPublishRequest,
    PromptSummary,
    PromptVersionResponse,
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


@router.get("/status", response_model=AiStatusResponse)
async def ai_status(_principal: CurrentPrincipal, settings: SettingsDep) -> AiStatusResponse:
    """Whether the AI gateway has a provider credential.

    Deliberately not gated on an ``ai`` permission: a sales user with no
    administrative rights still needs to be told why the research screen is
    empty, and "you may not ask whether AI exists" is not a useful answer.
    """
    configured = settings.ai_configured
    return AiStatusResponse(
        configured=configured,
        model=settings.ai_model if configured else None,
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
