"""Data access for custom field definitions, picklists and their options.

The only layer permitted to construct SQLAlchemy queries against
``crm.custom_field_definitions``, ``crm.picklists`` and
``crm.picklist_options``.

Three reads dominate: "every definition for this entity type" runs on every
create and update of a record, "every option in these picklists" runs beside
it, and "the whole configuration" renders the admin screen. All three are
written here as one statement each, because a per-field or per-list query would
put an N+1 on the write path of every record in the product.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.common import CrmEntityType
from app.products.crm.custom_fields.models import (
    CustomFieldDefinition,
    Picklist,
    PicklistOption,
)
from app.products.crm.shared.repository import TenantScopedRepository


class CustomFieldDefinitionRepository(TenantScopedRepository[CustomFieldDefinition]):
    """Queries over ``crm.custom_field_definitions``."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CustomFieldDefinition)

    async def for_entity(
        self,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
        *,
        include_inactive: bool = True,
    ) -> Sequence[CustomFieldDefinition]:
        """Every live definition on ``entity_type``, in display order.

        ``include_inactive`` defaults to True because both callers that matter
        need the inactive ones: the admin screen lists them, and the record
        write path has to know that a value it is being asked to store belongs
        to a field that exists but is retired — which is a different answer
        from "no such field".

        Ordered by ``(position, created_at)`` rather than ``position`` alone so
        two fields sharing a position have a stable order across page loads
        instead of whatever the planner returned last.
        """
        statement = self._live(organization_id).where(
            CustomFieldDefinition.entity_type == entity_type
        )
        if not include_inactive:
            statement = statement.where(CustomFieldDefinition.is_active.is_(True))
        result = await self._session.execute(
            statement.order_by(
                CustomFieldDefinition.position.asc(), CustomFieldDefinition.created_at.asc()
            )
        )
        return result.scalars().all()

    async def all_for_organization(
        self, organization_id: uuid.UUID
    ) -> Sequence[CustomFieldDefinition]:
        """Every live definition across every entity type, in display order."""
        result = await self._session.execute(
            self._live(organization_id).order_by(
                CustomFieldDefinition.entity_type.asc(),
                CustomFieldDefinition.position.asc(),
                CustomFieldDefinition.created_at.asc(),
            )
        )
        return result.scalars().all()

    async def api_name_taken(
        self,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
        api_name: str,
    ) -> bool:
        """Whether a live definition already claims ``api_name`` on this entity."""
        result = await self._session.execute(
            select(func.count())
            .select_from(CustomFieldDefinition)
            .where(
                CustomFieldDefinition.organization_id == organization_id,
                CustomFieldDefinition.deleted_at.is_(None),
                CustomFieldDefinition.entity_type == entity_type,
                func.lower(CustomFieldDefinition.api_name) == api_name.lower(),
            )
        )
        return int(result.scalar_one()) > 0

    async def count_for_entity(self, organization_id: uuid.UUID, entity_type: CrmEntityType) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(CustomFieldDefinition)
            .where(
                CustomFieldDefinition.organization_id == organization_id,
                CustomFieldDefinition.deleted_at.is_(None),
                CustomFieldDefinition.entity_type == entity_type,
            )
        )
        return int(result.scalar_one())

    async def using_picklist(
        self, organization_id: uuid.UUID, picklist_id: uuid.UUID
    ) -> Sequence[CustomFieldDefinition]:
        """Live definitions that draw their options from ``picklist_id``.

        Read before a picklist is archived, so the refusal can name the fields
        that would break rather than reporting an opaque foreign-key error.
        """
        result = await self._session.execute(
            self._live(organization_id).where(CustomFieldDefinition.picklist_id == picklist_id)
        )
        return result.scalars().all()

    def _live(self, organization_id: uuid.UUID) -> Select[tuple[CustomFieldDefinition]]:
        return select(CustomFieldDefinition).where(
            CustomFieldDefinition.organization_id == organization_id,
            CustomFieldDefinition.deleted_at.is_(None),
        )


