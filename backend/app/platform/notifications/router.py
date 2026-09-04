"""HTTP routes for the notifications module.

Mounted at ``/api/v1/notifications`` by the composition root. Every route
requires only authentication plus an established tenant context
(``CurrentPrincipal``) — there is no ``require_permission`` gate, because a
notification is scoped to its recipient rather than to a role's reach. See
``policies.py`` for why that is a deliberate absence and not an oversight.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.core.pagination import Page, PageParams, page_params
from app.platform.auth.dependencies import CurrentPrincipal
from app.platform.notifications.repository import NotificationRepository
from app.platform.notifications.schemas import NotificationResponse, UnreadCountResponse
from app.platform.notifications.service import NotificationService

router = APIRouter()

PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> NotificationService:
    return NotificationService(NotificationRepository(session))


ServiceDep = Annotated[NotificationService, Depends(get_service)]


@router.get("", response_model=Page[NotificationResponse])
async def list_notifications(
    principal: CurrentPrincipal,
    service: ServiceDep,
    params: PageParamsDep,
    unread_only: Annotated[bool, Query()] = False,
) -> Page[NotificationResponse]:
    """The caller's own notifications, newest first."""
    items, total = await service.list_for_recipient(
        principal, params=params, unread_only=unread_only
    )
    return Page.build(
        [NotificationResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(principal: CurrentPrincipal, service: ServiceDep) -> UnreadCountResponse:
    """The number badging the bell — cheap on its own so the topbar can poll it."""
    return UnreadCountResponse(unread_count=await service.unread_count(principal))


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: uuid.UUID, principal: CurrentPrincipal, service: ServiceDep
) -> NotificationResponse:
    """Mark one of the caller's own notifications read. Idempotent."""
    notification = await service.mark_read(notification_id, principal)
    return NotificationResponse.model_validate(notification)


@router.post("/read-all", response_model=UnreadCountResponse)
async def mark_all_notifications_read(
    principal: CurrentPrincipal, service: ServiceDep
) -> UnreadCountResponse:
    """Mark every one of the caller's unread notifications read.

    Responds with the count that changed, reusing ``UnreadCountResponse``:
    the number of notifications just marked read is also the caller's exact
    unread count immediately beforehand.
    """
    marked = await service.mark_all_read(principal)
    return UnreadCountResponse(unread_count=marked)


__all__ = ["router"]
