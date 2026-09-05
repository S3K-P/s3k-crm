"""Dashboard routes.

Two things live here under one permission module:

``GET /crm/dashboard/summary`` — the fixed home screen, unchanged.
``/crm/dashboard/boards/...``  — dashboards a user builds from saved reports.

Every route carries the same authentication, membership and RBAC dependencies
as the rest of the CRM: a dashboard is not a "summary view" exemption, it is
CRM data in aggregate form.

``/boards`` rather than mounting the collection at the module root, because
``/summary`` is already a sibling and a bare ``GET /crm/dashboard`` that
returned a list of dashboards next to a ``/summary`` that returns one
organization's KPIs would read as an inconsistency every time somebody met it.

Rendering (``GET /boards/{id}/data``) takes ``PermissionedPrincipal`` rather
than a ``require_permission`` gate, for the reason the reports router
documents at length: each tile authorizes against the module *its* report
reads, which is not knowable when the route is declared. Reaching the
dashboard at all still requires ``dashboard.VIEW`` on the route that fetched
it, and a tile whose module the caller cannot read comes back marked
unavailable rather than fabricated.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import (
    PermissionedPrincipal,
    Principal,
    require_permission,
)
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.dashboard.library import DashboardLibraryService
from app.products.crm.dashboard.schemas import (
    DashboardComponentCreate,
    DashboardComponentData,
    DashboardComponentResponse,
    DashboardComponentUpdate,
    DashboardCreate,
    DashboardData,
    DashboardDetail,
    DashboardReorder,
    DashboardResponse,
    DashboardSummary,
    DashboardUpdate,
)
from app.products.crm.dashboard.service import DashboardService
from app.products.crm.shared.pagination import Page, PageParams, page_params
from app.products.crm.shared.visibility import DashboardScope

router = APIRouter()

MODULE = "dashboard"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> DashboardService:
    return DashboardService(session)


def get_library(session: DbSession) -> DashboardLibraryService:
    return DashboardLibraryService(session)


ServiceDep = Annotated[DashboardService, Depends(get_service)]
LibraryDep = Annotated[DashboardLibraryService, Depends(get_library)]


# ---------------------------------------------------------------------------
# The fixed summary
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Configurable dashboards
# ---------------------------------------------------------------------------


@router.get("/boards", response_model=Page[DashboardResponse])
async def list_dashboards(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    library: LibraryDep,
    params: PageParamsDep,
) -> Page[DashboardResponse]:
    """Dashboards the caller may open: shared ones, plus their own private."""
    items, total = await library.list_dashboards(
        principal.organization_id, viewer_id=principal.user_id, params=params
    )
    return Page.build(
        [DashboardResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@router.post("/boards", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    payload: DashboardCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    library: LibraryDep,
) -> DashboardResponse:
    """Create an empty dashboard. Tiles are added afterwards."""
    dashboard = await library.create_dashboard(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return DashboardResponse.model_validate(dashboard)


@router.get("/boards/{dashboard_id}", response_model=DashboardDetail)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    library: LibraryDep,
) -> DashboardDetail:
    """A dashboard and its layout, without running any of its reports.

    What an editor needs. To see the numbers, use ``/data``.
    """
    dashboard = await library.get_visible_or_404(
        dashboard_id, principal.organization_id, viewer_id=principal.user_id
    )
    components = await library.components_of(dashboard)
    return DashboardDetail(
        **DashboardResponse.model_validate(dashboard).model_dump(),
        components=[
            DashboardComponentResponse.model_validate(component) for component in components
        ],
    )


@router.patch("/boards/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    payload: DashboardUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    library: LibraryDep,
) -> DashboardResponse:
    """Rename, re-share, or make this the caller's default. Owners only."""
    dashboard = await library.get_visible_or_404(
        dashboard_id, principal.organization_id, viewer_id=principal.user_id
    )
    library.require_owner(dashboard, principal.user_id)
    updated = await library.update_dashboard(
        dashboard,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return DashboardResponse.model_validate(updated)


@router.delete("/boards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_dashboard(
    dashboard_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    library: LibraryDep,
) -> Response:
    """Archive a dashboard and its tiles. The saved reports are untouched."""
    dashboard = await library.get_visible_or_404(
        dashboard_id, principal.organization_id, viewer_id=principal.user_id
    )
    library.require_owner(dashboard, principal.user_id)
    await library.delete_dashboard(dashboard, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/boards/{dashboard_id}/data", response_model=DashboardData)
async def render_dashboard(
    dashboard_id: uuid.UUID,
    principal: PermissionedPrincipal,
    library: LibraryDep,
) -> DashboardData:
    """Run every tile as the caller.

    A shared dashboard therefore shows each viewer their own numbers, and a
    tile reading a module the viewer lacks comes back with ``unavailable``
    rather than failing the page or — far worse — showing somebody else's
    figures.
    """
    dashboard = await library.get_visible_or_404(
        dashboard_id, principal.organization_id, viewer_id=principal.user_id
    )
    rendered = await library.render(dashboard, principal)
    return DashboardData(
        id=dashboard.id,
        name=dashboard.name,
        description=dashboard.description,
        generated_at=dt.datetime.now(dt.UTC),
        components=[DashboardComponentData.model_validate(entry) for entry in rendered],
    )


# ---------------------------------------------------------------------------
# Tiles
# ---------------------------------------------------------------------------


@router.post(
    "/boards/{dashboard_id}/components",
    response_model=DashboardComponentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_component(
    dashboard_id: uuid.UUID,
    payload: DashboardComponentCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    library: LibraryDep,
) -> DashboardComponentResponse:
    """Put a saved report on this dashboard.

    The report must be one the caller can open — their own, or shared. A
    report id they cannot see is a 404, the same answer they would get asking
    for it directly.
    """
    dashboard = await library.get_visible_or_404(
        dashboard_id, principal.organization_id, viewer_id=principal.user_id
    )
    library.require_owner(dashboard, principal.user_id)
    values = payload.model_dump(exclude_unset=True)
    if values.get("sort_order") is None:
        values.pop("sort_order", None)
    component = await library.add_component(dashboard, actor_id=principal.user_id, values=values)
    return DashboardComponentResponse.model_validate(component)


@router.patch(
    "/boards/{dashboard_id}/components/{component_id}",
    response_model=DashboardComponentResponse,
)
async def update_component(
    dashboard_id: uuid.UUID,
    component_id: uuid.UUID,
    payload: DashboardComponentUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    library: LibraryDep,
) -> DashboardComponentResponse:
    """Retitle, resize or repoint one tile."""
    dashboard = await library.get_visible_or_404(
        dashboard_id, principal.organization_id, viewer_id=principal.user_id
    )
    library.require_owner(dashboard, principal.user_id)
    component = await library.get_component_or_404(dashboard, component_id)
    updated = await library.update_component(
        dashboard,
        component,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return DashboardComponentResponse.model_validate(updated)


@router.delete(
    "/boards/{dashboard_id}/components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_component(
    dashboard_id: uuid.UUID,
    component_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    library: LibraryDep,
) -> Response:
    """Take a tile off. The saved report behind it is untouched."""
    dashboard = await library.get_visible_or_404(
        dashboard_id, principal.organization_id, viewer_id=principal.user_id
    )
    library.require_owner(dashboard, principal.user_id)
    component = await library.get_component_or_404(dashboard, component_id)
    await library.remove_component(dashboard, component, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/boards/{dashboard_id}/layout", response_model=list[DashboardComponentResponse])
async def reorder_components(
    dashboard_id: uuid.UUID,
    payload: DashboardReorder,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    library: LibraryDep,
) -> list[DashboardComponentResponse]:
    """Apply a whole new tile order.

    PUT rather than PATCH: the body is the complete order, and sending it
    twice leaves the dashboard exactly as sending it once did.
    """
    dashboard = await library.get_visible_or_404(
        dashboard_id, principal.organization_id, viewer_id=principal.user_id
    )
    library.require_owner(dashboard, principal.user_id)
    components = await library.reorder(dashboard, actor_id=principal.user_id, order=payload.order)
    return [DashboardComponentResponse.model_validate(component) for component in components]


__all__ = ["router"]
