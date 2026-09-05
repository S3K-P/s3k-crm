"""Report routes.

``GET  /crm/reports``            what can I run?
``POST /crm/reports/{key}/run``  run it, with a period.

Neither route is gated by ``require_permission``, and — as with
``/crm/search`` — the reason is that the permission is not known when the
route is declared. A report names its own module, so the check is made inside
the handler against the report the caller actually asked for; the catalogue
route makes no single check at all, because *which* reports are available is
the answer it returns rather than a precondition for asking.

Both therefore take :data:`~app.platform.auth.dependencies.PermissionedPrincipal`,
which proves authentication and membership and loads the permission snapshot
without asserting any of it. That is only safe because the service does
assert it — see ``service.run``. A handler wired to this dependency that
then read without consulting the snapshot would be an unauthenticated read
wearing a login.

``run`` is a POST rather than a GET because its parameters are a body, and
because a report is a computation over the whole tenant's data rather than a
cacheable resource. It is nonetheless side-effect free.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import DbSession
from app.platform.auth.dependencies import PermissionedPrincipal
from app.products.crm.reports.schemas import ReportResult, ReportRunRequest, ReportSummary
from app.products.crm.reports.service import ReportService

router = APIRouter()


def get_service(session: DbSession) -> ReportService:
    return ReportService(session)


ServiceDep = Annotated[ReportService, Depends(get_service)]


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
    return await service.run(
        key, principal, date_from=payload.date_from, date_to=payload.date_to
    )


__all__ = ["router"]
