"""Saved view routes, mounted at ``/crm/views``.

Gated on the ``views`` permission module. Note what that module does *not*
grant: a view names filters over a record type, and running it goes through
that record type's own list endpoint, behind that endpoint's permission and
record-level visibility. So holding ``views.VIEW`` and nothing else lets a
caller read the saved question and reach no record through it.

Every response carries ``can_edit`` for the caller who asked. That is a
convenience for the UI and never the control: the write endpoints resolve
ownership themselves, and a request to change somebody else's view is refused
whatever the client believed.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.common import CrmEntityType
from app.products.crm.views.models import SavedView
from app.products.crm.views.schemas import (
    SavedViewCreate,
    SavedViewResponse,
    SavedViewUpdate,
)
from app.products.crm.views.service import MODULE, SavedViewService

router = APIRouter()


def get_service(session: DbSession) -> SavedViewService:
    return SavedViewService(session)


ServiceDep = Annotated[SavedViewService, Depends(get_service)]


def _response(
    view: SavedView, principal: Principal, service: SavedViewService
) -> SavedViewResponse:
    payload = SavedViewResponse.model_validate(view)
    payload.can_edit = service.may_edit(principal, view)
    return payload


@router.get("", response_model=list[SavedViewResponse])
async def list_views(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    entity_type: Annotated[CrmEntityType, Query()],
) -> list[SavedViewResponse]:
    """Views on one record type that this caller may read.

    Unpaginated, and narrowed to one entity type rather than defaulting to all
    of them. Both follow from the caller: this is read on every render of one
    list screen, which wants that screen's views and all of them.
    """
    views = await service.list_for_entity(principal, entity_type)
    return [_response(view, principal, service) for view in views]


@router.post("", response_model=SavedViewResponse, status_code=status.HTTP_201_CREATED)
async def create_view(
    payload: SavedViewCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> SavedViewResponse:
    """Save a view, owned by the caller. A name they already used returns 409."""
    view = await service.create_view(principal, values=payload.model_dump(exclude_unset=True))
    return _response(view, principal, service)


@router.get("/{view_id}", response_model=SavedViewResponse)
async def get_view(
    view_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> SavedViewResponse:
    """One view. A colleague's private view is a 404, like a missing one."""
    view = await service.get_readable(principal, view_id)
    return _response(view, principal, service)


@router.patch("/{view_id}", response_model=SavedViewResponse)
async def update_view(
    view_id: uuid.UUID,
    payload: SavedViewUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> SavedViewResponse:
    """Change a view the caller owns, or any view if they hold ``views.VIEW_ALL``."""
    view = await service.get_editable(principal, view_id)
    updated = await service.update_view(
        principal, view, values=payload.model_dump(exclude_unset=True)
    )
    return _response(updated, principal, service)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view(
    view_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    """Remove a saved view. No record is touched — a view holds none."""
    view = await service.get_editable(principal, view_id)
    await service.delete_view(principal, view)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
