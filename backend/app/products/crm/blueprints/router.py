"""Blueprint routes, mounted at ``/crm/blueprints``.

Gated on the ``blueprints`` permission module, which only Admin holds by
default: a blueprint decides what everybody else in the organization is allowed
to do with a record, so configuring one is administration in the strongest
sense in the product.

``VIEW`` is granted more widely, because a rep needs to know why a move was
refused and what would unblock it. It grants sight of the tenant's own process
and of no record at all.

There is no endpoint here for *applying* a blueprint. It is applied inside the
lead and opportunity services, on the state-change path those modules already
own — a second way to move a record would be a second place the rules lived.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.blueprints.models import Blueprint, BlueprintField
from app.products.crm.blueprints.schemas import (
    BlueprintCreate,
    BlueprintResponse,
    BlueprintStateOption,
    BlueprintStatesResponse,
    BlueprintTransitionCreate,
    BlueprintTransitionResponse,
    BlueprintTransitionUpdate,
    BlueprintUpdate,
)
from app.products.crm.blueprints.service import MODULE, BlueprintService

router = APIRouter()


def get_service(session: DbSession) -> BlueprintService:
    return BlueprintService(session)


ServiceDep = Annotated[BlueprintService, Depends(get_service)]


@router.get("", response_model=list[BlueprintResponse])
async def list_blueprints(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> list[BlueprintResponse]:
    """Every blueprint in the organization, with its move count.

    Unpaginated: an organization has one process per governed field and two
    governed fields, so the whole set is small by construction and every caller
    wants all of it.
    """
    blueprints = await service.list_blueprints(principal.organization_id)
    counts = await service.transition_counts(principal.organization_id)
    payload = []
    for blueprint in blueprints:
        response = BlueprintResponse.model_validate(blueprint)
        response.transition_count = counts.get(blueprint.id, 0)
        payload.append(response)
    return payload


@router.get("/states", response_model=BlueprintStatesResponse)
async def list_states(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    field: Annotated[BlueprintField, Query()],
) -> BlueprintStatesResponse:
    """The states a governed field can hold.

    Declared before ``/{blueprint_id}``: FastAPI matches in registration order
    and the id route would otherwise claim ``/states`` and reject it as a
    malformed UUID.
    """
    states = await service.available_states(principal.organization_id, field)
    return BlueprintStatesResponse(
        field=field, states=[BlueprintStateOption(**entry) for entry in states]
    )


@router.post("", response_model=BlueprintResponse, status_code=status.HTTP_201_CREATED)
async def create_blueprint(
    payload: BlueprintCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> BlueprintResponse:
    """Define a blueprint. Created inactive; activate it once it has moves."""
    blueprint = await service.create_blueprint(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return BlueprintResponse.model_validate(blueprint)


@router.get("/{blueprint_id}", response_model=BlueprintResponse)
async def get_blueprint(
    blueprint_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> BlueprintResponse:
    """One blueprint with every move it describes."""
    blueprint = await service.get_or_404(blueprint_id, principal.organization_id)
    return await _detail(blueprint, service)


@router.patch("/{blueprint_id}", response_model=BlueprintResponse)
async def update_blueprint(
    blueprint_id: uuid.UUID,
    payload: BlueprintUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> BlueprintResponse:
    """Rename, describe, activate or deactivate.

    Activation validates the whole process — that every move names a state that
    still exists, that there is at least one move, and that no other blueprint
    already governs the field — because it is the last moment before the
    configuration starts refusing people's work.
    """
    blueprint = await service.get_or_404(blueprint_id, principal.organization_id)
    updated = await service.update_blueprint(
        blueprint, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return await _detail(updated, service)


@router.delete("/{blueprint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_blueprint(
    blueprint_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    """Retire a blueprint. It stops constraining records immediately."""
    blueprint = await service.get_or_404(blueprint_id, principal.organization_id)
    await service.archive_blueprint(blueprint, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{blueprint_id}/transitions",
    response_model=BlueprintTransitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_transition(
    blueprint_id: uuid.UUID,
    payload: BlueprintTransitionCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> BlueprintTransitionResponse:
    """Describe a move.

    ``EDIT`` rather than ``CREATE``: the thing being changed is the blueprint,
    and a role that may maintain an existing process but not define new ones is
    a coherent one to hold.

    Refused if the move is one the built-in state machine would not allow — a
    blueprint narrows what is possible and never widens it, so a rule for an
    impossible move could never fire and its author would reasonably believe
    they had enabled something.
    """
    blueprint = await service.get_or_404(blueprint_id, principal.organization_id)
    transition = await service.add_transition(
        blueprint, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return BlueprintTransitionResponse.model_validate(transition)


@router.patch(
    "/{blueprint_id}/transitions/{transition_id}",
    response_model=BlueprintTransitionResponse,
)
async def update_transition(
    blueprint_id: uuid.UUID,
    transition_id: uuid.UUID,
    payload: BlueprintTransitionUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> BlueprintTransitionResponse:
    blueprint = await service.get_or_404(blueprint_id, principal.organization_id)
    transition = await service.get_transition_or_404(blueprint, transition_id)
    updated = await service.update_transition(
        blueprint,
        transition,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return BlueprintTransitionResponse.model_validate(updated)


@router.delete(
    "/{blueprint_id}/transitions/{transition_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_transition(
    blueprint_id: uuid.UUID,
    transition_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> Response:
    """Remove a move.

    Removing the last rule for a destination stops the blueprint constraining
    that state at all, which is the intended way to relax a process.
    """
    blueprint = await service.get_or_404(blueprint_id, principal.organization_id)
    transition = await service.get_transition_or_404(blueprint, transition_id)
    await service.remove_transition(blueprint, transition, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _detail(blueprint: Blueprint, service: BlueprintService) -> BlueprintResponse:
    transitions = await service.transitions(blueprint.organization_id, blueprint.id)
    response = BlueprintResponse.model_validate(blueprint)
    response.transitions = [
        BlueprintTransitionResponse.model_validate(transition) for transition in transitions
    ]
    response.transition_count = len(transitions)
    return response


__all__ = ["router"]
