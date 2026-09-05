"""Folders and saved reports — the library around the built-in catalogue.

Three rules hold everything here together:

1. **A saved report stores a question, never an answer.** ``run_saved`` resolves
   the period, re-authorizes the caller against the *base report's* module and
   executes it under the caller's own record visibility. Two colleagues opening
   one shared report legitimately see different numbers, and that is the
   feature rather than a bug to paper over.

2. **``reports.*`` governs the object; ``<module>.VIEW`` governs the data.**
   Saving a report you cannot run is allowed and harmless — you have written
   down a question, not obtained an answer. Running it is where the second
   check bites, and it is the same check the ad-hoc route makes.

3. **Sharing is visible to the query, not to the response.** A private report
   belonging to someone else is excluded in SQL, so it is never fetched and
   never counted — the rule ``NoteService`` established, for the same reason.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Collection, Sequence
from typing import Any

from fastapi import status
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.platform.auth.dependencies import Principal
from app.products.crm.reports.catalog import REPORTS
from app.products.crm.reports.models import (
    ReportFolder,
    ReportPeriod,
    SavedReport,
    ShareScope,
)
from app.products.crm.reports.schemas import ReportResult
from app.products.crm.reports.service import ReportService
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService

#: The permission module these entities belong to.
#:
#: Overridden rather than inherited: ``TenantScopedService.audit_module``
#: derives the name from ``__tablename__``, which works everywhere else in the
#: CRM because table and module names coincide. Here two tables
#: (``saved_reports``, ``report_folders``) share one module, so the derivation
#: would file half the trail under a module that does not exist in
#: ``PERMISSION_MODULES`` and make it unfilterable.
REPORTS_MODULE = "reports"


def drop_explicit_nulls(
    values: dict[str, Any], required: Collection[str]
) -> dict[str, Any]:
    """Remove ``None`` for fields the column does not allow to be null.

    ``model_dump(exclude_unset=True)`` keeps a field the client sent
    explicitly as ``null``, which is right for a nullable column — that is how
    a report is moved out of a folder. For a ``NOT NULL`` column it would
    reach the database and come back as a 500, so an explicit null there is
    treated as "no change" instead.

    The alternative, rejecting it, would mean a 422 for a request whose
    meaning is already unambiguous: PATCH means "change these", and asking to
    change a required field to nothing is not a change anybody can want.
    """
    return {
        key: value
        for key, value in values.items()
        if not (value is None and key in required)
    }


class UnknownReportError(AppError):
    """The saved report names a catalogue entry that does not exist."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "unknown_report"
    message = "That report does not exist in the report catalogue."


class FolderNotEmptyError(AppError):
    """Refusing to delete a folder that still holds reports."""

    status_code = status.HTTP_409_CONFLICT
    code = "folder_not_empty"
    message = "Move or delete the reports in this folder first."


class SavedReportInUseError(AppError):
    """Refusing to delete a saved report that dashboards still draw."""

    status_code = status.HTTP_409_CONFLICT
    code = "saved_report_in_use"
    message = "This report is on a dashboard. Remove the tile first."


