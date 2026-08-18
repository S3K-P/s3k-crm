"""Lead source routes, mounted at ``/crm/lead-sources``.

Gated on the ``lead_sources`` permission module, which is separate from
``leads``: classifying where business comes from is an administrative concern,
and a rep who may edit leads need not be able to redefine the taxonomy.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.leads.models import LeadSourceStatus
from app.products.crm.leads.schemas import (
    LeadSourceCreate,
    LeadSourceResponse,
    LeadSourceUpdate,
)
from app.products.crm.leads.source_service import LeadSourceService
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()

MODULE = "lead_sources"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> LeadSourceService:
    return LeadSourceService(session)


ServiceDep = Annotated[LeadSourceService, Depends(get_service)]


@router.get("", response_model=Page[LeadSourceResponse])
async def list_lead_sources(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    source_status: Annotated[LeadSourceStatus | None, Query(alias="status")] = None,
    category: Annotated[str | None, Query(max_length=120)] = None,
) -> Page[LeadSourceResponse]:
    """List lead sources with their live lead counts."""
    filters = service.build_filters(search=search, status=source_status, category=category)
    items, total = await service.list_sources(
        principal.organization_id, params=params, filters=filters
    )
    counts = await service.lead_counts(principal.organization_id)

    payload: list[LeadSourceResponse] = []
    for item in items:
        response = LeadSourceResponse.model_validate(item)
        response.lead_count = counts.get(item.id, 0)
        payload.append(response)
    return Page.build(payload, total=total, params=params)


@router.post("", response_model=LeadSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_source(
    payload: LeadSourceCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> LeadSourceResponse:
    """Create a lead source. A duplicate name returns 409."""
    source = await service.create_source(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return LeadSourceResponse.model_validate(source)


@router.get("/{source_id}", response_model=LeadSourceResponse)
async def get_lead_source(
    source_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> LeadSourceResponse:
    source = await service.get_or_404(source_id, principal.organization_id)
    response = LeadSourceResponse.model_validate(source)
    counts = await service.lead_counts(principal.organization_id)
    response.lead_count = counts.get(source.id, 0)
    return response


@router.patch("/{source_id}", response_model=LeadSourceResponse)
async def update_lead_source(
    source_id: uuid.UUID,
    payload: LeadSourceUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LeadSourceResponse:
    source = await service.get_or_404(source_id, principal.organization_id)
    updated = await service.update_source(
        source, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return LeadSourceResponse.model_validate(updated)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_lead_source(
    source_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    """Archive a lead source. Blocked while leads still reference it."""
    source = await service.get_or_404(source_id, principal.organization_id)
    await service.archive_source(source, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
