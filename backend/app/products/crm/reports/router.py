"""Report routes.

Two groups, authorized two different ways, and the split is the module's
design rather than an inconsistency:

**Running a report** — ``GET /crm/reports``, ``POST /crm/reports/{key}/run``,
``POST /crm/reports/saved/{id}/run`` — is not gated by ``require_permission``,
for the same reason ``/crm/search`` is not: the permission is not known when
the route is declared. A report names its own module, so the check is made
inside the handler against the report the caller actually asked for; the
catalogue route makes no single check at all, because *which* reports are
available is the answer it returns rather than a precondition for asking.
These take :data:`~app.platform.auth.dependencies.PermissionedPrincipal`,
which proves authentication and membership and loads the permission snapshot
without asserting any of it. That is only safe because the service does assert
it — see ``service.run``.

**Managing the library** — folders and saved reports — *is* gated, on
``reports.*``, because the object's own lifecycle is knowable up front. Saving
a definition you cannot run is deliberately allowed: you have written down a
question, not obtained an answer, and the run route still refuses you.

Route order matters here. ``/saved`` and ``/folders`` are declared **before**
``/{key}/run`` so a literal segment is never captured as a report key.

``run`` is a POST rather than a GET because its parameters are a body, and
because a report is a computation over the whole tenant's data rather than a
cacheable resource. It is nonetheless side-effect free.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import (
    PermissionedPrincipal,
    Principal,
    require_permission,
)
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.reports.library import (
    REPORTS_MODULE,
    ReportFolderService,
    SavedReportService,
)
from app.products.crm.reports.schemas import (
    ReportFolderCreate,
    ReportFolderResponse,
    ReportFolderUpdate,
    ReportResult,
    ReportRunRequest,
    ReportSummary,
    SavedReportCreate,
    SavedReportResponse,
    SavedReportUpdate,
)
from app.products.crm.reports.service import ReportService
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()

MODULE = REPORTS_MODULE
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_service(session: DbSession) -> ReportService:
    return ReportService(session)


def get_folders(session: DbSession) -> ReportFolderService:
    return ReportFolderService(session)


def get_saved(session: DbSession) -> SavedReportService:
    return SavedReportService(session)


ServiceDep = Annotated[ReportService, Depends(get_service)]
FolderDep = Annotated[ReportFolderService, Depends(get_folders)]
SavedDep = Annotated[SavedReportService, Depends(get_saved)]


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ReportSummary])
async def list_reports(
    principal: PermissionedPrincipal, service: ServiceDep
) -> list[ReportSummary]:
    """The reports this caller may run, with their columns' chart hints.

    An empty list is a legitimate answer for somebody holding no CRM ``VIEW``
    permission, not a 403: a reports screen that refuses to load tells the
    person there is something there to see.
    """
    return service.catalogue(principal)


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------


@router.get("/folders", response_model=Page[ReportFolderResponse])
async def list_folders(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: FolderDep,
    params: PageParamsDep,
) -> Page[ReportFolderResponse]:
    """Every folder in the organization. Folders are not privately owned."""
    items, total = await service.list_folders(principal.organization_id, params=params)
    return Page.build(
        [ReportFolderResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@router.post("/folders", response_model=ReportFolderResponse, status_code=status.HTTP_201_CREATED)
async def create_folder(
    payload: ReportFolderCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: FolderDep,
) -> ReportFolderResponse:
    """Create a folder. A name already in use is a 409."""
    folder = await service.create_folder(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return ReportFolderResponse.model_validate(folder)


@router.patch("/folders/{folder_id}", response_model=ReportFolderResponse)
async def update_folder(
    folder_id: uuid.UUID,
    payload: ReportFolderUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: FolderDep,
) -> ReportFolderResponse:
    """Rename or re-describe a folder.

    Not restricted to the creator: a folder is shared furniture, and the
    organization's filing should not be frozen by whoever happened to make it.
    """
    folder = await service.get_or_404(folder_id, principal.organization_id)
    updated = await service.update_folder(
        folder, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return ReportFolderResponse.model_validate(updated)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_folder(
    folder_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: FolderDep,
) -> Response:
    """Archive an empty folder. A folder with reports in it is a 409."""
    folder = await service.get_or_404(folder_id, principal.organization_id)
    await service.delete_folder(folder, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Saved reports
# ---------------------------------------------------------------------------


@router.get("/saved", response_model=Page[SavedReportResponse])
async def list_saved_reports(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: SavedDep,
    params: PageParamsDep,
    folder_id: Annotated[uuid.UUID | None, Query()] = None,
    unfiled: Annotated[bool, Query()] = False,
) -> Page[SavedReportResponse]:
    """Saved reports the caller may open, newest first.

    Colleagues' private reports are excluded by the query itself, so they are
    never fetched and never counted. ``unfiled=true`` returns the ones in no
    folder and takes precedence over ``folder_id``.
    """
    filters = service.build_filters(
        viewer_id=principal.user_id, folder_id=folder_id, unfiled=unfiled
    )
    items, total = await service.list_saved(
        principal.organization_id, params=params, filters=filters
    )
    return Page.build(
        [SavedReportResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@router.post("/saved", response_model=SavedReportResponse, status_code=status.HTTP_201_CREATED)
async def create_saved_report(
    payload: SavedReportCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: SavedDep,
) -> SavedReportResponse:
    """Save a report definition.

    Deliberately does **not** require permission on the base report's module.
    Writing down "pipeline by stage, this quarter" discloses nothing; running
    it is where ``opportunities.VIEW`` is demanded, and it is demanded there
    every time.
    """
    saved = await service.create_saved(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return SavedReportResponse.model_validate(saved)


@router.get("/saved/{saved_report_id}", response_model=SavedReportResponse)
async def get_saved_report(
    saved_report_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: SavedDep,
) -> SavedReportResponse:
    """One saved report. Somebody else's private report returns 404."""
    saved = await service.get_visible_or_404(
        saved_report_id, principal.organization_id, viewer_id=principal.user_id
    )
    return SavedReportResponse.model_validate(saved)


