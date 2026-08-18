"""Activity and meeting routes, including the per-record timeline."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.activities.models import Activity, ActivityStatus, ActivityType, Meeting
from app.products.crm.activities.schemas import (
    ActivityCreate,
    ActivityResponse,
    ActivityUpdate,
    MeetingDetail,
)
from app.products.crm.activities.service import ActivityService
from app.products.crm.common import CrmEntityType
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()

MODULE = "activities"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> ActivityService:
    return ActivityService(session)


ServiceDep = Annotated[ActivityService, Depends(get_service)]


def _to_response(activity: Activity, meeting: Meeting | None) -> ActivityResponse:
    """Compose the activity with its optional scheduling detail."""
    response = ActivityResponse.model_validate(activity)
    if meeting is not None:
        response.meeting = MeetingDetail.model_validate(meeting)
    return response


def _to_responses(
    activities: Sequence[Activity], meetings: dict[uuid.UUID, Meeting]
) -> list[ActivityResponse]:
    return [_to_response(activity, meetings.get(activity.id)) for activity in activities]


@router.get("", response_model=Page[ActivityResponse])
async def list_activities(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    params: PageParamsDep,
    search: Annotated[str | None, Query(max_length=255)] = None,
    activity_type: Annotated[ActivityType | None, Query(alias="type")] = None,
    activity_status: Annotated[ActivityStatus | None, Query(alias="status")] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
    related_entity_type: Annotated[CrmEntityType | None, Query()] = None,
    related_entity_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[ActivityResponse]:
    """List activities in the caller's organization."""
    filters = service.build_filters(
        search=search,
        activity_type=activity_type,
        status=activity_status,
        owner_id=owner_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    items, total = await service.list_activities(
        principal.organization_id, params=params, filters=filters
    )
    meetings = await service.load_meetings(items)
    return Page.build(_to_responses(items, meetings), total=total, params=params)


@router.get("/timeline", response_model=list[ActivityResponse])
async def entity_timeline(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    related_entity_type: Annotated[CrmEntityType, Query()],
    related_entity_id: Annotated[uuid.UUID, Query()],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ActivityResponse]:
    """Everything recorded against one record, most recent first.

    Powers the timeline panel on the account, contact, lead and opportunity
    detail pages.
    """
    items = await service.timeline(
        principal.organization_id,
        entity_type=related_entity_type,
        entity_id=related_entity_id,
        limit=limit,
    )
    meetings = await service.load_meetings(items)
    return _to_responses(items, meetings)


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_activity(
    payload: ActivityCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> ActivityResponse:
    """Log or schedule an activity. Meetings carry their scheduling detail."""
    activity = await service.create_activity(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return _to_response(activity, await service.get_meeting(activity))


@router.get("/{activity_id}", response_model=ActivityResponse)
async def get_activity(
    activity_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> ActivityResponse:
    """Fetch one activity. An id from another organization returns 404."""
    activity = await service.get_or_404(activity_id, principal.organization_id)
    return _to_response(activity, await service.get_meeting(activity))


@router.patch("/{activity_id}", response_model=ActivityResponse)
async def update_activity(
    activity_id: uuid.UUID,
    payload: ActivityUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> ActivityResponse:
    """Partially update an activity and any meeting detail sent with it."""
    activity = await service.get_or_404(activity_id, principal.organization_id)
    updated = await service.update_activity(
        activity, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return _to_response(updated, await service.get_meeting(updated))


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_activity(
    activity_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    activity = await service.get_or_404(activity_id, principal.organization_id)
    await service.archive_activity(activity, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
