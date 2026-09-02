"""Dashboard routes.

One endpoint, one permission. It carries the same authentication, membership
and RBAC dependencies as every other CRM route — a dashboard is not a
"summary view" exemption, it is CRM data in aggregate form.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.dashboard.reporting import ReportingRepository
from app.products.crm.dashboard.schemas import DashboardSummary
from app.products.crm.dashboard.service import DashboardService
from app.products.crm.shared.visibility import DashboardScope, RecordVisibility

router = APIRouter()

MODULE = "dashboard"


def get_service(session: DbSession) -> DashboardService:
    return DashboardService(session)


ServiceDep = Annotated[DashboardService, Depends(get_service)]


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> DashboardSummary:
    """KPIs, pipeline, tasks, meetings and recent activity for the active org.

    Scoped to ``principal.organization_id``, which the tenant middleware has
    already verified the caller is an active member of. An organization with no
    CRM records returns zeros and empty lists — a real empty state, not an
    error.

    Counts are narrowed to what this caller may open, so the KPI above a list
    and the list itself always agree. A rep sees their own pipeline; a manager
    or administrator, holding ``VIEW_ALL``, sees the organization's.
    """
    return await service.summary(
        principal.organization_id, scope=DashboardScope.for_principal(principal)
    )


__all__ = ["router"]


# --- Reporting ---------------------------------------------------------------
#
# A fixed set of questions a sales manager asks, answered in SQL, rather than a
# query builder (analysis §6.6 rules a BI system out of scope). Each is scoped
# and visibility-filtered like every other read, so a report can never total
# figures its reader may not open.


@router.get("/reports/sources", response_model=list[dict[str, Any]])
async def source_performance(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    session: DbSession,
) -> list[dict[str, Any]]:
    """Per-source funnel: leads, qualified, converted, opportunities, won value.

    Answerable because ``lead_sources`` is an entity rather than a picklist —
    the difference from Zoho that makes source attribution a query instead of a
    spreadsheet.
    """
    repository = ReportingRepository(session)
    rows = await repository.source_performance(
        principal.organization_id,
        lead_visibility=RecordVisibility.for_module(principal, "leads"),
        opportunity_visibility=RecordVisibility.for_module(principal, "opportunities"),
    )
    return [row.as_dict() for row in rows]


@router.get("/reports/win-loss", response_model=dict[str, Any])
async def win_loss(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    session: DbSession,
    days: Annotated[int | None, Query(ge=1, le=3650)] = None,
) -> dict[str, Any]:
    """Won and lost counts, values, win rate and the leading loss reasons."""
    since = (
        dt.datetime.now(dt.UTC) - dt.timedelta(days=days) if days is not None else None
    )
    return await ReportingRepository(session).win_loss(
        principal.organization_id,
        since=since,
        visibility=RecordVisibility.for_module(principal, "opportunities"),
    )


@router.get("/reports/ageing", response_model=list[dict[str, Any]])
async def pipeline_ageing(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    session: DbSession,
) -> list[dict[str, Any]]:
    """How long open deals have been sitting, in buckets."""
    return await ReportingRepository(session).pipeline_ageing(
        principal.organization_id,
        visibility=RecordVisibility.for_module(principal, "opportunities"),
    )


@router.get("/reports/funnel", response_model=list[dict[str, Any]])
async def stage_funnel(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    session: DbSession,
) -> list[dict[str, Any]]:
    """Deal count and value per stage — the shape of the pipeline."""
    return await ReportingRepository(session).stage_conversion(
        principal.organization_id,
        visibility=RecordVisibility.for_module(principal, "opportunities"),
    )
