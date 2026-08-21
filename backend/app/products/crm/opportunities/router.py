"""Opportunity routes, including the stage lifecycle."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.core.exceptions import NotFoundError
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.service import AccountService
from app.products.crm.opportunities.schemas import (
    OpportunityCreate,
    OpportunityReopen,
    OpportunityResponse,
    OpportunityStageChange,
    OpportunityUpdate,
    PipelineStageResponse,
    StageHistoryEntry,
)
from app.products.crm.opportunities.service import OpportunityService
from app.products.crm.shared.pagination import Page, PageParams, page_params
from app.products.crm.shared.visibility import RecordVisibility

router = APIRouter()

MODULE = "opportunities"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> OpportunityService:
    return OpportunityService(session)


ServiceDep = Annotated[OpportunityService, Depends(get_service)]


def visible_to(principal: Principal) -> RecordVisibility:
    """What this caller may read in this module (ADR-010).

    Passed to every read below, including the reads that back an edit or a
    delete, so a record outside the caller's visibility is a 404 on every
    verb rather than only on the list.
    """
    return RecordVisibility.for_module(principal, MODULE)


@router.get("", response_model=Page[OpportunityResponse])
async def list_opportunities(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    stage_id: Annotated[uuid.UUID | None, Query()] = None,
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    primary_contact_id: Annotated[uuid.UUID | None, Query()] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
    is_open: Annotated[bool | None, Query()] = None,
) -> Page[OpportunityResponse]:
    """List opportunities in the caller's organization."""
    filters = service.build_filters(
        search=search,
        stage_id=stage_id,
        account_id=account_id,
        primary_contact_id=primary_contact_id,
        owner_id=owner_id,
        is_open=is_open,
    )
    items, total = await service.list_opportunities(
        principal.organization_id,
        params=params,
        filters=filters,
        visibility=visible_to(principal),
    )
    return Page.build(
        [OpportunityResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@router.get("/stages", response_model=list[PipelineStageResponse])
async def list_stages(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> list[PipelineStageResponse]:
    """The organization's pipeline stages, in order."""
    stages = await service.list_stages(principal.organization_id)
    return [PipelineStageResponse.model_validate(stage) for stage in stages]


@router.post("", response_model=OpportunityResponse, status_code=status.HTTP_201_CREATED)
async def create_opportunity(
    payload: OpportunityCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
    session: DbSession,
) -> OpportunityResponse:
    """Create a deal.

    The account and stage are both re-checked against the caller's
    organization, so neither can be borrowed from another tenant.
    """
    accounts = AccountService(session)
    if not await accounts.exists(payload.account_id, principal.organization_id):
        raise NotFoundError("Account not found.")
    await service.get_stage(payload.stage_id, principal.organization_id)

    opportunity = await service.create(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return OpportunityResponse.model_validate(opportunity)


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> OpportunityResponse:
    opportunity = await service.get_or_404(
        opportunity_id, principal.organization_id, visibility=visible_to(principal)
    )
    return OpportunityResponse.model_validate(opportunity)


@router.patch("/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    opportunity_id: uuid.UUID,
    payload: OpportunityUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> OpportunityResponse:
    """Update an open deal. Editing a closed one returns 409."""
    opportunity = await service.get_or_404(
        opportunity_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.update_open(
        opportunity, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return OpportunityResponse.model_validate(updated)


@router.post("/{opportunity_id}/stage", response_model=OpportunityResponse)
async def change_stage(
    opportunity_id: uuid.UUID,
    payload: OpportunityStageChange,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> OpportunityResponse:
    """Move a deal to another stage, closing it if the stage is terminal."""
    opportunity = await service.get_or_404(
        opportunity_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.change_stage(
        opportunity,
        stage_id=payload.stage_id,
        actor_id=principal.user_id,
        note=payload.note,
        loss_reason=payload.loss_reason,
        win_reason=payload.win_reason,
    )
    return OpportunityResponse.model_validate(updated)


@router.post("/{opportunity_id}/reopen", response_model=OpportunityResponse)
async def reopen_opportunity(
    opportunity_id: uuid.UUID,
    payload: OpportunityReopen,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> OpportunityResponse:
    """Return a closed deal to an open stage."""
    opportunity = await service.get_or_404(
        opportunity_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.reopen(
        opportunity, stage_id=payload.stage_id, actor_id=principal.user_id
    )
    return OpportunityResponse.model_validate(updated)


@router.get("/{opportunity_id}/history", response_model=list[StageHistoryEntry])
async def stage_history(
    opportunity_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> list[StageHistoryEntry]:
    """Every stage movement for this deal, newest first."""
    opportunity = await service.get_or_404(
        opportunity_id, principal.organization_id, visibility=visible_to(principal)
    )
    entries = await service.stage_history(opportunity)
    return [StageHistoryEntry.model_validate(entry) for entry in entries]


@router.delete("/{opportunity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_opportunity(
    opportunity_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    opportunity = await service.get_or_404(
        opportunity_id, principal.organization_id, visibility=visible_to(principal)
    )
    await service.soft_delete(opportunity, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
