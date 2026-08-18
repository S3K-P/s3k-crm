"""Campaign routes, including membership management."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.campaigns.models import CampaignStatus, CampaignType
from app.products.crm.campaigns.schemas import (
    CampaignCreate,
    CampaignMemberCreate,
    CampaignMemberResponse,
    CampaignResponse,
    CampaignUpdate,
)
from app.products.crm.campaigns.service import CampaignService
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()

MODULE = "campaigns"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> CampaignService:
    return CampaignService(session)


ServiceDep = Annotated[CampaignService, Depends(get_service)]


@router.get("", response_model=Page[CampaignResponse])
async def list_campaigns(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    campaign_status: Annotated[CampaignStatus | None, Query(alias="status")] = None,
    campaign_type: Annotated[CampaignType | None, Query(alias="type")] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[CampaignResponse]:
    """List campaigns with their enrolled-member counts."""
    filters = service.build_filters(
        search=search, status=campaign_status, campaign_type=campaign_type, owner_id=owner_id
    )
    items, total = await service.list_campaigns(
        principal.organization_id, params=params, filters=filters
    )
    counts = await service.member_counts(principal.organization_id)

    payload: list[CampaignResponse] = []
    for item in items:
        response = CampaignResponse.model_validate(item)
        response.member_count = counts.get(item.id, 0)
        payload.append(response)
    return Page.build(payload, total=total, params=params)


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> CampaignResponse:
    """Create a campaign. Metrics start at zero and are derived, never set."""
    campaign = await service.create_campaign(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return CampaignResponse.model_validate(campaign)


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> CampaignResponse:
    """Fetch one campaign with freshly derived metrics."""
    campaign = await service.get_or_404(campaign_id, principal.organization_id)
    await service.recompute_metrics(campaign)
    response = CampaignResponse.model_validate(campaign)
    response.member_count = len(await service.list_members(campaign))
    return response


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    payload: CampaignUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> CampaignResponse:
    campaign = await service.get_or_404(campaign_id, principal.organization_id)
    updated = await service.update_campaign(
        campaign, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return CampaignResponse.model_validate(updated)


@router.get("/{campaign_id}/members", response_model=list[CampaignMemberResponse])
async def list_campaign_members(
    campaign_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> list[CampaignMemberResponse]:
    """Leads and contacts enrolled in this campaign."""
    campaign = await service.get_or_404(campaign_id, principal.organization_id)
    members = await service.list_members(campaign)
    return [CampaignMemberResponse.model_validate(member) for member in members]


@router.post(
    "/{campaign_id}/members",
    response_model=CampaignMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_campaign_member(
    campaign_id: uuid.UUID,
    payload: CampaignMemberCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> CampaignMemberResponse:
    """Enrol a lead or contact. Another tenant's record returns 404."""
    campaign = await service.get_or_404(campaign_id, principal.organization_id)
    member = await service.add_member(
        campaign, entity_type=payload.entity_type, entity_id=payload.entity_id
    )
    return CampaignMemberResponse.model_validate(member)


@router.delete(
    "/{campaign_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_campaign_member(
    campaign_id: uuid.UUID,
    member_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> Response:
    campaign = await service.get_or_404(campaign_id, principal.organization_id)
    await service.remove_member(campaign, member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_campaign(
    campaign_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    campaign = await service.get_or_404(campaign_id, principal.organization_id)
    await service.soft_delete(campaign, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
