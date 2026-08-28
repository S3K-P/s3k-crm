"""Contact routes.

Every endpoint declares the permission it needs; the dependency resolves the
caller's roles from the database on each request, so nothing the client sends
influences the outcome.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.contacts.models import ContactStatus
from app.products.crm.contacts.schemas import (
    ContactCreate,
    ContactResponse,
    ContactUpdate,
)
from app.products.crm.contacts.service import ContactService
from app.products.crm.shared.csv_export import collect_rows, csv_response
from app.products.crm.shared.pagination import Page, PageParams, page_params
from app.products.crm.shared.visibility import RecordVisibility

router = APIRouter()

MODULE = "contacts"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> ContactService:
    return ContactService(session)


ServiceDep = Annotated[ContactService, Depends(get_service)]


def visible_to(principal: Principal) -> RecordVisibility:
    """What this caller may read in this module (ADR-010).

    Passed to every read below, including the reads that back an edit or a
    delete, so a record outside the caller's visibility is a 404 on every
    verb rather than only on the list.
    """
    return RecordVisibility.for_module(principal, MODULE)


@router.get("", response_model=Page[ContactResponse])
async def list_contacts(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    contact_status: Annotated[ContactStatus | None, Query(alias="status")] = None,
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[ContactResponse]:
    """List contacts in the caller's organization."""
    filters = service.build_filters(
        search=search, status=contact_status, account_id=account_id, owner_id=owner_id
    )
    items, total = await service.list_contacts(
        principal.organization_id,
        params=params,
        filters=filters,
        visibility=visible_to(principal),
    )
    return Page.build(
        [ContactResponse.model_validate(item) for item in items], total=total, params=params
    )


@router.get("/export", response_class=Response)
async def export_contacts(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EXPORT))],
    service: ServiceDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    contact_status: Annotated[ContactStatus | None, Query(alias="status")] = None,
    account_id: Annotated[uuid.UUID | None, Query()] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Response:
    """Download the contacts this caller can see, as CSV.

    Declared before the id route: FastAPI matches in registration order, and
    ``/{contact_id}`` would otherwise claim ``/export`` and reject it as a
    malformed UUID.

    Takes the same filters as the list endpoint and resolves rows through the
    same service call and the same ``RecordVisibility``, so the file contains
    exactly the rows on screen. ``EXPORT`` is a separate permission from
    ``VIEW``: reading a record in the application and removing a copy of it
    from every control the application has are different acts.
    """
    filters = service.build_filters(
        search=search, status=contact_status, account_id=account_id, owner_id=owner_id
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
            "status": contact_status,
            "account_id": account_id,
            "owner_id": owner_id,
        },
    )
    return csv_response(rows, ContactResponse, entity_plural="contacts")


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
    allow_duplicate: Annotated[bool, Query()] = False,
) -> ContactResponse:
    """Create a contact. A duplicate email returns 409 unless overridden."""
    values = payload.model_dump(exclude_unset=True)
    if values.get("email") is not None:
        values["email"] = str(values["email"])
    contact = await service.create_contact(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=values,
        allow_duplicate=allow_duplicate,
    )
    return ContactResponse.model_validate(contact)


@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(
    contact_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> ContactResponse:
    """Fetch one contact. An id from another organization returns 404."""
    contact = await service.get_or_404(
        contact_id, principal.organization_id, visibility=visible_to(principal)
    )
    return ContactResponse.model_validate(contact)


@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
    allow_duplicate: Annotated[bool, Query()] = False,
) -> ContactResponse:
    """Partially update a contact."""
    contact = await service.get_or_404(
        contact_id, principal.organization_id, visibility=visible_to(principal)
    )
    values = payload.model_dump(exclude_unset=True)
    if values.get("email") is not None:
        values["email"] = str(values["email"])
    updated = await service.update_contact(
        contact,
        actor_id=principal.user_id,
        values=values,
        allow_duplicate=allow_duplicate,
    )
    return ContactResponse.model_validate(updated)


@router.post("/{contact_id}/primary", response_model=ContactResponse)
async def make_primary(
    contact_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> ContactResponse:
    """Promote a contact to primary on its account, demoting the incumbent."""
    contact = await service.get_or_404(
        contact_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.set_primary(contact, actor_id=principal.user_id)
    return ContactResponse.model_validate(updated)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_contact(
    contact_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    """Archive a contact, clearing it from its account if it was primary."""
    contact = await service.get_or_404(
        contact_id, principal.organization_id, visibility=visible_to(principal)
    )
    await service.archive_contact(contact, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