class PicklistRepository(TenantScopedRepository[Picklist]):
    """Queries over ``crm.picklists`` and, because it owns them, its options."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Picklist)

    async def by_api_name(self, organization_id: uuid.UUID, api_name: str) -> Picklist | None:
        result = await self._session.execute(
            select(Picklist).where(
                Picklist.organization_id == organization_id,
                Picklist.deleted_at.is_(None),
                func.lower(Picklist.api_name) == api_name.lower(),
            )
        )
        return result.scalar_one_or_none()

    async def options(
        self,
        organization_id: uuid.UUID,
        picklist_id: uuid.UUID,
        *,
        include_inactive: bool = True,
    ) -> Sequence[PicklistOption]:
        """Options of one list, in display order."""
        return await self.options_for(
            organization_id, [picklist_id], include_inactive=include_inactive
        )

    async def options_for(
        self,
        organization_id: uuid.UUID,
        picklist_ids: Sequence[uuid.UUID],
        *,
        include_inactive: bool = True,
    ) -> Sequence[PicklistOption]:
        """Options of several lists in one query.

        The plural form is the one the record write path uses: a record type
        with six picklist fields would otherwise issue six queries before it
        could validate a single write.
        """
        if not picklist_ids:
            return []
        statement = select(PicklistOption).where(
            PicklistOption.organization_id == organization_id,
            PicklistOption.deleted_at.is_(None),
            PicklistOption.picklist_id.in_(list(picklist_ids)),
        )
        if not include_inactive:
            statement = statement.where(PicklistOption.is_active.is_(True))
        result = await self._session.execute(
            statement.order_by(
                PicklistOption.picklist_id.asc(),
                PicklistOption.position.asc(),
                PicklistOption.created_at.asc(),
            )
        )
        return result.scalars().all()

    async def get_option(
        self, organization_id: uuid.UUID, option_id: uuid.UUID
    ) -> PicklistOption | None:
        """One option, scoped to the organization.

        Scoped even though the caller has already resolved the parent list:
        the id arrives from the URL, and resolving it through the tenant filter
        is what makes a guessed identifier from another tenant a 404 rather
        than an edit.
        """
        result = await self._session.execute(
            select(PicklistOption).where(
                PicklistOption.organization_id == organization_id,
                PicklistOption.deleted_at.is_(None),
                PicklistOption.id == option_id,
            )
        )
        return result.scalar_one_or_none()

    async def option_value_taken(
        self, picklist_id: uuid.UUID, value: str, *, excluding: uuid.UUID | None = None
    ) -> bool:
        statement = (
            select(func.count())
            .select_from(PicklistOption)
            .where(
                PicklistOption.picklist_id == picklist_id,
                PicklistOption.deleted_at.is_(None),
                func.lower(PicklistOption.value) == value.lower(),
            )
        )
        if excluding is not None:
            statement = statement.where(PicklistOption.id != excluding)
        result = await self._session.execute(statement)
        return int(result.scalar_one()) > 0

    async def count_options(self, picklist_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(PicklistOption)
            .where(
                PicklistOption.picklist_id == picklist_id,
                PicklistOption.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def option_counts(self, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Live option count per list, keyed by list id.

        One grouped query for the whole page: the admin list shows this against
        every row, and asking per row would be a classic N+1.
        """
        result = await self._session.execute(
            select(PicklistOption.picklist_id, func.count())
            .where(
                PicklistOption.organization_id == organization_id,
                PicklistOption.deleted_at.is_(None),
            )
            .group_by(PicklistOption.picklist_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def clear_default(self, picklist_id: uuid.UUID, *, excluding: uuid.UUID) -> None:
        """Demote whichever option currently claims the default, if any.

        Issued as a direct UPDATE rather than by mutating ORM instances, and
        that is load-bearing rather than a style choice. The partial unique
        index refuses two defaults *within* a transaction, and SQLAlchemy's
        unit of work orders INSERTs before UPDATEs at flush time — so an ORM
        demotion queued alongside a new default row would be applied second and
        the insert would collide. Executing the UPDATE here puts the demotion
        on the wire before the caller flushes the promotion.

        The pair is still atomic in effect: both are in one transaction, so if
        either fails neither lands and the list can never end up with two
        defaults, or with none it did not ask for.

        ``synchronize_session="fetch"`` so instances the caller is already
        holding — the option it just read, in particular — do not keep
        reporting the stale ``is_default`` they had before this ran.
        """
        await self._session.execute(
            update(PicklistOption)
            .where(
                PicklistOption.picklist_id == picklist_id,
                PicklistOption.deleted_at.is_(None),
                PicklistOption.is_default.is_(True),
                PicklistOption.id != excluding,
            )
            .values(is_default=False)
            .execution_options(synchronize_session="fetch")
        )


__all__ = ["CustomFieldDefinitionRepository", "PicklistRepository"]
