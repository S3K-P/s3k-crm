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
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile, status

from app.core.database import DbSession
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.platform.auth.dependencies import AuthorizationServiceDep, CurrentPrincipal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.imports.catalog import (
    IMPORTABLE,
    ImportableEntity,
    custom_field_key,
    custom_field_targets,
    field_names,
    required_fields,
)
from app.products.crm.imports.schemas import (
    DuplicatePolicy,
    ImportEntityInfo,
    ImportFieldInfo,
    ImportMappingTemplateCreate,
    ImportMappingTemplateResponse,
    ImportResult,
)
from app.products.crm.imports.service import (
    MAX_IMPORT_ROWS,
    ImportFileError,
    ImportMappingTemplateService,
    ImportService,
    parse_csv,
)

router = APIRouter()


def _entity_or_404(slug: str) -> ImportableEntity:
    entity = IMPORTABLE.get(slug)
    if entity is None:
        raise NotFoundError(f"'{slug}' cannot be imported.")
    return entity


async def _describe(
    entity: ImportableEntity, session: DbSession, organization_id: uuid.UUID
) -> ImportEntityInfo:
    required = set(required_fields(entity))
    fields = [
        ImportFieldInfo(name=name, required=name in required) for name in field_names(entity)
    ]
    # Checkpoint 4: this organization's own active custom fields, offered
    # alongside the built-in columns as `custom:<api_name>` mapping targets.
    # Never required here — the *entity's* required-ness (and any layout's
    # conditional override) is enforced where every other write is, inside
    # `CustomFieldValueService.resolve`, not duplicated into this listing.
    for definition in await custom_field_targets(session, entity, organization_id):
        fields.append(ImportFieldInfo(name=custom_field_key(definition.api_name), required=False))
    return ImportEntityInfo(
        slug=entity.slug,
        label=entity.label,
        fields=fields,
        duplicate_field=entity.duplicate_field,
        max_rows=MAX_IMPORT_ROWS,
    )


@router.get("/entities", response_model=list[ImportEntityInfo])
async def list_importable_entities(
    principal: CurrentPrincipal, session: DbSession
) -> list[ImportEntityInfo]:
    """The entities and their fields, for the wizard's mapping step.

    Unauthenticated callers are refused by the CRM router's own dependencies;
    no permission beyond CRM access is required to read this, because it
    describes the *schema* — including which custom fields this organization
    has defined, not any customer data — the same call
    ``custom_fields.VIEW`` being granted to every system role already makes.
    """
    return [
        await _describe(entity, session, principal.organization_id)
        for entity in IMPORTABLE.values()
    ]


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

    # Checkpoint 4: a target may also be `custom:<api_name>`, resolved against
    # this organization's own *active* definitions — never a fixed schema, so
    # this list has to be built per request rather than joined onto
    # `field_names`, which is intentionally organization-agnostic.
    known_custom = {
        custom_field_key(definition.api_name)
        for definition in await custom_field_targets(session, entity, principal.organization_id)
    }
    unknown = set(mapping.values()) - set(field_names(entity)) - known_custom
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


# --- Saved mapping templates (Checkpoint 4) --------------------------------
#
# Same authorization shape as preview/commit above: the entity is a path
# parameter, so the module is resolved from it rather than declared on the
# route. A template names no customer data — only which CSV column an
# importer once pointed at which field — so `VIEW` is enough to list one and
# `CREATE`/`DELETE` (the same actions importing itself requires) to save or
# remove one, rather than inventing a permission of its own.


def _template_service(session: DbSession) -> ImportMappingTemplateService:
    return ImportMappingTemplateService(session)


@router.get("/{slug}/mapping-templates", response_model=list[ImportMappingTemplateResponse])
async def list_mapping_templates(
    slug: str,
    session: DbSession,
    principal: CurrentPrincipal,
    authorization: AuthorizationServiceDep,
) -> list[ImportMappingTemplateResponse]:
    entity = _entity_or_404(slug)
    await authorization.require(
        membership_id=principal.membership_id, module=entity.module, action=PermissionAction.VIEW
    )
    templates = await _template_service(session).for_entity(principal.organization_id, slug)
    return [ImportMappingTemplateResponse.model_validate(t) for t in templates]


@router.post(
    "/{slug}/mapping-templates",
    response_model=ImportMappingTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_mapping_template(
    slug: str,
    payload: ImportMappingTemplateCreate,
    session: DbSession,
    principal: CurrentPrincipal,
    authorization: AuthorizationServiceDep,
) -> ImportMappingTemplateResponse:
    entity = _entity_or_404(slug)
    await authorization.require(
        membership_id=principal.membership_id, module=entity.module, action=PermissionAction.CREATE
    )
    known_custom = {
        custom_field_key(definition.api_name)
        for definition in await custom_field_targets(session, entity, principal.organization_id)
    }
    unknown = set(payload.mapping.values()) - set(field_names(entity)) - known_custom
    if unknown:
        raise ValidationFailedError(
            f"Unknown {entity.label} field(s): {', '.join(sorted(unknown))}."
        )
    template = await _template_service(session).create_template(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        entity_slug=slug,
        values=payload.model_dump(),
    )
    return ImportMappingTemplateResponse.model_validate(template)


@router.delete("/{slug}/mapping-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping_template(
    slug: str,
    template_id: uuid.UUID,
    session: DbSession,
    principal: CurrentPrincipal,
    authorization: AuthorizationServiceDep,
) -> Response:
    entity = _entity_or_404(slug)
    await authorization.require(
        membership_id=principal.membership_id, module=entity.module, action=PermissionAction.DELETE
    )
    service = _template_service(session)
    template = await service.get_or_404(template_id, principal.organization_id)
    if template.entity_slug != slug:
        raise NotFoundError("Mapping template not found.")
    await service.soft_delete(template, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
