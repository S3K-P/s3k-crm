"""AI gateway routes: status, the connection test, and prompt configuration.

Two access levels, and the split is the point of §13:

``GET /ai/status``
    Any authenticated member of the organization. It says whether AI is
    configured, for which provider and model, and what the most recent real
    call found — which every screen in the AI section needs in order to choose
    between the feature and an honest "not connected" / "provider failing"
    state. It never calls a model, so reading it on every page load costs
    nothing, and it exposes no credential and no prompt.

``POST /ai/health``
    ``ai.ADMIN``. Sends one minimal real request to the configured provider
    and model and reports what happened. A POST because it spends provider
    quota and writes an audit entry; nothing runs it automatically.

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
from app.core.redis import RedisClient
from app.platform.ai.models import MARKET_INSIGHTS_PROMPT_KEY
from app.platform.ai.schemas import (
    AiHealthResponse,
    AiStatusResponse,
    PromptConfigResponse,
    PromptPublishRequest,
    PromptSummary,
    PromptVersionResponse,
)
from app.platform.ai.service import (
    DEFAULT_MARKET_INSIGHTS_PROMPT,
    AiConnectionService,
    AiPromptService,
)
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


def get_status_service(settings: SettingsDep, redis: RedisClient) -> AiConnectionService:
    """The read-only half: no database session, because status reads none."""
    return AiConnectionService(settings=settings, redis=redis)


def get_connection_service(
    settings: SettingsDep, redis: RedisClient, session: DbSession
) -> AiConnectionService:
    """The connection test's service, bound to this request's session for the audit entry.

    Its own dependency so tests can substitute the provider without patching a
    module global — the pattern Market Insights' ``get_service`` already uses.
    """
    return AiConnectionService(settings=settings, redis=redis, session=session)


@router.get("/status", response_model=AiStatusResponse)
async def ai_status(
    _principal: CurrentPrincipal,
    service: Annotated[AiConnectionService, Depends(get_status_service)],
) -> AiStatusResponse:
    """What is known about the AI connection, without calling a model.

    Deliberately not gated on an ``ai`` permission: a sales user with no
    administrative rights still needs to be told why the research screen is
    empty, and "you may not ask whether AI exists" is not a useful answer.
    """
    status = await service.status()
    return AiStatusResponse(
        configured=status.configured,
        provider=status.provider,
        model=status.model,
        state=status.state,
        reason=status.issue,
        checked_at=status.checked_at,
        check_source=status.check_source,
        latency_ms=status.latency_ms,
        error_code=status.error_code,
    )


@router.post("/health", response_model=AiHealthResponse)
async def ai_health(
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.ADMIN))
    ],
    settings: SettingsDep,
    service: Annotated[AiConnectionService, Depends(get_connection_service)],
) -> AiHealthResponse:
    """Test the connection with one minimal real request to the configured model.

    Always answers 200 with a ``state`` — a failed test is a successful answer
    to "does it work". ``AVAILABLE`` means the provider's model actually replied.
    """
    check = await service.check(
        organization_id=principal.organization_id, actor_id=principal.user_id
    )
    return AiHealthResponse(
        provider=settings.ai_provider,
        model=settings.ai_active_model,
        state=check.state,
        checked_at=check.checked_at,
        latency_ms=check.latency_ms,
        error_code=check.error_code,
        responded_model=check.model,
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
