"""Import, export and bulk-operation routes.

Permissions are the interesting part, and each one is deliberate:

* **Import needs CREATE and EDIT** on the target module, because a file in
  ``BOTH`` mode does both. Requiring the pair up front is simpler to reason
  about than deciding per row, and a user who may only create should not
  discover mid-file that half their rows were refused.
* **Export needs EXPORT.** The permission has existed in the catalogue since
  the beginning and nothing implemented it (analysis §5.8) — a matrix that
  promises a capability the product does not have is worse than one that
  admits the gap.
* **Bulk archive needs DELETE, bulk update needs EDIT**, matching the
  single-record verbs. Bulk is a volume change, not a privilege change.

Record-level visibility is applied to every operation, so a rep cannot export,
update or archive a record they cannot open.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status

from app.core.database import DbSession
from app.core.exceptions import ValidationFailedError
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.platform.authorization.service import PermissionDeniedError
from app.products.crm.datatransfer.models import ImportMode
from app.products.crm.datatransfer.registry import MODULES
from app.products.crm.datatransfer.schemas import (
    BulkOwnerRequest,
    BulkResultResponse,
    BulkSelection,
    BulkStageRequest,
    BulkStageResultResponse,
    BulkUpdateRequest,
    FieldDescriptor,
    ImportJobResponse,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportResultResponse,
    ImportRowErrorResponse,
    ImportUndoResponse,
    ModuleCatalog,
    ModuleDescriptor,
)
from app.products.crm.datatransfer.service import DataTransferService, require_module
from app.products.crm.opportunities.service import OpportunityService
from app.products.crm.shared.visibility import RecordVisibility

router = APIRouter()

#: Uploads are capped well below the row limit's worst case. A file larger than
#: this is a migration that should be split, and accepting it would mean
#: buffering it in memory before the row count could refuse it.
MAX_UPLOAD_BYTES = 16 * 1024 * 1024


def get_service(session: DbSession) -> DataTransferService:
    return DataTransferService(session)


ServiceDep = Annotated[DataTransferService, Depends(get_service)]

#: Every route here resolves its real permission from the module in the
#: path (see ``_authorize``). This dependency is the doorway check: the
#: caller must be able to open the CRM at all. It is deliberately the
#: weakest permission in the catalogue, not the operative one.
CrmUser = Annotated[
    Principal, Depends(require_permission("dashboard", PermissionAction.VIEW))
]


async def _authorize(
    principal: Principal, module_key: str, *actions: PermissionAction
) -> None:
    """Check the caller holds every action on the module they named.

    The module arrives in the path, so the permission cannot be resolved by a
    route-level dependency the way every other CRM endpoint does it. Checking
    here keeps the rule in one place rather than repeated per handler.
    """
    module = require_module(module_key)
    missing = [
        action.value
        for action in actions
        if not principal.has_permission(module.permission_module, action)
    ]
    if missing:
        raise PermissionDeniedError(
            f"You do not have permission to do this on {module.key}.",
            details={"module": module.permission_module, "requires": missing},
        )


def _visibility(principal: Principal, module_key: str) -> RecordVisibility:
    module = require_module(module_key)
    return RecordVisibility.for_module(principal, module.permission_module)


async def _read_upload(upload: UploadFile) -> bytes:
    raw = await upload.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationFailedError(
            f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)}MB.",
            details={"size": len(raw)},
        )
    return raw


def _parse_mapping(raw: str | None) -> dict[str, str] | None:
    """Decode the ``header=field,header=field`` mapping form value.

    A flat string rather than JSON because it travels in a multipart form
    alongside the file, and a nested body would mean two requests or a
    base64'd blob.
    """
    if not raw or not raw.strip():
        return None
    mapping: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        header, _, target = pair.partition("=")
        header, target = header.strip(), target.strip()
        if header and target:
            mapping[header] = target
    return mapping or None


# --- Discovery ---------------------------------------------------------------


@router.get("/modules", response_model=ModuleCatalog)
async def list_modules(
    principal: CrmUser,
) -> ModuleCatalog:
    """Which modules support import/export, and what fields they accept.

    Drives the mapping UI. Gated on the weakest CRM permission there is: this
    is schema, not data, and a user who can open the CRM at all may see it.
    """
    del principal
    return ModuleCatalog(
        modules=[
            ModuleDescriptor(
                key=module.key,
                fields=[
                    FieldDescriptor(
                        name=spec.name,
                        kind=spec.kind.value,
                        required=spec.required,
                        max_length=spec.max_length,
                        choices=list(spec.choices),
                        accepts_name=spec.lookup_model is not None,
                    )
                    for spec in module.fields
                ],
                match_fields=list(module.match_fields),
                bulk_updatable=list(module.bulk_updatable),
                required_fields=list(module.required_fields()),
            )
            for module in MODULES.values()
        ]
    )


# --- Import ------------------------------------------------------------------


@router.post("/{module_key}/preview", response_model=ImportPreviewResponse)
async def preview_import(
    module_key: str,
    principal: CrmUser,
    service: ServiceDep,
    file: Annotated[UploadFile, File()],
    mode: Annotated[ImportMode, Form()] = ImportMode.ADD,
    match_field: Annotated[str | None, Form()] = None,
    skip_empty_values: Annotated[bool, Form()] = True,
    mapping: Annotated[str | None, Form()] = None,
) -> ImportPreviewResponse:
    """Validate a file and report what importing it would do. Writes nothing."""
    await _authorize(principal, module_key, PermissionAction.CREATE, PermissionAction.EDIT)
    raw = await _read_upload(file)

    module, outcome = await service.preview_import(
        organization_id=principal.organization_id,
        module_key=module_key,
        raw=raw,
        filename=file.filename or "upload.csv",
        mapping=_parse_mapping(mapping),
        mode=mode,
        match_field=match_field,
        skip_empty_values=skip_empty_values,
    )
    return ImportPreviewResponse(
        module=module.key,
        total_rows=outcome.total_rows,
        will_create=outcome.created,
        will_update=outcome.updated,
        will_skip=outcome.skipped,
        error_count=len(outcome.errors),
        headers=outcome.headers,
        mapping=outcome.mapping,
        unmapped_headers=outcome.unmapped_headers,
        rows=[
            ImportPreviewRow(
                row_number=row.row_number,
                action=row.action,
                values=row.values,
                matched_id=row.matched_id,
            )
            for row in outcome.preview
        ],
        errors=[
            ImportRowErrorResponse(
                row_number=error.row_number,
                field_name=error.field_name,
                message=error.message,
            )
            for error in outcome.errors[:200]
        ],
    )


@router.post(
    "/{module_key}", response_model=ImportResultResponse, status_code=status.HTTP_201_CREATED
)
async def run_import(
    module_key: str,
    principal: CrmUser,
    service: ServiceDep,
    file: Annotated[UploadFile, File()],
    mode: Annotated[ImportMode, Form()] = ImportMode.ADD,
    match_field: Annotated[str | None, Form()] = None,
    skip_empty_values: Annotated[bool, Form()] = True,
    mapping: Annotated[str | None, Form()] = None,
) -> ImportResultResponse:
    """Import a file. Rows that fail are reported; the rest still land."""
    await _authorize(principal, module_key, PermissionAction.CREATE, PermissionAction.EDIT)
    raw = await _read_upload(file)

    job, outcome = await service.run_import(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        module_key=module_key,
        raw=raw,
        filename=file.filename or "upload.csv",
        mapping=_parse_mapping(mapping),
        mode=mode,
        match_field=match_field,
        skip_empty_values=skip_empty_values,
    )
    return ImportResultResponse(
        job=ImportJobResponse.model_validate(job),
        errors=[
            ImportRowErrorResponse(
                row_number=error.row_number,
                field_name=error.field_name,
                message=error.message,
            )
            for error in outcome.errors[:200]
        ],
    )


@router.get("", response_model=list[ImportJobResponse])
async def list_imports(
    principal: CrmUser,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ImportJobResponse]:
    """Import history for the organization."""
    jobs = await service.list_jobs(principal.organization_id, limit=limit)
    return [ImportJobResponse.model_validate(job) for job in jobs]


@router.get("/{job_id}/errors", response_model=list[ImportRowErrorResponse])
async def import_errors(
    job_id: uuid.UUID,
    principal: CrmUser,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[ImportRowErrorResponse]:
    """Every row that did not land, with the reason and the spreadsheet line."""
    job = await service.get_job(job_id, principal.organization_id)
    errors = await service.job_errors(job, limit=limit)
    return [ImportRowErrorResponse.model_validate(error) for error in errors]


@router.post("/{job_id}/undo", response_model=ImportUndoResponse)
async def undo_import(
    job_id: uuid.UUID,
    principal: CrmUser,
    service: ServiceDep,
) -> ImportUndoResponse:
    """Archive the records this import created.

    Records it *updated* are left alone — reversing those would need a
    before-image the import does not store. The response says how many, so the
    caller is never left assuming the file was fully reversed.
    """
    job = await service.get_job(job_id, principal.organization_id)
    await _authorize(principal, job.module, PermissionAction.DELETE)
    archived = await service.undo_import(job, actor_id=principal.user_id)
    return ImportUndoResponse(archived=archived, updates_not_reverted=job.updated_count)


# --- Export ------------------------------------------------------------------


@router.get("/{module_key}/export")
async def export_module(
    module_key: str,
    principal: CrmUser,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=50_000)] = 50_000,
) -> Response:
    """Download the caller's visible records as CSV.

    Requires the ``EXPORT`` permission on the module — the first thing in the
    product to actually use it.
    """
    await _authorize(principal, module_key, PermissionAction.VIEW, PermissionAction.EXPORT)

    module, body, rows = await service.export_csv(
        organization_id=principal.organization_id,
        module_key=module_key,
        visibility=_visibility(principal, module_key),
        limit=limit,
    )
    filename = f"{module.key}-{principal.organization_id}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Lets the UI report the row count without parsing the body.
            "X-Exported-Rows": str(rows),
        },
    )


# --- Bulk operations ---------------------------------------------------------


@router.post("/{module_key}/bulk/update", response_model=BulkResultResponse)
async def bulk_update(
    module_key: str,
    payload: BulkUpdateRequest,
    principal: CrmUser,
    service: ServiceDep,
) -> BulkResultResponse:
    """Set the same fields on many records."""
    await _authorize(principal, module_key, PermissionAction.EDIT)
    changed = await service.bulk_update(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        module_key=module_key,
        ids=payload.ids,
        values=payload.values,
        visibility=_visibility(principal, module_key),
    )
    return BulkResultResponse(requested=len(payload.ids), changed=changed)


@router.post("/{module_key}/bulk/archive", response_model=BulkResultResponse)
async def bulk_archive(
    module_key: str,
    payload: BulkSelection,
    principal: CrmUser,
    service: ServiceDep,
) -> BulkResultResponse:
    """Soft-delete many records."""
    await _authorize(principal, module_key, PermissionAction.DELETE)
    changed = await service.bulk_archive(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        module_key=module_key,
        ids=payload.ids,
        visibility=_visibility(principal, module_key),
    )
    return BulkResultResponse(requested=len(payload.ids), changed=changed)


@router.post("/{module_key}/bulk/restore", response_model=BulkResultResponse)
async def bulk_restore(
    module_key: str,
    payload: BulkSelection,
    principal: CrmUser,
    service: ServiceDep,
) -> BulkResultResponse:
    """Bring archived records back."""
    await _authorize(principal, module_key, PermissionAction.DELETE)
    changed = await service.bulk_restore(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        module_key=module_key,
        ids=payload.ids,
        visibility=_visibility(principal, module_key),
    )
    return BulkResultResponse(requested=len(payload.ids), changed=changed)


@router.post("/{module_key}/bulk/owner", response_model=BulkResultResponse)
async def bulk_assign_owner(
    module_key: str,
    payload: BulkOwnerRequest,
    principal: CrmUser,
    service: ServiceDep,
) -> BulkResultResponse:
    """Reassign many records to one owner."""
    await _authorize(principal, module_key, PermissionAction.EDIT)
    changed = await service.bulk_assign_owner(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        module_key=module_key,
        ids=payload.ids,
        owner_id=payload.owner_id,
        visibility=_visibility(principal, module_key),
    )
    return BulkResultResponse(requested=len(payload.ids), changed=changed)


@router.post("/opportunities/bulk/stage", response_model=BulkStageResultResponse)
async def bulk_change_stage(
    payload: BulkStageRequest,
    principal: Annotated[
        Principal, Depends(require_permission("opportunities", PermissionAction.EDIT))
    ],
    session: DbSession,
    service: ServiceDep,
) -> BulkStageResultResponse:
    """Move many deals to one stage.

    Deliberately **not** a bulk column update. A stage move applies the win/loss
    rules, stamps closure timestamps, derives probability, writes stage history
    and fires the stage's follow-up — so it runs the real
    ``change_stage`` per deal rather than a blind UPDATE that would skip all
    five. Deals that refuse (already closed, missing a loss reason) are
    reported individually instead of failing the batch.
    """
    del service
    opportunities = OpportunityService(session)
    visibility = RecordVisibility.for_module(principal, "opportunities")

    changed = 0
    failures: list[str] = []
    for opportunity_id in dict.fromkeys(payload.ids):
        try:
            opportunity = await opportunities.get_or_404(
                opportunity_id, principal.organization_id, visibility=visibility
            )
            await opportunities.change_stage(
                opportunity,
                stage_id=payload.stage_id,
                actor_id=principal.user_id,
                loss_reason=payload.loss_reason,
                win_reason=payload.win_reason,
            )
            changed += 1
        except Exception as error:
            failures.append(f"{opportunity_id}: {getattr(error, 'message', str(error))}")

    return BulkStageResultResponse(
        requested=len(payload.ids), changed=changed, failures=failures[:50]
    )


__all__ = ["router"]
