"""Market Insights routes.

Every endpoint declares the permission it needs and resolves the caller's
record visibility, exactly like the other CRM modules. ``visible_to`` is passed
to every read — including the reads behind a rename, a follow-up or a delete —
so another user's research session is a 404 on every verb, not only on the
list (§13).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.config import Settings
from app.core.database import DbSession
from app.core.redis import RedisClient
from app.platform.ai.service import AiGatewayService, AiPromptService
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.market_insights.models import (
    MarketInsightSession,
    ResearchStatus,
)
from app.products.crm.market_insights.schemas import (
    FollowUpRequest,
    LinkAccountRequest,
    MessageResponse,
    ResearchStartRequest,
    SessionDetail,
    SessionRenameRequest,
    SessionSummary,
    SourceResponse,
)
from app.products.crm.market_insights.service import MarketInsightService
from app.products.crm.shared.pagination import Page, PageParams, page_params
from app.products.crm.shared.visibility import RecordVisibility

router = APIRouter()

MODULE = "market_insights"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(
    session: DbSession, request: Request, redis: RedisClient
) -> MarketInsightService:
    """Build the service with a gateway bound to this request's session.

    The gateway shares the request transaction so its audit record lands with
    the session and messages it describes, or rolls back with them.
    """
    settings: Settings = request.app.state.settings
    return MarketInsightService(
        session,
        gateway=AiGatewayService(settings=settings, session=session, redis=redis),
        prompts=AiPromptService(session),
        # A second, independent factory. Used only to record a failed turn,
        # which happens on a path that is about to roll this transaction back.
        session_factory=request.app.state.session_factory,
    )


ServiceDep = Annotated[MarketInsightService, Depends(get_service)]


def visible_to(principal: Principal) -> RecordVisibility:
    """What this caller may read in this module (ADR-010, §13)."""
    return RecordVisibility.for_module(principal, MODULE)


async def _detail(service: MarketInsightService, session: MarketInsightSession) -> SessionDetail:
    """One session with its conversation and evidence attached."""
    messages = await service.messages(session)
    sources = await service.sources(session)
    return SessionDetail(
        **SessionSummary.model_validate(session).model_dump(),
        messages=[MessageResponse.model_validate(message) for message in messages],
        sources=[SourceResponse.model_validate(source) for source in sources],
    )


@router.get("", response_model=Page[SessionSummary])
async def list_sessions(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    research_status: Annotated[ResearchStatus | None, Query(alias="status")] = None,
) -> Page[SessionSummary]:
    """Research history for the caller, newest activity first (§9, §10)."""
    filters = service.build_filters(
        search=search, account_id=account_id, status_filter=research_status
    )
    items, total = await service.list_sessions(
        principal.organization_id,
        params=params,
        filters=filters,
        visibility=visible_to(principal),
    )
    return Page.build(
        [SessionSummary.model_validate(item) for item in items], total=total, params=params
    )


@router.post("", response_model=SessionDetail, status_code=status.HTTP_201_CREATED)
async def start_research(
    payload: ResearchStartRequest,
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))
    ],
    service: ServiceDep,
) -> SessionDetail:
    """Research a company and return its Market Intelligence Report.

    Works for a CRM account (``account_id`` supplied) and for an external
    company that exists nowhere in the CRM (§3). The response carries the whole
    session, so the client renders the report from one round trip.
    """
    session = await service.start_research(
        principal=principal,
        company_name=payload.company_name,
        account_id=payload.account_id,
    )
    return await _detail(service, session)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> SessionDetail:
    """Reopen a session with its conversation restored (§10).

    The stored messages are returned as they were written; nothing is
    regenerated, so reopening never starts a fresh conversation.
    """
    session = await service.get_or_404(
        session_id, principal.organization_id, visibility=visible_to(principal)
    )
    return await _detail(service, session)


@router.post("/{session_id}/messages", response_model=SessionDetail)
async def ask_follow_up(
    session_id: uuid.UUID,
    payload: FollowUpRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> SessionDetail:
    """Continue the conversation about this company (§6)."""
    session = await service.get_or_404(
        session_id, principal.organization_id, visibility=visible_to(principal)
    )
    await service.ask(session=session, principal=principal, question=payload.question)
    return await _detail(service, session)


@router.patch("/{session_id}", response_model=SessionSummary)
async def rename_session(
    session_id: uuid.UUID,
    payload: SessionRenameRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> SessionSummary:
    """Rename a research session (§10)."""
    session = await service.get_or_404(
        session_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.rename(
        session, title=payload.title, actor_id=principal.user_id
    )
    return SessionSummary.model_validate(updated)


@router.post("/{session_id}/account", response_model=SessionSummary)
async def link_account(
    session_id: uuid.UUID,
    payload: LinkAccountRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> SessionSummary:
    """Associate this research with a CRM account (§8).

    The account must already exist — created through the ordinary accounts
    flow, duplicate warning included. This endpoint links; it never creates.
    """
    session = await service.get_or_404(
        session_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.link_account(
        session, principal=principal, account_id=payload.account_id
    )
    return SessionSummary.model_validate(updated)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_session(
    session_id: uuid.UUID,
    principal: Annotated[
        Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))
    ],
    service: ServiceDep,
) -> Response:
    """Archive a research session. Nothing is physically deleted."""
    session = await service.get_or_404(
        session_id, principal.organization_id, visibility=visible_to(principal)
    )
    await service.archive(session, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
