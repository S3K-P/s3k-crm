"""Configurable dashboards: the arrangement, and rendering it.

Named ``DashboardLibraryService`` rather than ``DashboardService`` because
that name is taken, in this same package, by the fixed ``/summary`` screen.
The two are different products of the same permission module — see
``models.py`` for why they share it.

**Rendering is a loop of ordinary report runs, and deliberately so.** Each tile
delegates to :class:`~app.products.crm.reports.library.SavedReportService`,
which delegates to the same ``ReportService.run`` the ad-hoc route uses. There
is no dashboard-specific query path, which means there is no second place for
the record-visibility rule to be got wrong: a tile shows the viewer's numbers
because it is running the viewer's report.

The loop is sequential. One :class:`AsyncSession` cannot have two statements in
flight, so gathering the tiles concurrently would need a session each and a
connection each — a real cost, paid on every dashboard load, to overlap
queries that are individually fast. If a dashboard ever grows slow the fix is
fewer tiles or a faster report, not more connections.

**A tile the viewer cannot run is reported, not fatal.** Returning 403 for the
whole dashboard because one tile reads a module the viewer lacks would make a
shared dashboard useless to exactly the people it was shared with. The tile
comes back marked unavailable, which discloses nothing new: the viewer can
already see that the tile exists.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.platform.audit.service import Action as AuditAction
from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import PermissionDeniedError
from app.products.crm.dashboard.models import (
    DASHBOARD_GRID_COLUMNS,
    Dashboard,
    DashboardComponent,
)
from app.products.crm.reports.library import (
    NotOwnerError,
    SavedReportService,
    UnknownReportError,
    drop_explicit_nulls,
)
from app.products.crm.reports.models import SavedReport, ShareScope
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService

#: Both tables live under the existing ``dashboard`` permission module.
DASHBOARD_MODULE = "dashboard"

#: Why a tile could not be drawn. Deliberately coarse — the viewer is told the
#: tile is unavailable and roughly why, never which records exist behind it.
UNAVAILABLE_PERMISSION = "permission"
UNAVAILABLE_REPORT_GONE = "report_unavailable"

#: A dashboard cannot grow without bound. The ceiling is a guard on the
#: rendering loop above rather than a design opinion: twenty-four tiles is
#: already twice what fits on a screen, and each one is a full report run.
MAX_COMPONENTS_PER_DASHBOARD = 24


class TooManyComponentsError(ConflictError):
    """The dashboard already holds as many tiles as it may."""

    def __init__(self) -> None:
        super().__init__(f"A dashboard can hold at most {MAX_COMPONENTS_PER_DASHBOARD} tiles.")


class DashboardLibraryService(TenantScopedService[Dashboard]):
    """Dashboards a user builds, and the tiles on them."""

    entity_name = "Dashboard"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Dashboard), Dashboard)
        self._session = session
        self._components = TenantScopedRepository(session, DashboardComponent)
        self._saved = SavedReportService(session)

    @property
    def audit_module(self) -> str:
        """``dashboard``, not the ``dashboards`` table name.

        The derivation in the base class assumes table and permission module
        share a name, which holds for every entity module but not here.
        """
        return DASHBOARD_MODULE

    # --- Reads -------------------------------------------------------------

    @staticmethod
    def visibility_filter(viewer_id: uuid.UUID | None) -> ColumnElement[bool]:
        """Shared dashboards, plus the viewer's own private ones."""
        shared = Dashboard.visibility == ShareScope.SHARED
        if viewer_id is None:
            return shared
        return or_(
            shared,
            and_(
                Dashboard.visibility == ShareScope.PRIVATE,
                Dashboard.owner_id == viewer_id,
            ),
        )

    async def list_dashboards(
        self, organization_id: uuid.UUID, *, viewer_id: uuid.UUID | None, params: PageParams
    ) -> tuple[Sequence[Dashboard], int]:
        return await self.list(
            organization_id, params=params, filters=[self.visibility_filter(viewer_id)]
        )

    async def get_visible_or_404(
        self,
        dashboard_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        viewer_id: uuid.UUID | None,
    ) -> Dashboard:
        dashboard = await self.get_or_404(dashboard_id, organization_id)
        if dashboard.visibility is ShareScope.PRIVATE and dashboard.owner_id != viewer_id:
            raise NotFoundError(f"{self.entity_name} not found.")
        return dashboard

    async def components_of(self, dashboard: Dashboard) -> list[DashboardComponent]:
        """Tiles in display order.

        ``sort_order`` then ``created_at``: two tiles can legitimately share a
        sort order (a client that reorders by rewriting only what moved), and
        without the tiebreak their order would vary between requests for no
        reason the user could see.
        """
        result = await self._session.execute(
            select(DashboardComponent)
            .where(
                DashboardComponent.organization_id == dashboard.organization_id,
                DashboardComponent.dashboard_id == dashboard.id,
                DashboardComponent.deleted_at.is_(None),
            )
            .order_by(DashboardComponent.sort_order.asc(), DashboardComponent.created_at.asc())
        )
        return list(result.scalars().all())

    async def saved_reports_for(
        self, components: Sequence[DashboardComponent], organization_id: uuid.UUID
    ) -> dict[uuid.UUID, SavedReport]:
        """The saved reports behind a set of tiles, in one query.

        Includes reports the viewer could not open directly. That is correct
        and worth being explicit about: putting a report on a shared dashboard
        *is* the act of sharing it, and the tile still runs as the viewer, so
        no number crosses a boundary. What the viewer gains is the report's
        name, which the tile was going to show them anyway.
        """
        ids = {component.saved_report_id for component in components}
        if not ids:
            return {}
        result = await self._session.execute(
            select(SavedReport).where(
                SavedReport.organization_id == organization_id,
                SavedReport.id.in_(ids),
                SavedReport.deleted_at.is_(None),
            )
        )
        return {report.id: report for report in result.scalars().all()}

    # --- Rendering ---------------------------------------------------------

    async def render(
        self,
        dashboard: Dashboard,
        principal: Principal,
        *,
        today: dt.date | None = None,
    ) -> list[dict[str, Any]]:
        """Run every tile as ``principal``, in display order.

        Returns one entry per tile carrying either a ``result`` or an
        ``unavailable`` reason — never both, never neither.
        """
        components = await self.components_of(dashboard)
        reports = await self.saved_reports_for(components, dashboard.organization_id)

        rendered: list[dict[str, Any]] = []
        for component in components:
            saved = reports.get(component.saved_report_id)
            entry: dict[str, Any] = {
                "id": component.id,
                "saved_report_id": component.saved_report_id,
                "title": component.title or (saved.name if saved else "Unavailable"),
                "display": component.display,
                "width": component.width,
                "sort_order": component.sort_order,
                "result": None,
                "unavailable": None,
            }
            if saved is None:
                # The report was archived directly in the database — the API
                # refuses to delete one that is still on a dashboard.
                entry["unavailable"] = UNAVAILABLE_REPORT_GONE
                rendered.append(entry)
                continue
            try:
                entry["result"] = await self._saved.run_saved(saved, principal, today=today)
            except PermissionDeniedError:
                entry["unavailable"] = UNAVAILABLE_PERMISSION
            except (NotFoundError, UnknownReportError):
                entry["unavailable"] = UNAVAILABLE_REPORT_GONE
            rendered.append(entry)
        return rendered

    # --- Commands ----------------------------------------------------------

    async def create_dashboard(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> Dashboard:
        payload = dict(values)
        await self._require_free_name(organization_id, payload.get("name"))
        payload["owner_id"] = actor_id
        make_default = bool(payload.get("is_default"))
        dashboard = await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )
        if make_default:
            await self._clear_other_defaults(dashboard, actor_id)
        return dashboard

    async def update_dashboard(
        self,
        dashboard: Dashboard,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> Dashboard:
        payload = drop_explicit_nulls(
            dict(values), {"name", "visibility", "is_default"}
        )
        name = payload.get("name")
        if name is not None and name != dashboard.name:
            await self._require_free_name(dashboard.organization_id, name)
        payload.pop("owner_id", None)
        updated = await self.update(dashboard, actor_id=actor_id, values=payload)
        if payload.get("is_default"):
            await self._clear_other_defaults(updated, actor_id)
        return updated

    async def delete_dashboard(
        self, dashboard: Dashboard, *, actor_id: uuid.UUID | None
    ) -> Dashboard:
        """Archive a dashboard and the tiles on it.

        Tiles are archived here rather than left behind, because a tile is
        part of its dashboard rather than a thing in its own right — the same
        judgement the ``ON DELETE CASCADE`` on the foreign key makes for a hard
        delete. The saved reports the tiles pointed at are untouched: those
        belong to the library, not to this dashboard.
        """
        for component in await self.components_of(dashboard):
            await self._components.soft_delete(component)
        return await self.soft_delete(dashboard, actor_id=actor_id)

    async def add_component(
        self,
        dashboard: Dashboard,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> DashboardComponent:
        """Put a saved report on a dashboard.

        The report must be one the caller can open. Without that check a
        member could mount a colleague's private report on a shared dashboard
        and read its name — and, worse, hand every other viewer a tile whose
        existence its owner never agreed to.
        """
        payload = dict(values)
        saved_report_id = payload.get("saved_report_id")
        if not isinstance(saved_report_id, uuid.UUID):
            raise NotFoundError("Saved report not found.")
        await self._saved.get_visible_or_404(
            saved_report_id, dashboard.organization_id, viewer_id=actor_id
        )

        existing = await self.components_of(dashboard)
        if len(existing) >= MAX_COMPONENTS_PER_DASHBOARD:
            raise TooManyComponentsError

        payload.setdefault(
            "sort_order",
            max((component.sort_order for component in existing), default=-1) + 1,
        )
        payload["dashboard_id"] = dashboard.id

        component = DashboardComponent(
            **payload,
            organization_id=dashboard.organization_id,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        added = await self._components.add(component)
        await self._record_component_change(AuditAction.CREATED, dashboard, added, actor_id)
        return added

    async def get_component_or_404(
        self, dashboard: Dashboard, component_id: uuid.UUID
    ) -> DashboardComponent:
        """A tile of *this* dashboard.

        Scoped to the parent as well as the organization, so a valid component
        id from another dashboard cannot be edited through this one's URL.
        """
        component = await self._components.get(component_id, dashboard.organization_id)
        if component is None or component.dashboard_id != dashboard.id:
            raise NotFoundError("Dashboard tile not found.")
        return component

    async def update_component(
        self,
        dashboard: Dashboard,
        component: DashboardComponent,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> DashboardComponent:
        payload = drop_explicit_nulls(
            dict(values), {"saved_report_id", "display", "width", "sort_order"}
        )
        payload.pop("dashboard_id", None)
        if "saved_report_id" in payload:
            saved_report_id = payload["saved_report_id"]
            if not isinstance(saved_report_id, uuid.UUID):
                raise NotFoundError("Saved report not found.")
            await self._saved.get_visible_or_404(
                saved_report_id, dashboard.organization_id, viewer_id=actor_id
            )
        for field, value in payload.items():
            setattr(component, field, value)
        component.updated_by_id = actor_id
        await self._components.flush()
        await self._record_component_change(AuditAction.UPDATED, dashboard, component, actor_id)
        return component

    async def remove_component(
        self,
        dashboard: Dashboard,
        component: DashboardComponent,
        *,
        actor_id: uuid.UUID | None,
    ) -> None:
        component.updated_by_id = actor_id
        await self._components.soft_delete(component)
        await self._record_component_change(AuditAction.DELETED, dashboard, component, actor_id)

    async def reorder(
        self,
        dashboard: Dashboard,
        *,
        actor_id: uuid.UUID | None,
        order: Sequence[uuid.UUID],
    ) -> list[DashboardComponent]:
        """Apply a whole new tile order in one call.

        A drag-and-drop that moves one tile changes the position of every tile
        after it, so a PATCH per tile would be both chatty and non-atomic —
        a failure halfway would leave a layout nobody chose. Ids not belonging
        to this dashboard are a 404 rather than being skipped: a client sending
        one has a bug, and silently reordering the rest would hide it.
        """
        components = {component.id: component for component in await self.components_of(dashboard)}
        unknown = [component_id for component_id in order if component_id not in components]
        if unknown:
            raise NotFoundError("Dashboard tile not found.")

        for position, component_id in enumerate(order):
            components[component_id].sort_order = position
            components[component_id].updated_by_id = actor_id
        await self._components.flush()

        await self.audit.record(
            organization_id=dashboard.organization_id,
            action=AuditAction.UPDATED,
            module=DASHBOARD_MODULE,
            actor_id=actor_id,
            entity_type="DASHBOARD",
            entity_id=dashboard.id,
            entity_label=dashboard.name,
            details={"reordered": [str(component_id) for component_id in order]},
        )
        return await self.components_of(dashboard)

    @staticmethod
    def require_owner(dashboard: Dashboard, actor_id: uuid.UUID | None) -> None:
        """Only the owner reshapes a dashboard.

        Sharing a dashboard invites colleagues to read it, not to rearrange
        what everyone else sees.
        """
        if dashboard.owner_id is not None and dashboard.owner_id != actor_id:
            raise NotOwnerError

    # --- Internals ---------------------------------------------------------

    async def _record_component_change(
        self,
        action: AuditAction,
        dashboard: Dashboard,
        component: DashboardComponent,
        actor_id: uuid.UUID | None,
    ) -> None:
        """Audit a tile change against its dashboard.

        The dashboard is the entity an audit reader recognises; "tile 8f2c…
        changed" would be unreadable on its own. The tile's own id is in the
        details for anyone who needs to trace it.
        """
        await self.audit.record(
            organization_id=dashboard.organization_id,
            action=action,
            module=DASHBOARD_MODULE,
            actor_id=actor_id,
            entity_type="DASHBOARD_COMPONENT",
            entity_id=component.id,
            entity_label=component.title or dashboard.name,
            details={
                "dashboard_id": str(dashboard.id),
                "saved_report_id": str(component.saved_report_id),
                "display": str(component.display),
                "width": component.width,
            },
        )

    async def _clear_other_defaults(self, dashboard: Dashboard, actor_id: uuid.UUID | None) -> None:
        """One default per person.

        Cleared with a single UPDATE rather than by loading and saving each
        row: this is bookkeeping the user did not ask for, and putting a row
        per old default through the audited update path would fill the trail
        with entries nobody made.
        """
        if dashboard.owner_id is None:
            return
        await self._session.execute(
            update(Dashboard)
            .where(
                Dashboard.organization_id == dashboard.organization_id,
                Dashboard.owner_id == dashboard.owner_id,
                Dashboard.id != dashboard.id,
                Dashboard.is_default.is_(True),
            )
            .values(is_default=False, updated_by_id=actor_id)
        )

    async def _require_free_name(self, organization_id: uuid.UUID, name: str | None) -> None:
        if name is None:
            return
        existing = await self._session.execute(
            select(Dashboard.id).where(
                Dashboard.organization_id == organization_id,
                func.lower(Dashboard.name) == name.strip().lower(),
                Dashboard.deleted_at.is_(None),
            )
        )
        if existing.first() is not None:
            raise ConflictError(f"A dashboard called '{name.strip()}' already exists.")


__all__ = [
    "DASHBOARD_GRID_COLUMNS",
    "DASHBOARD_MODULE",
    "MAX_COMPONENTS_PER_DASHBOARD",
    "UNAVAILABLE_PERMISSION",
    "UNAVAILABLE_REPORT_GONE",
    "DashboardLibraryService",
    "TooManyComponentsError",
]
