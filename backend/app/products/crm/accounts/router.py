"""Account routes.

Every endpoint declares the permission it needs. The dependency resolves the
caller's roles from the database on each request, so nothing the client sends —
including any permission list the frontend may hold — influences the outcome.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.models import Account, AccountStatus
from app.products.crm.accounts.schemas import (
    AccountBulkUpdate,
    AccountCreate,
    AccountOverviewResponse,
    AccountResponse,
    AccountTimelineEntryResponse,
    AccountUpdate,
)
from app.products.crm.accounts.service import AccountService
from app.products.crm.common import CrmEntityType
from app.products.crm.custom_fields.query import CustomFieldQueryDep
from app.products.crm.reports.custom import build_advanced_filter_predicate
from app.products.crm.reports.fields import ReportEntity
from app.products.crm.shared.advanced_filter_query import AdvancedFilterDep
from app.products.crm.shared.csv_export import collect_rows, csv_response
from app.products.crm.shared.pagination import Page, PageParams, page_params
from app.products.crm.shared.schemas import BulkIdsRequest, BulkOperationResult
from app.products.crm.shared.visibility import RecordVisibility

router = APIRouter()

MODULE = "accounts"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> AccountService:
    return AccountService(session)


ServiceDep = Annotated[AccountService, Depends(get_service)]


def visible_to(principal: Principal) -> RecordVisibility:
    """What this caller may read in this module (ADR-010).

    Passed to every read below, including the reads that back an edit or a
    delete, so a record outside the caller's visibility is a 404 on every
    verb rather than only on the list.
    """
    return RecordVisibility.for_module(principal, MODULE)


@router.get("", response_model=Page[AccountResponse])
async def list_accounts(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    session: DbSession,
    params: PageParamsDep,
    custom: CustomFieldQueryDep,
    advanced: AdvancedFilterDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    account_status: Annotated[AccountStatus | None, Query(alias="status")] = None,
    industry: Annotated[str | None, Query(max_length=120)] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[AccountResponse]:
    """List accounts in the caller's organization.

    Tenant-defined fields participate: ``?cf_<api_name>=`` filters on one,
    ``?cf_<api_name>__gte=`` and friends compare, and ``?sort_by=cf_<api_name>``
    orders by one. Names are resolved against this organization's own
    definitions before any SQL is built (``custom_fields/query.py``), so an
    unrecognised one is a 422 rather than a filter on nothing.

    ``?advanced_filter=`` (Checkpoint 5): see ``leads.router.list_leads``'s
    docstring — the mechanism is identical, entity-parameterised.
    """
    filters = service.build_filters(
        search=search, status=account_status, industry=industry, owner_id=owner_id
    )
    custom_filters, custom_sort = await custom.resolve(
        Account,
        organization_id=principal.organization_id,
        entity_type=CrmEntityType.ACCOUNT,
    )
    filters = [*filters, *custom_filters]
    if advanced is not None:
        predicate = await build_advanced_filter_predicate(
            session, principal.organization_id, ReportEntity.ACCOUNT, advanced
        )
        if predicate is not None:
            filters.append(predicate)
    items, total = await service.list_accounts(
        principal.organization_id,
        params=params,
        filters=filters,
        visibility=visible_to(principal),
        sort_column=custom_sort,
    )
    return Page.build(
        [AccountResponse.model_validate(item) for item in items], total=total, params=params
    )


@router.get("/export", response_class=Response)
async def export_accounts(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EXPORT))],
    service: ServiceDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    account_status: Annotated[AccountStatus | None, Query(alias="status")] = None,
    industry: Annotated[str | None, Query(max_length=120)] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Download the accounts this caller can see, as CSV.

    Declared before ``/{account_id}``: FastAPI matches in registration order,
    and the id route would otherwise claim ``/export`` and reject it as a
    malformed UUID.

    Takes the same filters as the list endpoint and resolves rows through the
    same service call and the same ``RecordVisibility``, so the file contains
    exactly the rows on screen. ``EXPORT`` is a separate permission from
    ``VIEW``: reading a record in the application and removing a copy of it
    from every control the application has are different acts.
    """
    filters = service.build_filters(
        search=search, status=account_status, industry=industry, owner_id=owner_id
    )
    rows = await collect_rows(
        service,
        principal.organization_id,
        filters=filters,
        visibility=visible_to(principal),
        sort_by="name",
        sort_dir="asc",
    )
    await service.record_export(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        row_count=len(rows),
        filters_applied={
            "search": search,
            "status": account_status,
            "industry": industry,
            "owner_id": owner_id,
        },
    )
    return csv_response(rows, AccountResponse, entity_plural="accounts")


@router.post("/bulk-update", response_model=BulkOperationResult)
async def bulk_update_accounts(
    payload: AccountBulkUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> BulkOperationResult:
    return await service.bulk_update(
        payload.ids,
        principal.organization_id,
        actor_id=principal.user_id,
        values=payload.values.model_dump(exclude_unset=True),
        visibility=visible_to(principal),
    )


@router.post("/bulk-delete", response_model=BulkOperationResult)
async def bulk_delete_accounts(
    payload: BulkIdsRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> BulkOperationResult:
    return await service.bulk_delete(
        payload.ids,
        principal.organization_id,
        actor_id=principal.user_id,
        visibility=visible_to(principal),
    )


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
    allow_duplicate: Annotated[bool, Query()] = False,
) -> AccountResponse:
    """Create an account. A duplicate name returns 409 unless overridden."""
    account = await service.create_account(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
        allow_duplicate=allow_duplicate,
    )
    return AccountResponse.model_validate(account)


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> AccountResponse:
    """Fetch one account. An id from another organization returns 404."""
    account = await service.get_or_404(
        account_id, principal.organization_id, visibility=visible_to(principal)
    )
    return AccountResponse.model_validate(account)


@router.get("/{account_id}/overview", response_model=AccountOverviewResponse)
async def get_account_overview(
    account_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> AccountOverviewResponse:
    """The Account 360 summary header: contacts, pipeline, tasks, owner.

    A handful of aggregate queries regardless of how many contacts or deals
    the account has — see ``AccountOverviewRepository`` — and every count is
    narrowed to what this caller may see, the same as the underlying lists.
    """
    account = await service.get_or_404(
        account_id, principal.organization_id, visibility=visible_to(principal)
    )
    overview = await service.overview(account, principal)
    # `AccountOverview` is a `slots=True` dataclass, so it has no `__dict__`;
    # `asdict` reads `__dataclass_fields__` instead.
    return AccountOverviewResponse(**asdict(overview))


@router.get("/{account_id}/timeline", response_model=list[AccountTimelineEntryResponse])
async def get_account_timeline(
    account_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AccountTimelineEntryResponse]:
    """Everything recorded against this account, merged and newest first.

    Combines logged activities, deal creation, deal stage changes and contact
    creation. Notes are excluded — see ``accounts/overview.py`` for why.
    """
    account = await service.get_or_404(
        account_id, principal.organization_id, visibility=visible_to(principal)
    )
    entries = await service.timeline(account, principal, limit=limit)
    return [AccountTimelineEntryResponse(**asdict(entry)) for entry in entries]


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> AccountResponse:
    """Partially update an account."""
    account = await service.get_or_404(
        account_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.update(
        account, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return AccountResponse.model_validate(updated)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_account(
    account_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    """Archive an account. Blocked while it has open opportunities."""
    account = await service.get_or_404(
        account_id, principal.organization_id, visibility=visible_to(principal)
    )
    await service.archive_account(account, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
