"""CSV import routes.

Three endpoints, matching the three questions the wizard asks:

``GET  /crm/imports/entities``          what can I import, and onto which fields?
``POST /crm/imports/{entity}/preview``  what would happen if I did?
``POST /crm/imports/{entity}/commit``   do it.

The file is uploaded again for the commit rather than parked on the server
between the two calls. That keeps the API stateless -- no temporary storage to
secure, expire or clean up -- and at a 5 000-row ceiling the second upload is
under a megabyte. It also removes a whole class of bug where the commit
operates on a file the preview did not describe.
"""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.core.database import DbSession
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.platform.auth.dependencies import AuthorizationServiceDep, CurrentPrincipal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.imports.catalog import (
    IMPORTABLE,
    ImportableEntity,
    field_names,
    required_fields,
)
from app.products.crm.imports.schemas import (
    DuplicatePolicy,
    ImportEntityInfo,
    ImportFieldInfo,
    ImportResult,
)
from app.products.crm.imports.service import (
    MAX_IMPORT_ROWS,
    ImportFileError,
    ImportService,
    parse_csv,
)

router = APIRouter()


def _entity_or_404(slug: str) -> ImportableEntity:
    entity = IMPORTABLE.get(slug)
    if entity is None:
        raise NotFoundError(f"'{slug}' cannot be imported.")
    return entity


def _describe(entity: ImportableEntity) -> ImportEntityInfo:
    required = set(required_fields(entity))
    return ImportEntityInfo(
        slug=entity.slug,
        label=entity.label,
        fields=[
            ImportFieldInfo(name=name, required=name in required)
            for name in field_names(entity)
        ],
        duplicate_field=entity.duplicate_field,
        max_rows=MAX_IMPORT_ROWS,
    )


@router.get("/entities", response_model=list[ImportEntityInfo])
async def list_importable_entities() -> list[ImportEntityInfo]:
    """The entities and their fields, for the wizard's mapping step.

    Unauthenticated callers are refused by the CRM router's own dependencies;
    no permission beyond CRM access is required to read this, because it
    describes the *schema* and names no customer data.
    """
    return [_describe(entity) for entity in IMPORTABLE.values()]


def _parse_mapping(raw: str) -> dict[str, str]:
    """Read the wizard's column mapping out of a multipart form field.

    JSON in a form field rather than a JSON body because the file travels in
    the same request. Malformed input is a 422 naming the field, not a 500.
    """
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError("`mapping` must be valid JSON.") from exc

    if not isinstance(parsed, dict) or not parsed:
        raise ValidationFailedError("`mapping` must be a non-empty object of column to field.")

    mapping: dict[str, str] = {}
    for header, field in parsed.items():
        if not isinstance(header, str) or not isinstance(field, str):
            raise ValidationFailedError("`mapping` must map column names to field names.")
        if field:
            mapping[header] = field
    if not mapping:
        raise ValidationFailedError("Map at least one column before importing.")
    return mapping


async def _run(
    *,
    slug: str,
    session: DbSession,
    principal: CurrentPrincipal,
    authorization: AuthorizationServiceDep,
    upload: UploadFile,
    mapping_json: str,
    duplicate_policy: DuplicatePolicy,
    dry_run: bool,
) -> ImportResult:
    """Shared body of preview and commit -- identical but for ``dry_run``.

    **Where the permission is checked.** The entity is a path parameter, so
    the module to authorize against is not known when the route is declared
    and ``require_permission(module, action)`` -- which takes both at import
    time -- cannot express it. The check is therefore made here, against the
    entity the caller actually named, through the same
    ``AuthorizationService.require`` the dependency uses and raising the same
    ``PermissionDeniedError``.

    It runs **before the file is read**. An unauthorized caller should not be
    able to make the server parse a megabyte of their CSV, and a 403 that
    arrives only after the upload has been processed has already done the work
    it was meant to refuse.

    ``CREATE`` is the permission, for both preview and commit. A preview runs
    the real creates and rolls them back; treating it as a lesser act would let
    a caller without ``CREATE`` probe the organization's duplicate rule -- for
    instance to learn whether an email is already on a lead.
    """
    entity = _entity_or_404(slug)
    await authorization.require(
        membership_id=principal.membership_id,
        module=entity.module,
        action=PermissionAction.CREATE,
    )
    mapping = _parse_mapping(mapping_json)

    unknown = set(mapping.values()) - set(field_names(entity))
    if unknown:
        raise ValidationFailedError(
            f"Unknown {entity.label} field(s): {', '.join(sorted(unknown))}."
        )

    raw = await upload.read()
    if not raw:
        raise ImportFileError("The file is empty.")

    headers, rows = parse_csv(raw)
    service = ImportService(session, entity)
    return await service.run(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        headers=headers,
        rows=rows,
        mapping=mapping,
        duplicate_policy=duplicate_policy,
        dry_run=dry_run,
    )


@router.post("/{slug}/preview", response_model=ImportResult)
async def preview_import(
    slug: str,
    session: DbSession,
    principal: CurrentPrincipal,
    authorization: AuthorizationServiceDep,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
    duplicate_policy: Annotated[DuplicatePolicy, Form()] = DuplicatePolicy.SKIP,
) -> ImportResult:
    """Report what a commit would do, without keeping any of it."""
    return await _run(
        slug=slug,
        session=session,
        principal=principal,
        authorization=authorization,
        upload=file,
        mapping_json=mapping,
        duplicate_policy=duplicate_policy,
        dry_run=True,
    )


@router.post("/{slug}/commit", response_model=ImportResult)
async def commit_import(
    slug: str,
    session: DbSession,
    principal: CurrentPrincipal,
    authorization: AuthorizationServiceDep,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str, Form()],
    duplicate_policy: Annotated[DuplicatePolicy, Form()] = DuplicatePolicy.SKIP,
) -> ImportResult:
    """Run the import and keep the rows that succeeded."""
    return await _run(
        slug=slug,
        session=session,
        principal=principal,
        authorization=authorization,
        upload=file,
        mapping_json=mapping,
        duplicate_policy=duplicate_policy,
        dry_run=False,
    )


__all__ = ["router"]
