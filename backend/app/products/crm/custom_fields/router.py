"""Custom field and picklist routes.

Two routers on one permission module, mounted at ``/crm/custom-fields`` and
``/crm/picklists``. Two prefixes because a picklist is not a field and does not
belong under ``/crm/custom-fields/{id}``, where it would collide with a field
id — the same reasoning that gave email templates their own prefix.

**The permission split, and why ``VIEW`` is granted to everyone.** Defining a
field is administration and needs ``custom_fields.CREATE`` / ``EDIT`` /
``DELETE``, which only Admin holds. *Reading* the definitions is not: every
user who can open a lead needs to know which custom fields that form has, or
the form cannot be drawn. So ``custom_fields.VIEW`` is granted to Manager and
User as well, and it grants sight of the tenant's own configuration only —
never of a single record's values, which stay behind the record's own module
permission.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.common import CrmEntityType
from app.products.crm.custom_fields.models import CustomFieldDefinition, PicklistOption
from app.products.crm.custom_fields.schemas import (
    CustomFieldCreate,
    CustomFieldReorder,
    CustomFieldResponse,
    CustomFieldUpdate,
    EntitySchemaResponse,
    PicklistCreate,
    PicklistOptionCreate,
    PicklistOptionResponse,
    PicklistOptionUpdate,
    PicklistResponse,
    PicklistUpdate,
)
from app.products.crm.custom_fields.service import CustomFieldService, PicklistService
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()
picklists_router = APIRouter()

MODULE = "custom_fields"
PageParamsDep = Annotated[PageParams, Depends(page_params)]


def get_field_service(session: DbSession) -> CustomFieldService:
    return CustomFieldService(session)


def get_picklist_service(session: DbSession) -> PicklistService:
    return PicklistService(session)


FieldServiceDep = Annotated[CustomFieldService, Depends(get_field_service)]
PicklistServiceDep = Annotated[PicklistService, Depends(get_picklist_service)]


# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CustomFieldResponse])
async def list_custom_fields(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: FieldServiceDep,
    picklists: PicklistServiceDep,
    entity_type: Annotated[CrmEntityType | None, Query()] = None,
    include_inactive: Annotated[bool, Query()] = True,
) -> list[CustomFieldResponse]:
    """Every custom field definition, optionally narrowed to one record type.

    Unpaginated on purpose. The set is bounded by ``MAX_FIELDS_PER_ENTITY`` and
    every caller — the admin screen, and every record form in the product —
    wants all of it; paginating would make the common case two requests to
    answer a question that has one answer.
    """
    if entity_type is not None:
        definitions = await service.for_entity(
            principal.organization_id, entity_type, include_inactive=include_inactive
        )
    else:
        definitions = await service.all_for_organization(principal.organization_id)
        if not include_inactive:
            definitions = [d for d in definitions if d.is_active]
    return await _with_options(definitions, principal.organization_id, picklists)


@router.get("/schema/{entity_type}", response_model=EntitySchemaResponse)
async def entity_schema(
    entity_type: CrmEntityType,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: FieldServiceDep,
    picklists: PicklistServiceDep,
) -> EntitySchemaResponse:
    """The active fields for one record type, with their options inlined.

    What a record form reads. Inactive fields are excluded — a form must not
    offer a retired field — and each picklist field arrives with its live
    options, so drawing the form is one request rather than one per select.
    """
    definitions = await service.for_entity(
        principal.organization_id, entity_type, include_inactive=False
    )
    return EntitySchemaResponse(
        entity_type=entity_type,
        fields=await _with_options(definitions, principal.organization_id, picklists),
    )


@router.post("", response_model=CustomFieldResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_field(
    payload: CustomFieldCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: FieldServiceDep,
) -> CustomFieldResponse:
    """Define a field. A duplicate API name on the same record type returns 409."""
    definition = await service.create_definition(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return CustomFieldResponse.model_validate(definition)


@router.post("/reorder", response_model=list[CustomFieldResponse])
async def reorder_custom_fields(
    payload: CustomFieldReorder,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: FieldServiceDep,
) -> list[CustomFieldResponse]:
    """Set the display order for one record type's fields."""
    definitions = await service.reorder(
        principal.organization_id,
        payload.entity_type,
        payload.order,
        actor_id=principal.user_id,
    )
    return [CustomFieldResponse.model_validate(definition) for definition in definitions]


@router.get("/{field_id}", response_model=CustomFieldResponse)
async def get_custom_field(
    field_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: FieldServiceDep,
) -> CustomFieldResponse:
    definition = await service.get_or_404(field_id, principal.organization_id)
    return CustomFieldResponse.model_validate(definition)


