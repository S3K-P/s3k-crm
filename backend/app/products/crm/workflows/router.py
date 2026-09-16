"""Workflow routes, mounted at ``/crm/workflows``.

Gated on the ``workflows`` permission module — see ``.policies`` for the
``VIEW``-vs-everything-else split, the same one blueprints uses.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.shared.pagination import Page, PageParams, page_params
from app.products.crm.workflows.schemas import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowRunResponse,
    WorkflowUpdate,
)
from app.products.crm.workflows.service import MODULE, WorkflowRuleService, list_workflow_runs

router = APIRouter()


def get_service(session: DbSession) -> WorkflowRuleService:
    return WorkflowRuleService(session)


ServiceDep = Annotated[WorkflowRuleService, Depends(get_service)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]


@router.get("", response_model=Page[WorkflowResponse])
async def list_workflows(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
) -> Page[WorkflowResponse]:
    """Every workflow in the organization."""
    items, total = await service.list_workflows(principal.organization_id, params=params)
    return Page.build(
        [WorkflowResponse.model_validate(item) for item in items], total=total, params=params
    )


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> WorkflowResponse:
    """Define a workflow. Created inactive; activate it once it is configured."""
    rule = await service.create_workflow(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return WorkflowResponse.model_validate(rule)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> WorkflowResponse:
    rule = await service.get_or_404(workflow_id, principal.organization_id)
    return WorkflowResponse.model_validate(rule)


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> WorkflowResponse:
    """Edit a workflow, including activating (``is_active: true``) or
    disabling it (``is_active: false``)."""
    rule = await service.get_or_404(workflow_id, principal.organization_id)
    updated = await service.update_workflow(
        rule, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return WorkflowResponse.model_validate(updated)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_workflow(
    workflow_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    rule = await service.get_or_404(workflow_id, principal.organization_id)
    await service.soft_delete(rule, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workflow_id}/duplicate", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED
)
async def duplicate_workflow(
    workflow_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> WorkflowResponse:
    """A deactivated copy, named uniquely."""
    rule = await service.get_or_404(workflow_id, principal.organization_id)
    copy = await service.duplicate_workflow(rule, actor_id=principal.user_id)
    return WorkflowResponse.model_validate(copy)


@router.get("/{workflow_id}/runs", response_model=Page[WorkflowRunResponse])
async def get_workflow_runs(
    workflow_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    session: DbSession,
    params: PageParamsDep,
) -> Page[WorkflowRunResponse]:
    """Execution history for one workflow — most recent first."""
    await service.get_or_404(workflow_id, principal.organization_id)  # 404s a foreign/unknown id
    items, total = await list_workflow_runs(
        session, principal.organization_id, params=params, workflow_rule_id=workflow_id
    )
    return Page.build(
        [WorkflowRunResponse.model_validate(item) for item in items], total=total, params=params
    )


@router.get("/runs/all", response_model=Page[WorkflowRunResponse])
async def get_all_workflow_runs(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    session: DbSession,
    params: PageParamsDep,
) -> Page[WorkflowRunResponse]:
    """Execution history across every workflow — the admin activity feed.

    Nested two segments deep (``/runs/all``, not ``/runs``) so its path can
    never collide with ``/{workflow_id}`` — a bare ``/runs`` would otherwise
    be indistinguishable from a (malformed) workflow id at the router level.
    """
    items, total = await list_workflow_runs(session, principal.organization_id, params=params)
    return Page.build(
        [WorkflowRunResponse.model_validate(item) for item in items], total=total, params=params
    )


__all__ = ["router"]
