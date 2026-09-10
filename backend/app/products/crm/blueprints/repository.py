"""Data access for ``crm.blueprints`` and ``crm.blueprint_transitions``.

The only layer permitted to construct SQLAlchemy queries against either.

One read is on a hot path and shapes the whole module: "the active blueprint
for this field, with its transitions", which runs on every state change of
every governed record. It is two statements — the blueprint, then its
transitions — and never one per transition.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.blueprints.models import (
    Blueprint,
    BlueprintField,
    BlueprintTransition,
)
from app.products.crm.shared.repository import TenantScopedRepository


class BlueprintRepository(TenantScopedRepository[Blueprint]):
    """Queries over ``crm.blueprints`` and, because it owns them, its transitions."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Blueprint)

    async def active_for_field(
        self, organization_id: uuid.UUID, field: BlueprintField
    ) -> Blueprint | None:
        """The one active blueprint governing ``field``, if any.

        ``scalar_one_or_none`` rather than ``first``: the partial unique index
        guarantees at most one, and if that guarantee ever broke this would
        raise instead of silently picking whichever row the planner returned —
        which is the failure mode that makes a process rule appear to work for
        some records and not others.
        """
        result = await self._session.execute(
            self._live(organization_id).where(
                Blueprint.field == field, Blueprint.is_active.is_(True)
            )
        )
        return result.scalar_one_or_none()

    async def all_for_organization(self, organization_id: uuid.UUID) -> Sequence[Blueprint]:
        result = await self._session.execute(
            self._live(organization_id).order_by(
                Blueprint.field.asc(), Blueprint.name.asc()
            )
        )
        return result.scalars().all()

    async def name_taken(
        self,
        organization_id: uuid.UUID,
        name: str,
        *,
        excluding: uuid.UUID | None = None,
    ) -> bool:
        statement = (
            select(func.count())
            .select_from(Blueprint)
            .where(
                Blueprint.organization_id == organization_id,
                Blueprint.deleted_at.is_(None),
                func.lower(Blueprint.name) == name.lower(),
            )
        )
        if excluding is not None:
            statement = statement.where(Blueprint.id != excluding)
        return int((await self._session.execute(statement)).scalar_one()) > 0

    async def active_for_field_exists(
        self, organization_id: uuid.UUID, field: BlueprintField, *, excluding: uuid.UUID
    ) -> bool:
        """Whether another blueprint already governs ``field``.

        Checked before activation so the caller gets a 409 naming the conflict
        rather than an integrity error from the partial unique index.
        """
        result = await self._session.execute(
            select(func.count())
            .select_from(Blueprint)
            .where(
                Blueprint.organization_id == organization_id,
                Blueprint.deleted_at.is_(None),
                Blueprint.field == field,
                Blueprint.is_active.is_(True),
                Blueprint.id != excluding,
            )
        )
        return int(result.scalar_one()) > 0

    # --- Transitions -------------------------------------------------------

    async def transitions(
        self, organization_id: uuid.UUID, blueprint_id: uuid.UUID
    ) -> Sequence[BlueprintTransition]:
        """Every live transition of one blueprint, in display order."""
        result = await self._session.execute(
            select(BlueprintTransition)
            .where(
                BlueprintTransition.organization_id == organization_id,
                BlueprintTransition.deleted_at.is_(None),
                BlueprintTransition.blueprint_id == blueprint_id,
            )
            .order_by(
                BlueprintTransition.position.asc(), BlueprintTransition.created_at.asc()
            )
        )
        return result.scalars().all()

    async def transition_counts(self, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Live transition count per blueprint, keyed by blueprint id.

        One grouped query for the whole page: the configuration list shows this
        against every row, and asking per row would be a classic N+1.
        """
        result = await self._session.execute(
            select(BlueprintTransition.blueprint_id, func.count())
            .where(
                BlueprintTransition.organization_id == organization_id,
                BlueprintTransition.deleted_at.is_(None),
            )
            .group_by(BlueprintTransition.blueprint_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def get_transition(
        self, organization_id: uuid.UUID, transition_id: uuid.UUID
    ) -> BlueprintTransition | None:
        result = await self._session.execute(
            select(BlueprintTransition).where(
                BlueprintTransition.organization_id == organization_id,
                BlueprintTransition.deleted_at.is_(None),
                BlueprintTransition.id == transition_id,
            )
        )
        return result.scalar_one_or_none()

    async def transition_exists(
        self,
        blueprint_id: uuid.UUID,
        from_state: str,
        to_state: str,
        *,
        excluding: uuid.UUID | None = None,
    ) -> bool:
        statement = (
            select(func.count())
            .select_from(BlueprintTransition)
            .where(
                BlueprintTransition.blueprint_id == blueprint_id,
                BlueprintTransition.deleted_at.is_(None),
                BlueprintTransition.from_state == from_state,
                BlueprintTransition.to_state == to_state,
            )
        )
        if excluding is not None:
            statement = statement.where(BlueprintTransition.id != excluding)
        return int((await self._session.execute(statement)).scalar_one()) > 0

    async def count_transitions(self, blueprint_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(BlueprintTransition)
            .where(
                BlueprintTransition.blueprint_id == blueprint_id,
                BlueprintTransition.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    def _live(self, organization_id: uuid.UUID) -> Select[tuple[Blueprint]]:
        return select(Blueprint).where(
            Blueprint.organization_id == organization_id,
            Blueprint.deleted_at.is_(None),
        )


__all__ = ["BlueprintRepository"]
