"""Task routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.common import CrmEntityType, Priority
from app.products.crm.shared.pagination import Page, PageParams, page_params
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import TaskStatus
from app.products.crm.tasks.schemas import (
    TaskCreate,
    TaskResponse,
    TaskStatusCounts,
    TaskUpdate,
)
from app.products.crm.tasks.service import TaskService

router = APIRouter()

MODULE = "tasks"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


class TaskStatusChange(BaseModel):
    status: TaskStatus


def get_service(session: DbSession) -> TaskService:
    return TaskService(session)


ServiceDep = Annotated[TaskService, Depends(get_service)]


def visible_to(principal: Principal) -> RecordVisibility:
    """What this caller may read in this module (ADR-010).

    Passed to every read below, including the reads that back an edit or a
    delete, so a record outside the caller's visibility is a 404 on every
    verb rather than only on the list.
    """
    return RecordVisibility.for_module(principal, MODULE)


@router.get("", response_model=Page[TaskResponse])
async def list_tasks(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    priority: Annotated[Priority | None, Query()] = None,
    assigned_to_id: Annotated[uuid.UUID | None, Query()] = None,
    related_entity_type: Annotated[CrmEntityType | None, Query()] = None,
    related_entity_id: Annotated[uuid.UUID | None, Query()] = None,
    open_only: Annotated[bool, Query()] = False,
) -> Page[TaskResponse]:
    """List tasks in the caller's organization."""
    filters = service.build_filters(
        search=search,
        status=task_status,
        priority=priority,
        assigned_to_id=assigned_to_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        open_only=open_only,
    )
    items, total = await service.list_tasks(
        principal.organization_id,
        params=params,
        filters=filters,
        visibility=visible_to(principal),
    )
    return Page.build(
        [TaskResponse.model_validate(item) for item in items], total=total, params=params
    )


@router.get("/status-counts", response_model=TaskStatusCounts)
async def task_status_counts(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> TaskStatusCounts:
    """Per-status totals for board columns and summary chips."""
    return TaskStatusCounts(counts=await service.counts_by_status(principal.organization_id))


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> TaskResponse:
    """Create a task. A link to another tenant's record is rejected."""
    task = await service.create_task(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return TaskResponse.model_validate(task)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> TaskResponse:
    task = await service.get_or_404(
        task_id, principal.organization_id, visibility=visible_to(principal)
    )
    return TaskResponse.model_validate(task)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> TaskResponse:
    """Partially update a task. ``completed_at`` follows the status."""
    task = await service.get_or_404(
        task_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.update_task(
        task, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return TaskResponse.model_validate(updated)


@router.post("/{task_id}/status", response_model=TaskResponse)
async def change_task_status(
    task_id: uuid.UUID,
    payload: TaskStatusChange,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> TaskResponse:
    """Complete, reopen or cancel a task."""
    task = await service.get_or_404(
        task_id, principal.organization_id, visibility=visible_to(principal)
    )
    updated = await service.set_status(
        task, status=payload.status, actor_id=principal.user_id
    )
    return TaskResponse.model_validate(updated)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_task(
    task_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    task = await service.get_or_404(
        task_id, principal.organization_id, visibility=visible_to(principal)
    )
    await service.soft_delete(task, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
