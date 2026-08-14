"""Lead routes, including the status transition and conversion workflows."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.leads.models import LeadStatus
from app.products.crm.leads.schemas import (
    LeadConversionResponse,
    LeadConvertRequest,
    LeadCreate,
    LeadOwnerChange,
    LeadResponse,
    LeadStatusChange,
    LeadStatusCounts,
    LeadUpdate,
)
from app.products.crm.leads.service import LeadService
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()

MODULE = "leads"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> LeadService:
    return LeadService(session)


ServiceDep = Annotated[LeadService, Depends(get_service)]


@router.get("", response_model=Page[LeadResponse])
async def list_leads(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    lead_status: Annotated[LeadStatus | None, Query(alias="status")] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
    lead_source_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[LeadResponse]:
    """List leads in the caller's organization."""
    filters = service.build_filters(
        search=search, status=lead_status, owner_id=owner_id, lead_source_id=lead_source_id
    )
    items, total = await service.list_leads(
        principal.organization_id, params=params, filters=filters
    )
    return Page.build(
        [LeadResponse.model_validate(item) for item in items], total=total, params=params
    )


@router.get("/status-counts", response_model=LeadStatusCounts)
async def lead_status_counts(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> LeadStatusCounts:
    """Per-status totals backing the kanban column headers."""
    return LeadStatusCounts(counts=await service.counts_by_status(principal.organization_id))


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> LeadResponse:
    """Create a lead. New leads always start at ``NEW``."""
    values = payload.model_dump(exclude_unset=True)
    if values.get("email") is not None:
        values["email"] = str(values["email"])
    lead = await service.create(
        organization_id=principal.organization_id, actor_id=principal.user_id, values=values
    )
    return LeadResponse.model_validate(lead)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> LeadResponse:
    lead = await service.get_or_404(lead_id, principal.organization_id)
    return LeadResponse.model_validate(lead)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LeadResponse:
    """Update lead attributes. Status changes go through ``/status``."""
    lead = await service.get_or_404(lead_id, principal.organization_id)
    values = payload.model_dump(exclude_unset=True)
    if values.get("email") is not None:
        values["email"] = str(values["email"])
    updated = await service.update(lead, actor_id=principal.user_id, values=values)
    return LeadResponse.model_validate(updated)


@router.post("/{lead_id}/status", response_model=LeadResponse)
async def change_lead_status(
    lead_id: uuid.UUID,
    payload: LeadStatusChange,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LeadResponse:
    """Move a lead through the lifecycle. Illegal transitions return 422."""
    lead = await service.get_or_404(lead_id, principal.organization_id)
    updated = await service.change_status(
        lead,
        new_status=payload.status,
        actor_id=principal.user_id,
        lost_reason=payload.lost_reason,
    )
    return LeadResponse.model_validate(updated)


@router.post("/{lead_id}/owner", response_model=LeadResponse)
async def assign_lead_owner(
    lead_id: uuid.UUID,
    payload: LeadOwnerChange,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LeadResponse:
    lead = await service.get_or_404(lead_id, principal.organization_id)
    updated = await service.assign_owner(
        lead, owner_id=payload.owner_id, actor_id=principal.user_id
    )
    return LeadResponse.model_validate(updated)


@router.post(
    "/{lead_id}/convert",
    response_model=LeadConversionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def convert_lead(
    lead_id: uuid.UUID,
    payload: LeadConvertRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LeadConversionResponse:
    """Convert a qualified lead into an account, contact and optional deal."""
    lead = await service.get_or_404(lead_id, principal.organization_id)
    result = await service.convert(
        lead,
        actor_id=principal.user_id,
        account_id=payload.account_id,
        create_opportunity=payload.create_opportunity,
        opportunity_name=payload.opportunity_name,
        opportunity_value=payload.opportunity_value,
        stage_id=payload.stage_id,
        expected_close_date=payload.expected_close_date,
    )
    return LeadConversionResponse(
        lead_id=result.lead.id,
        account_id=result.account.id,
        contact_id=result.contact.id,
        opportunity_id=result.opportunity.id if result.opportunity else None,
    )


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_lead(
    lead_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    lead = await service.get_or_404(lead_id, principal.organization_id)
    await service.soft_delete(lead, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