@router.patch("/{field_id}", response_model=CustomFieldResponse)
async def update_custom_field(
    field_id: uuid.UUID,
    payload: CustomFieldUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: FieldServiceDep,
) -> CustomFieldResponse:
    definition = await service.get_or_404(field_id, principal.organization_id)
    updated = await service.update_definition(
        definition,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return CustomFieldResponse.model_validate(updated)


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_custom_field(
    field_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: FieldServiceDep,
) -> Response:
    """Retire a field. Values already stored under it are left untouched."""
    definition = await service.get_or_404(field_id, principal.organization_id)
    await service.archive_definition(definition, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Picklists
# ---------------------------------------------------------------------------


@picklists_router.get("", response_model=Page[PicklistResponse])
async def list_picklists(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: PicklistServiceDep,
    params: PageParamsDep,
) -> Page[PicklistResponse]:
    """Picklists with their live option counts."""
    items, total = await service.list(principal.organization_id, params=params)
    counts = await service.option_counts(principal.organization_id)
    payload = []
    for item in items:
        response = PicklistResponse.model_validate(item)
        response.option_count = counts.get(item.id, 0)
        payload.append(response)
    return Page.build(payload, total=total, params=params)


@picklists_router.post("", response_model=PicklistResponse, status_code=status.HTTP_201_CREATED)
async def create_picklist(
    payload: PicklistCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: PicklistServiceDep,
) -> PicklistResponse:
    """Create a picklist, optionally with its options in the same transaction."""
    values = payload.model_dump(exclude_unset=True, exclude={"options"})
    picklist = await service.create_picklist(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=values,
    )
    for option in payload.options:
        await service.add_option(
            picklist,
            actor_id=principal.user_id,
            values=option.model_dump(exclude_unset=True),
        )
    return await _picklist_detail(picklist.id, principal.organization_id, service)


@picklists_router.get("/{picklist_id}", response_model=PicklistResponse)
async def get_picklist(
    picklist_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: PicklistServiceDep,
) -> PicklistResponse:
    """One picklist with every option, active and inactive.

    Inactive options are included here, unlike on the schema endpoint: this is
    the administration view, where the whole point is to see and re-activate
    what was retired.
    """
    await service.get_or_404(picklist_id, principal.organization_id)
    return await _picklist_detail(picklist_id, principal.organization_id, service)


@picklists_router.patch("/{picklist_id}", response_model=PicklistResponse)
async def update_picklist(
    picklist_id: uuid.UUID,
    payload: PicklistUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: PicklistServiceDep,
) -> PicklistResponse:
    picklist = await service.get_or_404(picklist_id, principal.organization_id)
    await service.update_picklist(
        picklist, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return await _picklist_detail(picklist_id, principal.organization_id, service)


@picklists_router.delete("/{picklist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_picklist(
    picklist_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: PicklistServiceDep,
) -> Response:
    """Archive a picklist. Blocked while custom fields still draw from it."""
    picklist = await service.get_or_404(picklist_id, principal.organization_id)
    await service.archive_picklist(picklist, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@picklists_router.post(
    "/{picklist_id}/options",
    response_model=PicklistOptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_picklist_option(
    picklist_id: uuid.UUID,
    payload: PicklistOptionCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: PicklistServiceDep,
) -> PicklistOptionResponse:
    """Add an option. Adding to a list is editing it, not creating a resource.

    Hence ``custom_fields.EDIT`` rather than ``CREATE``: the thing being
    changed is the picklist, and a role that may maintain the option sets but
    not define new lists is a coherent one to hold.
    """
    picklist = await service.get_or_404(picklist_id, principal.organization_id)
    option = await service.add_option(
        picklist, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return PicklistOptionResponse.model_validate(option)


@picklists_router.patch("/{picklist_id}/options/{option_id}", response_model=PicklistOptionResponse)
async def update_picklist_option(
    picklist_id: uuid.UUID,
    option_id: uuid.UUID,
    payload: PicklistOptionUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: PicklistServiceDep,
) -> PicklistOptionResponse:
    picklist = await service.get_or_404(picklist_id, principal.organization_id)
    option = await service.get_option_or_404(picklist, option_id)
    updated = await service.update_option(
        picklist,
        option,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return PicklistOptionResponse.model_validate(updated)


@picklists_router.delete(
    "/{picklist_id}/options/{option_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_picklist_option(
    picklist_id: uuid.UUID,
    option_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: PicklistServiceDep,
) -> Response:
    """Remove an option. Records already holding it keep the value."""
    picklist = await service.get_or_404(picklist_id, principal.organization_id)
    option = await service.get_option_or_404(picklist, option_id)
    await service.remove_option(picklist, option, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _picklist_detail(
    picklist_id: uuid.UUID, organization_id: uuid.UUID, service: PicklistService
) -> PicklistResponse:
    picklist = await service.get_or_404(picklist_id, organization_id)
    options = await service.options(organization_id, picklist_id)
    response = PicklistResponse.model_validate(picklist)
    response.options = [PicklistOptionResponse.model_validate(o) for o in options]
    response.option_count = len(options)
    return response


async def _with_options(
    definitions: Sequence[CustomFieldDefinition],
    organization_id: uuid.UUID,
    picklists: PicklistService,
) -> list[CustomFieldResponse]:
    """Attach each picklist field's live options, in one query for all of them.

    The alternative — a query per field — is the N+1 this endpoint would
    otherwise put in front of every record form in the product.
    """
    picklist_ids = sorted({d.picklist_id for d in definitions if d.picklist_id is not None})
    grouped: dict[uuid.UUID, list[PicklistOption]] = {}
    if picklist_ids:
        # `include_inactive=False`: these responses feed forms, and a form must
        # not offer a retired option. The administration view reads the
        # picklist endpoint, which returns all of them.
        options = await picklists.options_for(organization_id, picklist_ids, include_inactive=False)
        for option in options:
            grouped.setdefault(option.picklist_id, []).append(option)

    payload: list[CustomFieldResponse] = []
    for definition in definitions:
        response = CustomFieldResponse.model_validate(definition)
        if definition.picklist_id is not None:
            response.options = [
                PicklistOptionResponse.model_validate(option)
                for option in grouped.get(definition.picklist_id, [])
            ]
        payload.append(response)
    return payload


__all__ = ["picklists_router", "router"]
