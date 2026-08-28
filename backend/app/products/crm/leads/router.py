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
    ConversionMatchAccount,
    ConversionMatchContact,
    LeadConversionResponse,
    LeadConversionSuggestions,
    LeadConvertRequest,
    LeadCreate,
    LeadOwnerChange,
    LeadResponse,
    LeadStatusChange,
    LeadStatusCounts,
    LeadUpdate,
)
from app.products.crm.leads.service import LeadService
from app.products.crm.shared.csv_export import collect_rows, csv_response
from app.products.crm.shared.pagination import Page, PageParams, page_params
from app.products.crm.shared.visibility import RecordVisibility

router = APIRouter()

MODULE = "leads"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> LeadService:
    return LeadService(session)


ServiceDep = Annotated[LeadService, Depends(get_service)]


def visible_to(principal: Principal) -> RecordVisibility:
    """What this caller may read in this module (ADR-010).

    Passed to every read below, including the reads that back an edit or a
    delete, so a record outside the caller's visibility is a 404 on every
    verb rather than only on the list.
    """
    return RecordVisibility.for_module(principal, MODULE)


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
        principal.organization_id,
        params=params,
        filters=filters,
        visibility=visible_to(principal),
    )
    return Page.build(
        [LeadResponse.model_validate(item) for item in items], total=total, params=params
    )


@router.get("/export", response_class=Response)
async def export_leads(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EXPORT))],
    service: ServiceDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    lead_status: Annotated[LeadStatus | None, Query(alias="status")] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
    lead_source_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Download the leads this caller can see, as CSV.

    Declared before the id route: FastAPI matches in registration order, and
    ``/{lead_id}`` would otherwise claim ``/export`` and reject it as a
    malformed UUID.

    Takes the same filters as the list endpoint and resolves rows through the
    same service call and the same ``RecordVisibility``, so the file contains
    exactly the rows on screen. ``EXPORT`` is a separate permission from
    ``VIEW``: reading a record in the application and removing a copy of it
    from every control the application has are different acts.
    """
    filters = service.build_filters(
        search=search, status=lead_status, owner_id=owner_id, lead_source_id=lead_source_id
    )
    rows = await collect_rows(
        service,
        principal.organization_id,
        filters=filters,
        visibility=visible_to(principal),
        sort_by="last_name",
        sort_dir="asc",
    )
    await service.record_export(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        row_count=len(rows),
        filters_applied={
            "search": search,
            "status": lead_status,
            "owner_id": owner_id,
            "lead_source_id": lead_source_id,
        },
    )
    return csv_response(rows, LeadResponse, entity_plural="leads")


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
    allow_duplicate: Annotated[bool, Query()] = False,
) -> LeadResponse:
    """Create a lead. New leads always start at ``NEW``."""
    values = payload.model_dump(exclude_unset=True)
    if values.get("email") is not None:
        values["email"] = str(values["email"])
    lead = await service.create_lead(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=values,
        allow_duplicate=allow_duplicate,
    )
    return LeadResponse.model_validate(lead)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> LeadResponse:
    lead = await service.get_or_404(
        lead_id, principal.organization_id, visibility=visible_to(principal)
    )
    return LeadResponse.model_validate(lead)


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: uuid.UUID,
    payload: LeadUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LeadResponse:
    """Update lead attributes. Status changes go through ``/status``."""
    lead = await service.get_or_404(
        lead_id, principal.organization_id, visibility=visible_to(principal)
    )
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
    lead = await service.get_or_404(
        lead_id, principal.organization_id, visibility=visible_to(principal)
    )
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
    lead = await service.get_or_404(
        lead_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.assign_owner(
        lead, owner_id=payload.owner_id, actor_id=principal.user_id
    )
    return LeadResponse.model_validate(updated)


@router.get("/{lead_id}/conversion-suggestions", response_model=LeadConversionSuggestions)
async def lead_conversion_suggestions(
    lead_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> LeadConversionSuggestions:
    """Existing accounts/contacts the convert UI should offer to link."""
    lead = await service.get_or_404(
        lead_id, principal.organization_id, visibility=visible_to(principal)
    )
    suggestions = await service.conversion_suggestions(lead)
    return LeadConversionSuggestions(
        matching_accounts=[
            ConversionMatchAccount(id=account.id, name=account.name)
            for account in suggestions.matching_accounts
        ],
        matching_contacts=[
            ConversionMatchContact(
                id=contact.id,
                full_name=contact.full_name,
                email=contact.email,
                account_id=contact.account_id,
            )
            for contact in suggestions.matching_contacts
        ],
        suggested_account_name=suggestions.suggested_account_name,
        suggested_contact_name=suggestions.suggested_contact_name,
        suggested_opportunity_name=suggestions.suggested_opportunity_name,
        suggested_deal_value=suggestions.suggested_deal_value,
    )


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
    lead = await service.get_or_404(
        lead_id, principal.organization_id, visibility=visible_to(principal)
    )
    result = await service.convert(
        lead,
        actor_id=principal.user_id,
        account_id=payload.account_id,
        contact_id=payload.contact_id,
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
    lead = await service.get_or_404(
        lead_id, principal.organization_id, visibility=visible_to(principal)
    )
    await service.soft_delete(lead, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
