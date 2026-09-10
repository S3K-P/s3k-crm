"""Data access for ``crm.saved_views``.

The only layer permitted to construct SQLAlchemy queries against the table.

One read dominates: "which views may this caller see on this record type",
which runs on every list render in the product. It is one statement, and the
visibility rule lives *inside* it rather than being applied to the results
afterwards — a Python filter over a fetched page would return short pages and,
worse, would put another person's private view on the wire before deciding not
to show it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.common import CrmEntityType
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.views.models import SavedView, ViewVisibility


def readable_by(viewer_id: uuid.UUID, peer_ids: frozenset[uuid.UUID]) -> ColumnElement[bool]:
    """The predicate for "views ``viewer_id`` may read".

    Three rungs, widening:

    * anything they own;
    * anything shared with a team they are on — ``TEAM`` visibility, owned by
      one of their peers;
    * anything shared organization-wide.

    ``peer_ids`` empty means "on no team", which correctly leaves the middle
    rung matching nothing rather than matching every ``TEAM`` view. That
    direction matters: an empty peer set must never read as "no restriction",
    which is the same rule ``RecordVisibility`` states for records.
    """
    clauses: list[ColumnElement[bool]] = [
        SavedView.owner_id == viewer_id,
        SavedView.visibility == ViewVisibility.ORGANIZATION,
    ]
    if peer_ids:
        clauses.append(
            (SavedView.visibility == ViewVisibility.TEAM)
            & SavedView.owner_id.in_(set(peer_ids))
        )
    return or_(*clauses)


class SavedViewRepository(TenantScopedRepository[SavedView]):
    """Queries over ``crm.saved_views``."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SavedView)

    async def for_entity(
        self,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
        *,
        visibility: ColumnElement[bool],
    ) -> Sequence[SavedView]:
        """Views on one record type that the caller may read, in display order.

        Ordered so a person's own views come first, then by name. A list
        screen's dropdown is read top-down, and "mine, then everybody's,
        alphabetically" is the order that makes it findable — where ordering
        by creation date puts a colleague's view from last year above the one
        you saved this morning.
        """
        result = await self._session.execute(
            self._live(organization_id)
            .where(SavedView.entity_type == entity_type, visibility)
            .order_by(SavedView.visibility.asc(), SavedView.name.asc())
        )
        return result.scalars().all()

    async def readable(
        self,
        organization_id: uuid.UUID,
        view_id: uuid.UUID,
        *,
        visibility: ColumnElement[bool],
    ) -> SavedView | None:
        """One view, if this caller may read it.

        A view they may not read returns ``None``, which the service turns into
        the same 404 another tenant's id produces — so a prober cannot tell a
        colleague's private view from one that does not exist.
        """
        result = await self._session.execute(
            self._live(organization_id).where(SavedView.id == view_id, visibility)
        )
        return result.scalar_one_or_none()

    async def name_taken(
        self,
        organization_id: uuid.UUID,
        owner_id: uuid.UUID,
        entity_type: CrmEntityType,
        name: str,
        *,
        excluding: uuid.UUID | None = None,
    ) -> bool:
        statement = (
            select(func.count())
            .select_from(SavedView)
            .where(
                SavedView.organization_id == organization_id,
                SavedView.deleted_at.is_(None),
                SavedView.owner_id == owner_id,
                SavedView.entity_type == entity_type,
                func.lower(SavedView.name) == name.lower(),
            )
        )
        if excluding is not None:
            statement = statement.where(SavedView.id != excluding)
        return int((await self._session.execute(statement)).scalar_one()) > 0

    async def count_for_entity(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType
    ) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(SavedView)
            .where(
                SavedView.organization_id == organization_id,
                SavedView.deleted_at.is_(None),
                SavedView.entity_type == entity_type,
            )
        )
        return int(result.scalar_one())

    async def clear_default(
        self,
        organization_id: uuid.UUID,
        owner_id: uuid.UUID,
        entity_type: CrmEntityType,
        *,
        excluding: uuid.UUID,
    ) -> None:
        """Demote this person's current default on this record type, if any.

        A direct UPDATE rather than mutated ORM instances, and for the reason
        the picklist default is: the partial unique index refuses two defaults
        even inside a transaction, and SQLAlchemy's unit of work orders INSERTs
        before UPDATEs — so an ORM demotion queued alongside a new default row
        would be applied second and the insert would collide.

        Scoped to ``owner_id``: a default is a personal preference, and
        promoting one must not silently demote a colleague's.
        """
        await self._session.execute(
            update(SavedView)
            .where(
                SavedView.organization_id == organization_id,
                SavedView.deleted_at.is_(None),
                SavedView.owner_id == owner_id,
                SavedView.entity_type == entity_type,
                SavedView.is_default.is_(True),
                SavedView.id != excluding,
            )
            .values(is_default=False)
            .execution_options(synchronize_session="fetch")
        )

    def _live(self, organization_id: uuid.UUID) -> Select[tuple[SavedView]]:
        return select(SavedView).where(
            SavedView.organization_id == organization_id,
            SavedView.deleted_at.is_(None),
        )


__all__ = ["SavedViewRepository", "readable_by"]
