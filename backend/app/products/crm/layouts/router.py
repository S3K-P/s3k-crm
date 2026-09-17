"""Record layout / form builder routes.

Configuring a layout is administration in the same strength blueprints are
(``authorization/catalog.py``): it decides what every rep's form looks like
and, through conditional rules, what is required of them. So mutation stays
behind ``record_layouts.EDIT``/``CREATE``/``DELETE`` — Admin-only by the system
role templates — while every role holds ``record_layouts.VIEW``: a rep's own
create/edit form has to be able to fetch the published layout it renders
against, and a rule that hid a field has to be visible to whoever is filling
the rest of the form in.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.database import DbSession
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.common import CrmEntityType
from app.products.crm.layouts.models import LayoutType, RecordLayout
from app.products.crm.layouts.schemas import (
    AvailableFieldInfo,
    EvaluateFieldStatesRequest,
    EvaluateFieldStatesResponse,
    FieldStateResponse,
    LayoutFieldCreate,
    LayoutFieldResponse,
    LayoutFieldRuleCreate,
    LayoutFieldRuleResponse,
    LayoutFieldRuleUpdate,
    LayoutFieldUpdate,
    LayoutReorderRequest,
    LayoutSectionCreate,
    LayoutSectionResponse,
    LayoutSectionUpdate,
    RecordLayoutCreate,
    RecordLayoutDetailResponse,
    RecordLayoutResponse,
    RecordLayoutUpdate,
)
from app.products.crm.layouts.service import LayoutService

router = APIRouter()

MODULE = "record_layouts"


def get_service(session: DbSession) -> LayoutService:
    return LayoutService(session)


ServiceDep = Annotated[LayoutService, Depends(get_service)]


async def _layout_or_404(
    service: LayoutService, layout_id: uuid.UUID, principal: Principal
) -> RecordLayout:
    return await service.get_or_404(layout_id, principal.organization_id)


async def _detail(service: LayoutService, layout: RecordLayout) -> RecordLayoutDetailResponse:
    sections = []
    for section, fields in await service.sections_with_fields(layout):
        sections.append(
            LayoutSectionResponse(
                id=section.id,
                layout_id=section.layout_id,
                name=section.name,
                position=section.position,
                columns=section.columns,
                fields=[LayoutFieldResponse.model_validate(field) for field in fields],
            )
        )
    rules = [
        LayoutFieldRuleResponse.model_validate(rule) for rule in await service.rules_for(layout)
    ]
    return RecordLayoutDetailResponse(
        **RecordLayoutResponse.model_validate(layout).model_dump(),
        sections=sections,
        rules=rules,
    )


@router.get("", response_model=list[RecordLayoutResponse])
async def list_layouts(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    entity_type: Annotated[CrmEntityType, Query()],
    layout_type: Annotated[LayoutType | None, Query()] = None,
) -> list[RecordLayoutResponse]:
    layouts = await service.list_for_entity(
        principal.organization_id, entity_type, layout_type=layout_type
    )
    return [RecordLayoutResponse.model_validate(layout) for layout in layouts]


@router.get("/published", response_model=RecordLayoutDetailResponse | None)
async def get_published_layout(
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
    entity_type: Annotated[CrmEntityType, Query()],
    layout_type: Annotated[LayoutType, Query()] = LayoutType.DETAIL,
) -> RecordLayoutDetailResponse | None:
    """The live layout a form for ``entity_type``/``layout_type`` should render.

    ``None`` (not 404) when no layout has been published — every entity type
    is fully usable with no layout at all, since forms fall back to their
    existing hardcoded rendering. This is what lets the feature be adopted
    incrementally, one entity type at a time.

    A request for ``CREATE`` or ``QUICK_CREATE`` falls back to the published
    ``DETAIL`` layout when neither has one of its own — see
    :meth:`~app.products.crm.layouts.service.LayoutService.get_published`.
    """
    published = await service.get_published(principal.organization_id, entity_type, layout_type)
    if published is None:
        return None
    return await _detail(service, published)


@router.get("/{layout_id}", response_model=RecordLayoutDetailResponse)
async def get_layout(
    layout_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> RecordLayoutDetailResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    return await _detail(service, layout)


@router.get("/{layout_id}/available-fields", response_model=list[AvailableFieldInfo])
async def list_available_fields(
    layout_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> list[AvailableFieldInfo]:
    layout = await _layout_or_404(service, layout_id, principal)
    return [
        AvailableFieldInfo(
            field_key=key,
            label=label,
            is_custom=is_custom,
            is_required_base=is_required,
            placed=placed,
        )
        for key, label, is_custom, is_required, placed in await service.available_fields(layout)
    ]


@router.post("", response_model=RecordLayoutResponse, status_code=status.HTTP_201_CREATED)
async def create_layout(
    payload: RecordLayoutCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))],
    service: ServiceDep,
) -> RecordLayoutResponse:
    layout = await service.create_layout(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(),
    )
    return RecordLayoutResponse.model_validate(layout)


@router.patch("/{layout_id}", response_model=RecordLayoutResponse)
async def update_layout(
    layout_id: uuid.UUID,
    payload: RecordLayoutUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> RecordLayoutResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    updated = await service.update(
        layout, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return RecordLayoutResponse.model_validate(updated)


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_layout(
    layout_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))],
    service: ServiceDep,
) -> Response:
    layout = await _layout_or_404(service, layout_id, principal)
    await service.archive_layout(layout, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{layout_id}/publish", response_model=RecordLayoutDetailResponse)
async def publish_layout(
    layout_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> RecordLayoutDetailResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    published = await service.publish(layout, actor_id=principal.user_id)
    return await _detail(service, published)


@router.post("/{layout_id}/unpublish", response_model=RecordLayoutResponse)
async def unpublish_layout(
    layout_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> RecordLayoutResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    updated = await service.unpublish(layout, actor_id=principal.user_id)
    return RecordLayoutResponse.model_validate(updated)


@router.post("/{layout_id}/evaluate", response_model=EvaluateFieldStatesResponse)
async def evaluate_layout(
    layout_id: uuid.UUID,
    payload: EvaluateFieldStatesRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))],
    service: ServiceDep,
) -> EvaluateFieldStatesResponse:
    """Live preview: which custom fields are visible/required for these values.

    Never authoritative on its own — the same evaluation runs again,
    server-side, inside the entity's own create/update when the form is
    actually submitted (:class:`~app.products.crm.custom_fields.service.CustomFieldValueService`).
    This endpoint exists so the builder's preview and a form's live "as you
    type" behaviour do not have to reimplement :mod:`.evaluate` in the
    browser from scratch — though the frontend also carries its own mirrored
    copy for a render that reacts with no network round trip; see
    ``frontend/features/crm/layouts/evaluate.ts``.
    """
    layout = await _layout_or_404(service, layout_id, principal)
    states = await service.evaluate_states(layout, payload.values)
    return EvaluateFieldStatesResponse(
        states={
            key: FieldStateResponse(visible=state.visible, required=state.required)
            for key, state in states.items()
        }
    )


# --- Sections ----------------------------------------------------------


@router.post(
    "/{layout_id}/sections",
    response_model=LayoutSectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_section(
    layout_id: uuid.UUID,
    payload: LayoutSectionCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LayoutSectionResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    section = await service.add_section(
        layout, actor_id=principal.user_id, values=payload.model_dump()
    )
    return LayoutSectionResponse(
        id=section.id,
        layout_id=section.layout_id,
        name=section.name,
        position=section.position,
        columns=section.columns,
        fields=[],
    )


@router.patch("/{layout_id}/sections/{section_id}", response_model=LayoutSectionResponse)
async def update_section(
    layout_id: uuid.UUID,
    section_id: uuid.UUID,
    payload: LayoutSectionUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LayoutSectionResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    section = await service.get_section_or_404(layout, section_id)
    updated = await service.update_section(
        section, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    fields = await service.fields_in_section(updated)
    return LayoutSectionResponse(
        id=updated.id,
        layout_id=updated.layout_id,
        name=updated.name,
        position=updated.position,
        columns=updated.columns,
        fields=[LayoutFieldResponse.model_validate(field) for field in fields],
    )


@router.delete("/{layout_id}/sections/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_section(
    layout_id: uuid.UUID,
    section_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> Response:
    layout = await _layout_or_404(service, layout_id, principal)
    section = await service.get_section_or_404(layout, section_id)
    await service.remove_section(section, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Fields --------------------------------------------------------------


@router.post(
    "/{layout_id}/fields", response_model=LayoutFieldResponse, status_code=status.HTTP_201_CREATED
)
async def add_field(
    layout_id: uuid.UUID,
    payload: LayoutFieldCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LayoutFieldResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    field = await service.add_field(
        layout, actor_id=principal.user_id, values=payload.model_dump()
    )
    return LayoutFieldResponse.model_validate(field)


@router.patch("/{layout_id}/fields/{field_id}", response_model=LayoutFieldResponse)
async def update_field(
    layout_id: uuid.UUID,
    field_id: uuid.UUID,
    payload: LayoutFieldUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LayoutFieldResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    field = await service.get_field_or_404(layout, field_id)
    updated = await service.update_field(
        field, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return LayoutFieldResponse.model_validate(updated)


@router.delete("/{layout_id}/fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_field(
    layout_id: uuid.UUID,
    field_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> Response:
    layout = await _layout_or_404(service, layout_id, principal)
    field = await service.get_field_or_404(layout, field_id)
    await service.remove_field(field, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{layout_id}/fields/reorder", response_model=list[LayoutFieldResponse])
async def reorder_fields(
    layout_id: uuid.UUID,
    payload: LayoutReorderRequest,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> list[LayoutFieldResponse]:
    """Persist a drag-and-drop's complete new arrangement.

    This is what makes the builder's drag-and-drop real rather than
    cosmetic: the frontend reorders its local state immediately for
    responsiveness, then calls this in the same interaction, and a page
    refresh reflects the same arrangement because it is now the arrangement
    the database holds.
    """
    layout = await _layout_or_404(service, layout_id, principal)
    fields = await service.reorder_fields(
        layout,
        actor_id=principal.user_id,
        entries=[entry.model_dump() for entry in payload.fields],
    )
    return [LayoutFieldResponse.model_validate(field) for field in fields]


# --- Rules -----------------------------------------------------------------


@router.post(
    "/{layout_id}/rules",
    response_model=LayoutFieldRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_rule(
    layout_id: uuid.UUID,
    payload: LayoutFieldRuleCreate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LayoutFieldRuleResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    rule = await service.add_rule(layout, actor_id=principal.user_id, values=payload.model_dump())
    return LayoutFieldRuleResponse.model_validate(rule)


@router.patch("/{layout_id}/rules/{rule_id}", response_model=LayoutFieldRuleResponse)
async def update_rule(
    layout_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: LayoutFieldRuleUpdate,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> LayoutFieldRuleResponse:
    layout = await _layout_or_404(service, layout_id, principal)
    rule = await service.get_rule_or_404(layout, rule_id)
    updated = await service.update_rule(
        rule, actor_id=principal.user_id, values=payload.model_dump(exclude_unset=True)
    )
    return LayoutFieldRuleResponse.model_validate(updated)


@router.delete("/{layout_id}/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_rule(
    layout_id: uuid.UUID,
    rule_id: uuid.UUID,
    principal: Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))],
    service: ServiceDep,
) -> Response:
    layout = await _layout_or_404(service, layout_id, principal)
    rule = await service.get_rule_or_404(layout, rule_id)
    await service.remove_rule(rule, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
