"""HTTP routes for the audit module — read-only by construction.

``GET /api/v1/audit-logs`` and its two companions are the *entire* surface.
There is no POST, PATCH or DELETE here and adding one would be a mistake: the
trail is appended by the services performing the audited actions, and the table
rejects UPDATE and DELETE at the database level regardless of what a route
tried to do (see ``app.platform.audit.policies``).

Every endpoint below is gated on ``audit.VIEW`` and scoped to the principal's
organization. The organization is never a parameter — it comes from the
verified tenant context, so there is no id in the URL or the query string for a
caller to tamper with.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.core.pagination import Page, PageParams, page_params
from app.platform.audit.models import AuditStatus
from app.platform.audit.policies import MODULE, VIEW
from app.platform.audit.schemas import AuditFilterOptionsResponse, AuditLogResponse
from app.platform.audit.service import AuditService, audit_for_session
from app.platform.auth.dependencies import Principal, require_permission

router = APIRouter()

PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> AuditService:
    return audit_for_session(session)


ServiceDep = Annotated[AuditService, Depends(get_service)]

#: The principal every route here requires. Declared once so no endpoint can be
#: added with a weaker gate by accident.
AuditReader = Annotated[Principal, Depends(require_permission(MODULE, VIEW))]


@router.get("", response_model=Page[AuditLogResponse])
async def list_audit_logs(
    principal: AuditReader,
    service: ServiceDep,
    params: PageParamsDep,
    occurred_from: Annotated[
        dt.datetime | None,
        Query(description="Only records at or after this instant (ISO 8601)."),
    ] = None,
    occurred_to: Annotated[
        dt.datetime | None,
        Query(description="Only records at or before this instant (ISO 8601)."),
    ] = None,
    actor_id: Annotated[uuid.UUID | None, Query(description="Who acted.")] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    module: Annotated[str | None, Query(max_length=64)] = None,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: Annotated[uuid.UUID | None, Query()] = None,
    entry_status: Annotated[AuditStatus | None, Query(alias="status")] = None,
) -> Page[AuditLogResponse]:
    """The caller's organization's audit trail, newest first.

    Sorting accepts ``created_at``, ``action``, ``module``, ``entity_type`` and
    ``status``; anything else falls back to ``created_at``. The allow-list is
    in the repository — an audit table is the largest in the schema and an
    unindexed sort over it is a denial of service.

    Filters are applied in SQL on top of the mandatory organization predicate,
    so the page and its total count always agree.
    """
    filters = service.build_filters(
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        actor_id=actor_id,
        action=action,
        module=module,
        entity_type=entity_type,
        entity_id=entity_id,
        status=entry_status,
    )
    views, total = await service.list_entries(
        principal.organization_id, params=params, filters=filters
    )
    return Page.build(
        [AuditLogResponse.from_view(view) for view in views], total=total, params=params
    )


@router.get("/filters", response_model=AuditFilterOptionsResponse)
async def get_filter_options(
    principal: AuditReader,
    service: ServiceDep,
) -> AuditFilterOptionsResponse:
    """Values worth offering in the filter controls for this organization."""
    actions, entity_types, recording_since = await service.filter_options(
        principal.organization_id
    )
    return AuditFilterOptionsResponse(
        actions=list(actions),
        entity_types=list(entity_types),
        statuses=[status.value for status in AuditStatus],
        recording_since=recording_since,
    )


@router.get("/{entry_id}", response_model=AuditLogResponse)
async def get_audit_log(
    entry_id: uuid.UUID,
    principal: AuditReader,
    service: ServiceDep,
) -> AuditLogResponse:
    """One record. An id from another organization returns 404, not 403."""
    view = await service.get_entry_view(entry_id, principal.organization_id)
    return AuditLogResponse.from_view(view)


__all__ = ["router"]