class NotOwnerError(AppError):
    """Only the owner may change or remove this."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "not_owner"
    message = "Only the owner can change this."


# ---------------------------------------------------------------------------
# Period resolution
# ---------------------------------------------------------------------------


def _quarter_start(day: dt.date) -> dt.date:
    return dt.date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)


def _month_start(day: dt.date) -> dt.date:
    return day.replace(day=1)


def _add_months(day: dt.date, months: int) -> dt.date:
    """Shift a *first-of-month* date by whole months."""
    index = (day.year * 12 + day.month - 1) + months
    return dt.date(index // 12, index % 12 + 1, 1)


def resolve_period(
    period: ReportPeriod,
    *,
    date_from: dt.date | None,
    date_to: dt.date | None,
    today: dt.date,
) -> tuple[dt.date | None, dt.date | None]:
    """Turn a stored period into the two dates a report actually runs with.

    Named periods resolve to the **whole** calendar span — ``THIS_MONTH`` ends
    on the last day of the month, not on today. Reports here look both
    backwards (deals won) and forwards (deals closing), and truncating at today
    would silently empty every forward-looking one: "this quarter's closing
    pipeline" would show only what was already due. Nothing is lost in the
    other direction, because a backward-looking report has no rows in the
    future anyway.

    Trailing windows (``LAST_7_DAYS`` and friends) do end today, and are
    inclusive of it — seven days means today plus the six before it, which is
    what a person means by "the last seven days".
    """
    match period:
        case ReportPeriod.ALL_TIME:
            return None, None
        case ReportPeriod.TODAY:
            return today, today
        case ReportPeriod.LAST_7_DAYS:
            return today - dt.timedelta(days=6), today
        case ReportPeriod.LAST_30_DAYS:
            return today - dt.timedelta(days=29), today
        case ReportPeriod.LAST_90_DAYS:
            return today - dt.timedelta(days=89), today
        case ReportPeriod.THIS_MONTH:
            start = _month_start(today)
            return start, _add_months(start, 1) - dt.timedelta(days=1)
        case ReportPeriod.LAST_MONTH:
            start = _add_months(_month_start(today), -1)
            return start, _add_months(start, 1) - dt.timedelta(days=1)
        case ReportPeriod.THIS_QUARTER:
            start = _quarter_start(today)
            return start, _add_months(start, 3) - dt.timedelta(days=1)
        case ReportPeriod.LAST_QUARTER:
            start = _add_months(_quarter_start(today), -3)
            return start, _add_months(start, 3) - dt.timedelta(days=1)
        case ReportPeriod.THIS_YEAR:
            return dt.date(today.year, 1, 1), dt.date(today.year, 12, 31)
        case ReportPeriod.CUSTOM:
            return date_from, date_to


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


class ReportFolderService(TenantScopedService[ReportFolder]):
    """Flat, organization-wide folders."""

    entity_name = "Report folder"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, ReportFolder), ReportFolder)
        self._session = session

    @property
    def audit_module(self) -> str:
        return REPORTS_MODULE

    async def list_folders(
        self, organization_id: uuid.UUID, *, params: PageParams
    ) -> tuple[Sequence[ReportFolder], int]:
        return await self.list(organization_id, params=params)

    async def create_folder(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> ReportFolder:
        await self._require_free_name(organization_id, values.get("name"))
        payload = dict(values)
        payload["owner_id"] = actor_id
        return await self.create(organization_id=organization_id, actor_id=actor_id, values=payload)

    async def update_folder(
        self,
        folder: ReportFolder,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> ReportFolder:
        payload = drop_explicit_nulls(dict(values), {"name"})
        name = payload.get("name")
        if name is not None and name != folder.name:
            await self._require_free_name(folder.organization_id, name)
        payload.pop("owner_id", None)
        return await self.update(folder, actor_id=actor_id, values=payload)

    async def delete_folder(
        self, folder: ReportFolder, *, actor_id: uuid.UUID | None
    ) -> ReportFolder:
        """Archive an empty folder.

        A non-empty one is refused rather than emptied. Cascading would delete
        colleagues' saved reports as a side effect of tidying, and silently
        unfiling them would leave a pile of homeless reports nobody asked for
        — neither is a decision this call should make on the user's behalf.
        Counted across *every* owner, including private reports the caller
        cannot see, because the folder is genuinely not empty either way.
        """
        remaining = await self._session.execute(
            select(func.count())
            .select_from(SavedReport)
            .where(
                SavedReport.organization_id == folder.organization_id,
                SavedReport.folder_id == folder.id,
                SavedReport.deleted_at.is_(None),
            )
        )
        if int(remaining.scalar_one()) > 0:
            raise FolderNotEmptyError
        return await self.soft_delete(folder, actor_id=actor_id)

    async def _require_free_name(self, organization_id: uuid.UUID, name: str | None) -> None:
        if name is None:
            return
        existing = await self._session.execute(
            select(ReportFolder.id).where(
                ReportFolder.organization_id == organization_id,
                func.lower(ReportFolder.name) == name.strip().lower(),
                ReportFolder.deleted_at.is_(None),
            )
        )
        if existing.first() is not None:
            raise ConflictError(f"A folder called '{name.strip()}' already exists.")


# ---------------------------------------------------------------------------
# Saved reports
# ---------------------------------------------------------------------------


class SavedReportService(TenantScopedService[SavedReport]):
    """Named report definitions, and running them."""

    entity_name = "Saved report"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, SavedReport), SavedReport)
        self._session = session
        self._reports = ReportService(session)

    @property
    def audit_module(self) -> str:
        return REPORTS_MODULE

    # --- Reads -------------------------------------------------------------

    @staticmethod
    def visibility_filter(viewer_id: uuid.UUID | None) -> ColumnElement[bool]:
        """Restrict a query to reports ``viewer_id`` may open.

        Shared reports, plus the viewer's own private ones. An anonymous
        viewer — which cannot happen through the API, but the type allows it —
        sees only what is shared.
        """
        shared = SavedReport.visibility == ShareScope.SHARED
        if viewer_id is None:
            return shared
        return or_(
            shared,
            and_(
                SavedReport.visibility == ShareScope.PRIVATE,
                SavedReport.owner_id == viewer_id,
            ),
        )

    def build_filters(
        self,
        *,
        viewer_id: uuid.UUID | None,
        folder_id: uuid.UUID | None = None,
        unfiled: bool = False,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [self.visibility_filter(viewer_id)]
        if unfiled:
            filters.append(SavedReport.folder_id.is_(None))
        elif folder_id is not None:
            filters.append(SavedReport.folder_id == folder_id)
        return filters

    async def list_saved(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[SavedReport], int]:
        return await self.list(organization_id, params=params, filters=filters)

    async def get_visible_or_404(
        self,
        saved_report_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        viewer_id: uuid.UUID | None,
    ) -> SavedReport:
        """Fetch a report the viewer may open, or 404.

        Someone else's private report is indistinguishable from one that never
        existed — confirming it were there would defeat marking it private.
        """
        saved = await self.get_or_404(saved_report_id, organization_id)
        if saved.visibility is ShareScope.PRIVATE and saved.owner_id != viewer_id:
            raise NotFoundError(f"{self.entity_name} not found.")
        return saved

    # --- Running -----------------------------------------------------------

    async def run_saved(
        self,
        saved: SavedReport,
        principal: Principal,
        *,
        today: dt.date | None = None,
    ) -> ReportResult:
        """Execute a saved report **as the caller**.

        Delegates to the same :class:`ReportService` the ad-hoc route uses, so
        the permission check on the base module and the record-visibility
        narrowing are not re-implemented here and cannot drift from it. The
        only thing this method adds is resolving the stored period into dates.

        Raises:
            UnknownReportError: the catalogue no longer has this key.
            PermissionDeniedError: the caller may not read the base module.
        """
        if saved.base_report_key not in REPORTS:
            raise UnknownReportError

        resolved = today or dt.datetime.now(dt.UTC).date()
        date_from, date_to = resolve_period(
            saved.period,
            date_from=saved.date_from,
            date_to=saved.date_to,
            today=resolved,
        )
        return await self._reports.run(
            saved.base_report_key,
            principal,
            date_from=date_from,
            date_to=date_to,
            today=resolved,
        )

    # --- Commands ----------------------------------------------------------

    async def create_saved(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> SavedReport:
        """Save a report definition.

        The catalogue key and the folder are both validated against the
        caller's own organization before anything is written — a folder id
        belonging to another tenant is a 404, not a foreign-key error.
        """
        payload = dict(values)
        key = payload.get("base_report_key")
        if key not in REPORTS:
            raise UnknownReportError
        await self._require_free_name(organization_id, payload.get("name"))
        await self._require_own_folder(organization_id, payload.get("folder_id"))
        payload["owner_id"] = actor_id
        return await self.create(organization_id=organization_id, actor_id=actor_id, values=payload)

    async def update_saved(
        self,
        saved: SavedReport,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> SavedReport:
        """Edit a saved report. Owners only — see :meth:`require_owner`."""
        payload = drop_explicit_nulls(
            dict(values), {"name", "base_report_key", "period", "visibility"}
        )
        if "base_report_key" in payload and payload["base_report_key"] not in REPORTS:
            raise UnknownReportError
        name = payload.get("name")
        if name is not None and name != saved.name:
            await self._require_free_name(saved.organization_id, name)
        if "folder_id" in payload:
            await self._require_own_folder(saved.organization_id, payload["folder_id"])
        # Ownership is not transferable through a PATCH: it decides who may
        # edit, so letting the body set it would let anyone who can edit hand
        # the report to somebody else — or take it.
        payload.pop("owner_id", None)
        return await self.update(saved, actor_id=actor_id, values=payload)

    async def delete_saved(self, saved: SavedReport, *, actor_id: uuid.UUID | None) -> SavedReport:
        """Archive a saved report, unless a dashboard tile still draws it.

        Refused rather than cascaded: deleting a report you own should not
        silently blank a tile on a colleague's dashboard. The router turns the
        error into a 409 that names the dashboards, so the person deleting can
        go and remove the tiles.
        """
        from app.products.crm.dashboard.models import DashboardComponent

        in_use = await self._session.execute(
            select(func.count())
            .select_from(DashboardComponent)
            .where(
                DashboardComponent.organization_id == saved.organization_id,
                DashboardComponent.saved_report_id == saved.id,
                DashboardComponent.deleted_at.is_(None),
            )
        )
        if int(in_use.scalar_one()) > 0:
            raise SavedReportInUseError
        return await self.soft_delete(saved, actor_id=actor_id)

    @staticmethod
    def require_owner(saved: SavedReport, actor_id: uuid.UUID | None) -> None:
        """Editing and deleting are the owner's alone.

        Sharing a report grants colleagues the right to *run* it, not to
        rewrite it underneath everyone who relies on it. An administrator who
        genuinely needs to remove somebody's report still can — through the
        same route, having taken ownership — but not by accident.
        """
        if saved.owner_id is not None and saved.owner_id != actor_id:
            raise NotOwnerError

    async def _require_free_name(self, organization_id: uuid.UUID, name: str | None) -> None:
        if name is None:
            return
        existing = await self._session.execute(
            select(SavedReport.id).where(
                SavedReport.organization_id == organization_id,
                func.lower(SavedReport.name) == name.strip().lower(),
                SavedReport.deleted_at.is_(None),
            )
        )
        if existing.first() is not None:
            raise ConflictError(f"A report called '{name.strip()}' already exists.")

    async def _require_own_folder(
        self, organization_id: uuid.UUID, folder_id: uuid.UUID | None
    ) -> None:
        if folder_id is None:
            return
        found = await self._session.execute(
            select(ReportFolder.id).where(
                ReportFolder.organization_id == organization_id,
                ReportFolder.id == folder_id,
                ReportFolder.deleted_at.is_(None),
            )
        )
        if found.first() is None:
            raise NotFoundError("Report folder not found.")


__all__ = [
    "REPORTS_MODULE",
    "FolderNotEmptyError",
    "NotOwnerError",
    "ReportFolderService",
    "SavedReportInUseError",
    "SavedReportService",
    "UnknownReportError",
    "resolve_period",
]
