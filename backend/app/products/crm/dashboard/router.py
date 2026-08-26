"""Dashboard routes.

One endpoint, one permission. It carries the same authentication, membership
and RBAC dependencies as every other CRM route — a dashboard is not a
"summary view" exemption, it is CRM data in aggregate form.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.dashboard.schemas import DashboardSummary
from app.products.crm.dashboard.service import DashboardService
from app.products.crm.shared.visibility import DashboardScope

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