@router.patch("/saved/{saved_report_id}", response_model=SavedReportResponse)
async def update_saved_report(
    saved_report_id: uuid.UUID,
    payload: SavedReportUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: SavedDep,
) -> SavedReportResponse:
    """Edit a saved report. Owners only, whatever the sharing setting."""
    saved = await service.get_visible_or_404(
        saved_report_id, principal.organization_id, viewer_id=principal.user_id
    )
    service.require_owner(saved, principal.user_id)
    updated = await service.update_saved(
        saved, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return SavedReportResponse.model_validate(updated)


@router.delete("/saved/{saved_report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_saved_report(
    saved_report_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: SavedDep,
) -> Response:
    """Archive a saved report. Owners only; a report on a dashboard is a 409."""
    saved = await service.get_visible_or_404(
        saved_report_id, principal.organization_id, viewer_id=principal.user_id
    )
    service.require_owner(saved, principal.user_id)
    await service.delete_saved(saved, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/saved/{saved_report_id}/run", response_model=ReportResult)
async def run_saved_report(
    saved_report_id: uuid.UUID,
    principal: PermissionedPrincipal,
    service: SavedDep,
) -> ReportResult:
    """Run a saved report as the caller.

    Both checks apply, in order: the report must be one this caller may open
    (theirs, or shared), and its base module must be one they may read. A
    shared report therefore returns *the caller's* numbers — the person who
    saved it cannot use sharing to hand out their own wider view.
    """
    saved = await service.get_visible_or_404(
        saved_report_id, principal.organization_id, viewer_id=principal.user_id
    )
    return await service.run_saved(saved, principal)


# ---------------------------------------------------------------------------
# Ad-hoc runs
# ---------------------------------------------------------------------------


@router.post("/{key}/run", response_model=ReportResult)
async def run_report(
    key: str,
    payload: ReportRunRequest,
    principal: PermissionedPrincipal,
    service: ServiceDep,
) -> ReportResult:
    """Run one report over the caller's own slice of the organization's data.

    A key that does not exist is a 404; a report whose module the caller
    cannot read is a 403. Rows are narrowed by the same record-level
    visibility the module's list endpoint applies, so the totals here and the
    list there describe the same records.
    """
    return await service.run(key, principal, date_from=payload.date_from, date_to=payload.date_to)


__all__ = ["router"]
