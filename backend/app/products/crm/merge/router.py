"""Merge routes, mounted at ``/crm/merge``.

``/crm/merge/{entity}/preview`` and ``/crm/merge/{entity}`` where ``entity`` is
``accounts``, ``contacts`` or ``leads``.

The permission a merge needs is not known when the route is declared — it
depends on the entity in the path — so this router takes the permission
snapshot and decides inside, the shape imports and reports already use. What it
decides is stricter than a normal write: a merge needs ``EDIT`` **and**
``DELETE`` on the entity's module, because it changes one record and retires
others, and a role granted only the first must not acquire the second by
routing through here.

``preview`` needs only ``VIEW`` — it reads and writes nothing — so a rep can be
shown what a merge would do before asking someone who may perform it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from app.core.database import DbSession
from app.core.exceptions import NotFoundError
from app.platform.auth.dependencies import PermissionedPrincipal, Principal
from app.platform.authorization.service import Action as PermissionAction
from app.platform.authorization.service import PermissionDeniedError
from app.products.crm.merge.catalog import MERGE_TARGETS, MergeTarget
from app.products.crm.merge.schemas import (
    MergePreviewRequest,
    MergePreviewResponse,
    MergeRequest,
    MergeResultResponse,
)
from app.products.crm.merge.service import MergeService

router = APIRouter()

#: The path segments this router serves. Declared here so an unknown entity is
#: a 404 from FastAPI's own path validation rather than reaching the handler.
EntitySegment = Annotated[str, Path(pattern="^(accounts|contacts|leads)$")]


def _target(entity: str) -> MergeTarget:
    target = MERGE_TARGETS.get(entity)
    if target is None:  # pragma: no cover - the path pattern already refuses it
        raise NotFoundError("That record type cannot be merged.")
    return target


def _require(principal: Principal, module: str, *actions: PermissionAction) -> None:
    """Assert every action, or refuse.

    Spelled out rather than folded into a route dependency because the module
    is a path parameter. The refusal is the same ``PermissionDeniedError`` the
    ``require_permission`` dependency raises, so a caller cannot tell a
    permission checked here from one checked there.
    """
    for action in actions:
        if not principal.has_permission(module, action):
            raise PermissionDeniedError(f"{module}.{action.value} is required.")


@router.post("/{entity}/preview", response_model=MergePreviewResponse)
async def preview_merge(
    entity: EntitySegment,
    payload: MergePreviewRequest,
    principal: PermissionedPrincipal,
    session: DbSession,
) -> MergePreviewResponse:
    """What a merge would change, without changing anything.

    Needs only ``VIEW`` on the entity's module: it reads. Deliberately takes no
    row locks — a preview that did would let anybody freeze a record by opening
    a dialog and walking away — so the values it reports can be stale by the
    time a merge runs. That is why the merge re-reads under a lock rather than
    trusting anything this returned.
    """
    target = _target(entity)
    _require(principal, target.module, PermissionAction.VIEW)

    service = MergeService(session, target)
    result = await service.preview(
        principal, primary_id=payload.primary_id, duplicate_ids=payload.duplicate_ids
    )
    return MergePreviewResponse.model_validate(result)


@router.post("/{entity}", response_model=MergeResultResponse)
async def merge_records(
    entity: EntitySegment,
    payload: MergeRequest,
    principal: PermissionedPrincipal,
    session: DbSession,
) -> MergeResultResponse:
    """Merge duplicates into the surviving record.

    Needs ``EDIT`` and ``DELETE`` on the entity's module. Everything happens in
    the request's single transaction: references move, then the duplicates are
    retired with a ``merged_into_id`` pointing at the survivor. A failure at any
    point leaves nothing moved and nothing retired.

    A record outside the caller's record-level visibility — including another
    tenant's — is a 404, indistinguishable from one that does not exist.
    """
    target = _target(entity)
    _require(principal, target.module, PermissionAction.EDIT, PermissionAction.DELETE)

    service = MergeService(session, target)
    survivor = await service.merge(
        principal,
        primary_id=payload.primary_id,
        duplicate_ids=payload.duplicate_ids,
        field_choices=payload.field_choices,
    )
    return MergeResultResponse(
        id=survivor.id,
        entity_type=target.entity_type,
        merged_ids=list(payload.duplicate_ids),
    )


__all__ = ["router"]
