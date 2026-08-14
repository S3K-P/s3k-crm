"""Account routes.

Every endpoint declares the permission it needs. The dependency resolves the
caller's roles from the database on each request, so nothing the client sends —
including any permission list the frontend may hold — influences the outcome.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.models import AccountStatus
from app.products.crm.accounts.schemas import (
    AccountCreate,
    AccountResponse,
    AccountUpdate,
)
from app.products.crm.accounts.service import AccountService
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()

MODULE = "accounts"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> AccountService:
    return AccountService(session)


ServiceDep = Annotated[AccountService, Depends(get_service)]


@router.get("", response_model=Page[AccountResponse])
async def list_accounts(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    account_status: Annotated[AccountStatus | None, Query(alias="status")] = None,
    industry: Annotated[str | None, Query(max_length=120)] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[AccountResponse]:
    """List accounts in the caller's organization."""
    filters = service.build_filters(
        search=search, status=account_status, industry=industry, owner_id=owner_id
    )
    items, total = await service.list_accounts(
        principal.organization_id, params=params, filters=filters
    )
    return Page.build(
        [AccountResponse.model_validate(item) for item in items], total=total, params=params
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
    account = await service.get_or_404(account_id, principal.organization_id)
    return AccountResponse.model_validate(account)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: uuid.UUID,
    payload: AccountUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> AccountResponse:
    """Partially update an account."""
    account = await service.get_or_404(account_id, principal.organization_id)
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
    account = await service.get_or_404(account_id, principal.organization_id)
    await service.archive_account(account, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
