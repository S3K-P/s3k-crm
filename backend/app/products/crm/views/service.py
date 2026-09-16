"""Business rules for saved list views (Phase F).

Four rules, and the second and third are the ones with teeth:

1. A name is unique per person per record type — not per organization, so two
   reps may each have their own "My hot leads".
2. **Reading a view is decided by its visibility**, resolved into SQL in the
   repository, so a colleague's private view is a 404 and not a shorter page.
3. **Changing a view needs ownership**, or ``views.VIEW_ALL`` — the same grant
   that lets a manager reach across owners everywhere else in the product. A
   view shared with the organization is readable by everyone and editable by
   nobody but its owner and a manager, which is what stops "shared" quietly
   meaning "communal".
4. A default is per person, so promoting one demotes only your own.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.common import CrmEntityType
from app.products.crm.reports.conditions import ReportFilterGroup
from app.products.crm.reports.custom import validate_builtin_filter_group
from app.products.crm.reports.fields import REPORT_ENTITY_FOR_CRM_ENTITY_TYPE
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.views.models import MAX_VIEWS_PER_ENTITY, SavedView, ViewVisibility
from app.products.crm.views.repository import SavedViewRepository, readable_by

MODULE = "views"


class DuplicateViewNameError(ConflictError):
    code = "duplicate_view_name"
    message = "You already have a view with that name on this record type."


class ViewLimitReachedError(ConflictError):
    code = "view_limit_reached"
    message = f"A record type may have at most {MAX_VIEWS_PER_ENTITY} saved views."


class ViewNotEditableError(NotFoundError):
    """Someone else's view, and the caller is not a manager.

    A 404 rather than a 403, and deliberately the same one an unknown id
    produces: a private view the caller may not read must not become visible
    through the *error* of trying to edit it.
    """

    code = "not_found"
    message = "View not found."


class SavedViewService(TenantScopedService[SavedView]):
    """Saved list views, scoped to one organization and one reader."""

    entity_name = "View"

    def __init__(self, session: AsyncSession) -> None:
        self._views = SavedViewRepository(session)
        super().__init__(self._views, SavedView)
        self._session = session

    @property
    def audit_module(self) -> str:
        # The table is `saved_views`; the permission module is `views`, and the
        # trail is filtered by the permission vocabulary.
        return MODULE

    def audit_label(self, entity: SavedView) -> str | None:
        # A name alone is ambiguous across record types — three entities may
        # each have a "Recently created".
        return f"{entity.entity_type.value}: {entity.name}"

    # --- Reads -------------------------------------------------------------

    async def list_for_entity(
        self, principal: Principal, entity_type: CrmEntityType
    ) -> Sequence[SavedView]:
        """Views on ``entity_type`` this caller may read."""
        return await self._views.for_entity(
            principal.organization_id,
            entity_type,
            visibility=readable_by(principal.user_id, principal.team_peer_ids),
        )

    async def get_readable(self, principal: Principal, view_id: uuid.UUID) -> SavedView:
        """One view this caller may read, or 404."""
        view = await self._views.readable(
            principal.organization_id,
            view_id,
            visibility=readable_by(principal.user_id, principal.team_peer_ids),
        )
        if view is None:
            raise NotFoundError("View not found.")
        return view

    async def get_editable(self, principal: Principal, view_id: uuid.UUID) -> SavedView:
        """One view this caller may change, or 404.

        Resolved through :meth:`get_readable` first, so a view they cannot even
        see produces the same answer as one that does not exist, and only then
        narrowed to ownership. Doing it the other way round — checking
        ownership against a directly fetched row — would let a caller confirm a
        colleague's view id by the difference between 403 and 404.
        """
        view = await self.get_readable(principal, view_id)
        if not self.may_edit(principal, view):
            raise ViewNotEditableError
        return view

    @staticmethod
    def may_edit(principal: Principal, view: SavedView) -> bool:
        """Whether ``principal`` may change ``view``.

        Its owner always may. Anyone else needs ``views.VIEW_ALL`` — reusing
        the manager grant rather than inventing a ``views.MANAGE`` nobody would
        think to grant. Surfaced on the response so the UI can hide an edit
        button it would otherwise offer and then fail.
        """
        return view.owner_id == principal.user_id or principal.has_permission(
            MODULE, PermissionAction.VIEW_ALL
        )

    # --- Writes ------------------------------------------------------------

    async def create_view(
        self, principal: Principal, *, values: Mapping[str, Any]
    ) -> SavedView:
        """Save a view owned by the caller.

        ``owner_id`` is taken from the principal and any value in the body is
        discarded: a client that could name another owner could plant a view in
        a colleague's list, and — through ``is_default`` — change which one
        their list screen opens with.
        """
        entity_type = CrmEntityType(str(values["entity_type"]))
        name = str(values["name"]).strip()

        if await self._views.name_taken(
            principal.organization_id, principal.user_id, entity_type, name
        ):
            raise DuplicateViewNameError
        if (
            await self._views.count_for_entity(principal.organization_id, entity_type)
            >= MAX_VIEWS_PER_ENTITY
        ):
            raise ViewLimitReachedError

        payload = dict(values, name=name, entity_type=entity_type)
        payload["owner_id"] = principal.user_id

        wants_default = bool(payload.get("is_default"))
        if wants_default:
            # Demoted before the insert reaches the database: the partial
            # unique index does not tolerate two defaults even momentarily.
            await self._views.clear_default(
                principal.organization_id,
                principal.user_id,
                entity_type,
                excluding=uuid.UUID(int=0),
            )

        return await self.create(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            values=payload,
        )

    async def update_view(
        self, principal: Principal, view: SavedView, *, values: Mapping[str, Any]
    ) -> SavedView:
        """Patch a view the caller has already been authorized to change."""
        payload = dict(values)
        # Neither is patchable. Moving a view to another record type would
        # leave its filters naming columns that entity does not have; changing
        # its owner would hand a colleague a view they never made and, through
        # `is_default`, change what their list screen opens with.
        payload.pop("entity_type", None)
        payload.pop("owner_id", None)

        if "advanced_filter" in payload and payload["advanced_filter"] is not None:
            # Re-parsed rather than trusted as a plain dict: `values` arrives
            # from `SavedViewUpdate.model_dump()`, which has already flattened
            # the nested `ReportFilterGroup` model — this is the first point
            # `view.entity_type` (only known once the row is loaded) is
            # available to validate a *changed* advanced filter against, per
            # `SavedViewUpdate`'s own docstring. `ValidationFailedError` (not
            # a plain `ValueError`) is right here: unlike the Pydantic
            # validators in `views.schemas`, this runs as ordinary service
            # code, where an `AppError` is what the global handler turns into
            # a 422 — a bare `ValueError` here would surface as a 500.
            group = ReportFilterGroup.model_validate(payload["advanced_filter"])
            report_entity = REPORT_ENTITY_FOR_CRM_ENTITY_TYPE.get(view.entity_type)
            if report_entity is None:
                msg = f"Advanced filters are not available for {view.entity_type.value.title()}."
                raise ValidationFailedError(msg)
            validate_builtin_filter_group(report_entity, group)
            payload["advanced_filter"] = group.model_dump(mode="json")

        new_name = payload.get("name")
        if new_name is not None:
            new_name = str(new_name).strip()
            payload["name"] = new_name
            if new_name.lower() != view.name.lower() and await self._views.name_taken(
                view.organization_id,
                view.owner_id,
                view.entity_type,
                new_name,
                excluding=view.id,
            ):
                raise DuplicateViewNameError

        if payload.get("is_default"):
            # Scoped to the view's *owner*, not the caller: a manager marking
            # somebody's view default sets it for that person, and must not
            # demote one of their own on the way past.
            await self._views.clear_default(
                view.organization_id,
                view.owner_id,
                view.entity_type,
                excluding=view.id,
            )

        return await self.update(view, actor_id=principal.user_id, values=payload)

    async def delete_view(self, principal: Principal, view: SavedView) -> SavedView:
        """Soft-delete a view. Nothing it pointed at is touched.

        Worth stating because "delete view" reads alarming beside a list of
        records: a view holds no rows, so removing one removes a saved
        question and nothing else.
        """
        return await self.soft_delete(view, actor_id=principal.user_id)


__all__ = [
    "MODULE",
    "DuplicateViewNameError",
    "SavedViewService",
    "ViewLimitReachedError",
    "ViewNotEditableError",
    "ViewVisibility",
]
