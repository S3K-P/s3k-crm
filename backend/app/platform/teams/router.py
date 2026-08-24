"""HTTP routes for the teams module.

Mounted at ``/api/v1/teams`` and ``/api/v1/departments`` by the composition
root. Every route is gated on the ``teams`` permission and scoped to the
caller's organization.

There is no "my teams" route. What a user's team membership *does* is widen
record-level visibility, and that is applied inside the CRM's own queries — a
separate endpoint would be a second place for the rule to live and a second
place for it to drift.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.core.pagination import Page, PageParams, page_params
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.teams.policies import CREATE, DELETE, EDIT, MODULE, VIEW
from app.platform.teams.repository import TeamRepository
from app.platform.teams.schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    TeamCreate,
    TeamMemberAdd,
    TeamMemberResponse,
    TeamResponse,
    TeamUpdate,
)
from app.platform.teams.service import TeamService

router = APIRouter()
department_router = APIRouter()

PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> TeamService:
    return TeamService(TeamRepository(session))


ServiceDep = Annotated[TeamService, Depends(get_service)]

#: Declared once so no route can be added with a weaker gate by accident.
Reader = Annotated[Principal, Depends(require_permission(MODULE, VIEW))]
Creator = Annotated[Principal, Depends(require_permission(MODULE, CREATE))]
Editor = Annotated[Principal, Depends(require_permission(MODULE, EDIT))]
Remover = Annotated[Principal, Depends(require_permission(MODULE, DELETE))]


def _team_response(team: object, member_count: int = 0) -> TeamResponse:
    response = TeamResponse.model_validate(team)
    return response.model_copy(update={"member_count": member_count})


# --- Departments ------------------------------------------------------------


@department_router.get("", response_model=Page[DepartmentResponse])
async def list_departments(
    principal: Reader, service: ServiceDep, params: PageParamsDep
) -> Page[DepartmentResponse]:
    items, total = await service.list_departments(principal, params=params)
    return Page.build(
        [DepartmentResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@department_router.post(
    "", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED
)
async def create_department(
    payload: DepartmentCreate, principal: Creator, service: ServiceDep
) -> DepartmentResponse:
    department = await service.create_department(principal, name=payload.name)
    return DepartmentResponse.model_validate(department)


@department_router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: uuid.UUID, principal: Reader, service: ServiceDep
) -> DepartmentResponse:
    return DepartmentResponse.model_validate(
        await service.get_department(department_id, principal)
    )


@department_router.patch("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    principal: Editor,
    service: ServiceDep,
) -> DepartmentResponse:
    department = await service.update_department(
        department_id, principal, name=payload.name
    )
    return DepartmentResponse.model_validate(department)


@department_router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    department_id: uuid.UUID, principal: Remover, service: ServiceDep
) -> Response:
    await service.delete_department(department_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Teams ------------------------------------------------------------------


@router.get("", response_model=Page[TeamResponse])
async def list_teams(
    principal: Reader,
    service: ServiceDep,
    params: PageParamsDep,
    department_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[TeamResponse]:
    teams, total, counts = await service.list_teams(
        principal, params=params, department_id=department_id
    )
    return Page.build(
        [_team_response(team, counts.get(team.id, 0)) for team in teams],
        total=total,
        params=params,
    )


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate, principal: Creator, service: ServiceDep
) -> TeamResponse:
    team = await service.create_team(
        principal, name=payload.name, department_id=payload.department_id
    )
    return _team_response(team)


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: uuid.UUID, principal: Reader, service: ServiceDep
) -> TeamResponse:
    team, member_count = await service.get_team_with_count(team_id, principal)
    return _team_response(team, member_count)


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID, payload: TeamUpdate, principal: Editor, service: ServiceDep
) -> TeamResponse:
    # ``department_id`` is tri-state: absent means "leave it", explicit null
    # means "detach". Pydantic records which fields the client actually sent.
    team = await service.update_team(
        team_id,
        principal,
        name=payload.name,
        department_id=payload.department_id,
        change_department="department_id" in payload.model_fields_set,
    )
    return _team_response(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: uuid.UUID, principal: Remover, service: ServiceDep
) -> Response:
    await service.delete_team(team_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Membership -------------------------------------------------------------


@router.get("/{team_id}/members", response_model=Page[TeamMemberResponse])
async def list_team_members(
    team_id: uuid.UUID, principal: Reader, service: ServiceDep, params: PageParamsDep
) -> Page[TeamMemberResponse]:
    items, total = await service.list_members(team_id, principal, params=params)
    return Page.build(
        [TeamMemberResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_team_member(
    team_id: uuid.UUID,
    payload: TeamMemberAdd,
    principal: Editor,
    service: ServiceDep,
) -> TeamMemberResponse:
    """Put a user on a team.

    ``EDIT`` rather than ``CREATE``: adding a member modifies the team, and an
    administrator who may not create teams should still be able to staff one.
    """
    membership = await service.add_member(team_id, principal, user_id=payload.user_id)
    return TeamMemberResponse.model_validate(membership)


@router.delete(
    "/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_team_member(
    team_id: uuid.UUID, user_id: uuid.UUID, principal: Editor, service: ServiceDep
) -> Response:
    await service.remove_member(team_id, principal, user_id=user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["department_router", "router"]
