"""AI Insights routes (Checkpoint 7).

Every endpoint requires ``ai_insights.<action>`` — requesting the feature —
on top of whatever the record itself requires, which ``AiInsightsService``
enforces while resolving it (``accounts.VIEW``, ``opportunities.VIEW``, ...).
Reading a cached result needs ``VIEW``; asking the model for a fresh one
needs ``CREATE``; feedback and applying a meeting extraction's items need
``EDIT``, the same split ``market_insights`` uses for asking a follow-up.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.config import Settings
from app.core.database import DbSession
from app.core.exceptions import NotFoundError
from app.core.redis import RedisClient
from app.platform.ai.service import AiGatewayService
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.ai_insights.models import AiFeature
from app.products.crm.ai_insights.schemas import (
    AiFeedbackRequest,
    AiGenerationResponse,
    EmailDraftRequest,
    InsightsDigest,
    MeetingApplyRequest,
    MeetingApplyResponse,
    MeetingExtractRequest,
    NlQueryRequest,
    NlQueryResponse,
    PriorityListResponse,
)
from app.products.crm.ai_insights.service import AiInsightsService
from app.products.crm.common import CrmEntityType

router = APIRouter()

MODULE = "ai_insights"


def get_service(session: DbSession, request: Request, redis: RedisClient) -> AiInsightsService:
    """Build the service with a gateway bound to this request's session.

    Same reasoning as ``market_insights.router.get_service``: the gateway
    shares the request transaction so its audit record lands with the
    generation it describes, or rolls back with it.
    """
    settings: Settings = request.app.state.settings
    return AiInsightsService(
        session, gateway=AiGatewayService(settings=settings, session=session, redis=redis)
    )


ServiceDep = Annotated[AiInsightsService, Depends(get_service)]
ViewPrincipal = Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))]
CreatePrincipal = Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))]
EditPrincipal = Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))]


# ---------------------------------------------------------------------------
# Account / opportunity / lead summaries and Account Intelligence
# ---------------------------------------------------------------------------


@router.get("/accounts/{account_id}/summary", response_model=AiGenerationResponse | None)
async def get_account_summary(
    account_id: uuid.UUID, principal: ViewPrincipal, service: ServiceDep
) -> AiGenerationResponse | None:
    """The cached summary, if one has ever been generated (§15)."""
    await service.resolve_account(principal, account_id)
    generation = await service.latest(
        principal,
        entity_type=CrmEntityType.ACCOUNT,
        entity_id=account_id,
        feature=AiFeature.ACCOUNT_SUMMARY,
    )
    return AiGenerationResponse.model_validate(generation) if generation else None


@router.post("/accounts/{account_id}/summary", response_model=AiGenerationResponse)
async def generate_account_summary(
    account_id: uuid.UUID, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    account = await service.resolve_account(principal, account_id)
    generation = await service.account_summary(principal, account)
    return AiGenerationResponse.model_validate(generation)


@router.get("/accounts/{account_id}/intelligence", response_model=AiGenerationResponse | None)
async def get_account_intelligence(
    account_id: uuid.UUID, principal: ViewPrincipal, service: ServiceDep
) -> AiGenerationResponse | None:
    await service.resolve_account(principal, account_id)
    generation = await service.latest(
        principal,
        entity_type=CrmEntityType.ACCOUNT,
        entity_id=account_id,
        feature=AiFeature.ACCOUNT_INTELLIGENCE,
    )
    return AiGenerationResponse.model_validate(generation) if generation else None


@router.post("/accounts/{account_id}/intelligence", response_model=AiGenerationResponse)
async def generate_account_intelligence(
    account_id: uuid.UUID, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    account = await service.resolve_account(principal, account_id)
    generation = await service.account_intelligence(principal, account)
    return AiGenerationResponse.model_validate(generation)


@router.get("/opportunities/{opportunity_id}/summary", response_model=AiGenerationResponse | None)
async def get_opportunity_summary(
    opportunity_id: uuid.UUID, principal: ViewPrincipal, service: ServiceDep
) -> AiGenerationResponse | None:
    await service.resolve_opportunity(principal, opportunity_id)
    generation = await service.latest(
        principal,
        entity_type=CrmEntityType.OPPORTUNITY,
        entity_id=opportunity_id,
        feature=AiFeature.OPPORTUNITY_SUMMARY,
    )
    return AiGenerationResponse.model_validate(generation) if generation else None


@router.post("/opportunities/{opportunity_id}/summary", response_model=AiGenerationResponse)
async def generate_opportunity_summary(
    opportunity_id: uuid.UUID, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    opportunity = await service.resolve_opportunity(principal, opportunity_id)
    generation = await service.opportunity_summary(principal, opportunity)
    return AiGenerationResponse.model_validate(generation)


@router.get("/leads/{lead_id}/summary", response_model=AiGenerationResponse | None)
async def get_lead_summary(
    lead_id: uuid.UUID, principal: ViewPrincipal, service: ServiceDep
) -> AiGenerationResponse | None:
    await service.resolve_lead(principal, lead_id)
    generation = await service.latest(
        principal, entity_type=CrmEntityType.LEAD, entity_id=lead_id, feature=AiFeature.LEAD_SUMMARY
    )
    return AiGenerationResponse.model_validate(generation) if generation else None


@router.post("/leads/{lead_id}/summary", response_model=AiGenerationResponse)
async def generate_lead_summary(
    lead_id: uuid.UUID, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    lead = await service.resolve_lead(principal, lead_id)
    generation = await service.lead_summary(principal, lead)
    return AiGenerationResponse.model_validate(generation)


# ---------------------------------------------------------------------------
# Next Best Action
# ---------------------------------------------------------------------------


@router.get(
    "/opportunities/{opportunity_id}/next-best-action", response_model=AiGenerationResponse | None
)
async def get_opportunity_next_best_action(
    opportunity_id: uuid.UUID, principal: ViewPrincipal, service: ServiceDep
) -> AiGenerationResponse | None:
    await service.resolve_opportunity(principal, opportunity_id)
    generation = await service.latest(
        principal,
        entity_type=CrmEntityType.OPPORTUNITY,
        entity_id=opportunity_id,
        feature=AiFeature.NEXT_BEST_ACTION,
    )
    return AiGenerationResponse.model_validate(generation) if generation else None


@router.post(
    "/opportunities/{opportunity_id}/next-best-action", response_model=AiGenerationResponse
)
async def generate_opportunity_next_best_action(
    opportunity_id: uuid.UUID, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    opportunity = await service.resolve_opportunity(principal, opportunity_id)
    generation = await service.next_best_action_for_opportunity(principal, opportunity)
    return AiGenerationResponse.model_validate(generation)


@router.get("/leads/{lead_id}/next-best-action", response_model=AiGenerationResponse | None)
async def get_lead_next_best_action(
    lead_id: uuid.UUID, principal: ViewPrincipal, service: ServiceDep
) -> AiGenerationResponse | None:
    await service.resolve_lead(principal, lead_id)
    generation = await service.latest(
        principal,
        entity_type=CrmEntityType.LEAD,
        entity_id=lead_id,
        feature=AiFeature.NEXT_BEST_ACTION,
    )
    return AiGenerationResponse.model_validate(generation) if generation else None


@router.post("/leads/{lead_id}/next-best-action", response_model=AiGenerationResponse)
async def generate_lead_next_best_action(
    lead_id: uuid.UUID, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    lead = await service.resolve_lead(principal, lead_id)
    generation = await service.next_best_action_for_lead(principal, lead)
    return AiGenerationResponse.model_validate(generation)


# ---------------------------------------------------------------------------
# AI email assistant
# ---------------------------------------------------------------------------


@router.post("/email-draft", response_model=AiGenerationResponse)
async def draft_email(
    payload: EmailDraftRequest, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    """Draft an email for the rep to review, edit and send themselves.

    Never sends anything — the draft is returned for the compose drawer.
    """
    generation = await service.draft_email(principal, payload)
    return AiGenerationResponse.model_validate(generation)


# ---------------------------------------------------------------------------
# Meeting-to-CRM
# ---------------------------------------------------------------------------


@router.post("/meetings/extract", response_model=AiGenerationResponse)
async def extract_meeting(
    payload: MeetingExtractRequest, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    account = (
        await service.resolve_account(principal, payload.account_id) if payload.account_id else None
    )
    opportunity = (
        await service.resolve_opportunity(principal, payload.opportunity_id)
        if payload.opportunity_id
        else None
    )
    generation = await service.extract_meeting(
        principal, text=payload.text, account=account, opportunity=opportunity
    )
    return AiGenerationResponse.model_validate(generation)


@router.post("/meetings/{generation_id}/apply", response_model=MeetingApplyResponse)
async def apply_meeting_actions(
    generation_id: uuid.UUID,
    payload: MeetingApplyRequest,
    principal: EditPrincipal,
    service: ServiceDep,
) -> MeetingApplyResponse:
    """Create the confirmed extraction items as real CRM records.

    Nothing is written until this call — see the module docstring on why
    extraction alone never mutates anything.
    """
    generation = await service.get_generation_or_404(principal, generation_id)
    results = await service.apply_meeting_actions(principal, generation, payload.indexes)
    return MeetingApplyResponse(
        generation=AiGenerationResponse.model_validate(generation), results=results
    )


# ---------------------------------------------------------------------------
# Natural-language CRM queries
# ---------------------------------------------------------------------------


@router.post("/query", response_model=NlQueryResponse)
async def run_nl_query(
    payload: NlQueryRequest, principal: CreatePrincipal, service: ServiceDep
) -> NlQueryResponse:
    generation, translation, result = await service.run_nl_query(principal, payload.question)
    return NlQueryResponse(
        generation_id=generation.id,
        understood=translation.understood,
        clarification=translation.clarification,
        definition=translation.definition,
        result=result,
    )


# ---------------------------------------------------------------------------
# Prioritization — rules first, AI explanation second
# ---------------------------------------------------------------------------


@router.get("/priority/opportunities", response_model=PriorityListResponse)
async def priority_opportunities(
    principal: ViewPrincipal,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PriorityListResponse:
    items = await service.prioritize_opportunities(principal, limit=limit)
    return PriorityListResponse(items=items)


@router.get("/priority/leads", response_model=PriorityListResponse)
async def priority_leads(
    principal: ViewPrincipal,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PriorityListResponse:
    items = await service.prioritize_leads(principal, limit=limit)
    return PriorityListResponse(items=items)


@router.post(
    "/priority/opportunities/{opportunity_id}/explain", response_model=AiGenerationResponse
)
async def explain_opportunity_priority(
    opportunity_id: uuid.UUID, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    score = await service.score_opportunity(principal, opportunity_id)
    if score is None:
        raise NotFoundError("This deal is closed and has no priority score.")
    generation = await service.explain_priority(principal, score=score, subject="this deal")
    return AiGenerationResponse.model_validate(generation)


@router.post("/priority/leads/{lead_id}/explain", response_model=AiGenerationResponse)
async def explain_lead_priority(
    lead_id: uuid.UUID, principal: CreatePrincipal, service: ServiceDep
) -> AiGenerationResponse:
    score = await service.score_lead(principal, lead_id)
    if score is None:
        raise NotFoundError(
            "This lead is converted, lost or unqualified and has no priority score."
        )
    generation = await service.explain_priority(principal, score=score, subject="this lead")
    return AiGenerationResponse.model_validate(generation)


# ---------------------------------------------------------------------------
# Insights digest (rules only, no model call)
# ---------------------------------------------------------------------------


@router.get("/digest", response_model=InsightsDigest)
async def insights_digest(principal: ViewPrincipal, service: ServiceDep) -> InsightsDigest:
    return await service.insights_digest(principal)


# ---------------------------------------------------------------------------
# Feedback and history — shared across every feature
# ---------------------------------------------------------------------------


@router.post("/generations/{generation_id}/feedback", response_model=AiGenerationResponse)
async def submit_feedback(
    generation_id: uuid.UUID,
    payload: AiFeedbackRequest,
    principal: EditPrincipal,
    service: ServiceDep,
) -> AiGenerationResponse:
    generation = await service.get_generation_or_404(principal, generation_id)
    updated = await service.submit_feedback(
        principal, generation, rating=payload.rating, comment=payload.comment
    )
    return AiGenerationResponse.model_validate(updated)


@router.get("/{entity_type}/{entity_id}/history", response_model=list[AiGenerationResponse])
async def get_history(
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
    principal: ViewPrincipal,
    service: ServiceDep,
) -> list[AiGenerationResponse]:
    """Every AI generation ever produced for one record, newest first (§16)."""
    generations = await service.history(principal, entity_type=entity_type, entity_id=entity_id)
    return [AiGenerationResponse.model_validate(g) for g in generations]


__all__ = ["router"]
