"""Note routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.common import CrmEntityType
from app.products.crm.notes.schemas import NoteCreate, NoteResponse, NoteUpdate
from app.products.crm.notes.service import NoteService
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()

MODULE = "notes"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> NoteService:
    return NoteService(session)


ServiceDep = Annotated[NoteService, Depends(get_service)]


@router.get("", response_model=Page[NoteResponse])
async def list_notes(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    related_entity_type: Annotated[CrmEntityType | None, Query()] = None,
    related_entity_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[NoteResponse]:
    """List notes the caller may see, newest first.

    Another user's private notes are excluded by the query itself, so they are
    never fetched and never counted.
    """
    filters = service.build_filters(
        viewer_id=principal.user_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    items, total = await service.list_notes(
        principal.organization_id, params=params, filters=filters
    )
    return Page.build(
        [NoteResponse.model_validate(item) for item in items], total=total, params=params
    )


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> NoteResponse:
    """Attach a note to a record. A link to another tenant's record is rejected."""
    note = await service.create_note(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return NoteResponse.model_validate(note)


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> NoteResponse:
    """Fetch one note. Someone else's private note returns 404."""
    note = await service.get_visible_or_404(
        note_id, principal.organization_id, viewer_id=principal.user_id
    )
    return NoteResponse.model_validate(note)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> NoteResponse:
    """Edit a note. Authors only, regardless of permission level."""
    note = await service.get_visible_or_404(
        note_id, principal.organization_id, viewer_id=principal.user_id
    )
    updated = await service.update_note(
        note, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return NoteResponse.model_validate(updated)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_note(
    note_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    """Archive a note. Authors only."""
    note = await service.get_visible_or_404(
        note_id, principal.organization_id, viewer_id=principal.user_id
    )
    await service.delete_note(note, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
