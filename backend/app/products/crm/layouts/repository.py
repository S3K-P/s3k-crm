"""Data access for record layouts, their sections, fields and rules."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.common import CrmEntityType
from app.products.crm.layouts.models import (
    LayoutField,
    LayoutFieldRule,
    LayoutSection,
    LayoutStatus,
    LayoutType,
    RecordLayout,
)
from app.products.crm.shared.repository import TenantScopedRepository


class RecordLayoutRepository(TenantScopedRepository[RecordLayout]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RecordLayout)

    async def for_entity(
        self,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
        *,
        layout_type: LayoutType | None = None,
    ) -> Sequence[RecordLayout]:
        statement = self._live(organization_id).where(RecordLayout.entity_type == entity_type)
        if layout_type is not None:
            statement = statement.where(RecordLayout.layout_type == layout_type)
        result = await self._session.execute(statement.order_by(RecordLayout.created_at.asc()))
        return result.scalars().all()

    async def published_for(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType, layout_type: LayoutType
    ) -> RecordLayout | None:
        """The one live layout for this entity type and screen, or ``None``.

        The read every record write consults (via
        :class:`~app.products.crm.custom_fields.service.CustomFieldValueService`)
        when it needs to know whether a conditional rule governs the field
        being validated — so it is a single indexed lookup, not a join across
        every layout.
        """
        result = await self._session.execute(
            self._live(organization_id).where(
                RecordLayout.entity_type == entity_type,
                RecordLayout.layout_type == layout_type,
                RecordLayout.status == LayoutStatus.PUBLISHED,
            )
        )
        return result.scalar_one_or_none()

    async def published_for_with_fallback(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType, layout_type: LayoutType
    ) -> RecordLayout | None:
        """:meth:`published_for`, falling back to the published ``DETAIL`` layout.

        Every ``record_layouts`` row that predates :class:`LayoutType` was
        backfilled as ``DETAIL`` (migration ``20260921_0200``) because that was
        the one layout driving every screen at the time. An organization that
        published a layout before ``CREATE``/``QUICK_CREATE`` existed must see
        no change at all until it deliberately publishes one of its own — so a
        request for either falls back to the ``DETAIL`` layout exactly the way
        it would have resolved before this member was added. A request for
        ``DETAIL`` itself has nothing to fall back to.
        """
        found = await self.published_for(organization_id, entity_type, layout_type)
        if found is not None or layout_type is LayoutType.DETAIL:
            return found
        return await self.published_for(organization_id, entity_type, LayoutType.DETAIL)

    def _live(self, organization_id: uuid.UUID) -> Select[tuple[RecordLayout]]:
        return select(RecordLayout).where(
            RecordLayout.organization_id == organization_id,
            RecordLayout.deleted_at.is_(None),
        )


class LayoutSectionRepository(TenantScopedRepository[LayoutSection]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LayoutSection)

    async def for_layout(
        self, organization_id: uuid.UUID, layout_id: uuid.UUID
    ) -> Sequence[LayoutSection]:
        result = await self._session.execute(
            select(LayoutSection)
            .where(
                LayoutSection.organization_id == organization_id,
                LayoutSection.deleted_at.is_(None),
                LayoutSection.layout_id == layout_id,
            )
            .order_by(LayoutSection.position.asc(), LayoutSection.created_at.asc())
        )
        return result.scalars().all()


class LayoutFieldRepository(TenantScopedRepository[LayoutField]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LayoutField)

    async def for_layout(
        self, organization_id: uuid.UUID, layout_id: uuid.UUID
    ) -> Sequence[LayoutField]:
        result = await self._session.execute(
            select(LayoutField)
            .where(
                LayoutField.organization_id == organization_id,
                LayoutField.deleted_at.is_(None),
                LayoutField.layout_id == layout_id,
            )
            .order_by(LayoutField.position.asc(), LayoutField.created_at.asc())
        )
        return result.scalars().all()

    async def field_key_taken(
        self, layout_id: uuid.UUID, field_key: str, *, excluding: uuid.UUID | None = None
    ) -> bool:
        statement = select(LayoutField.id).where(
            LayoutField.layout_id == layout_id,
            LayoutField.deleted_at.is_(None),
            LayoutField.field_key == field_key,
        )
        if excluding is not None:
            statement = statement.where(LayoutField.id != excluding)
        result = await self._session.execute(statement)
        return result.first() is not None


class LayoutFieldRuleRepository(TenantScopedRepository[LayoutFieldRule]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LayoutFieldRule)

    async def for_layout(
        self, organization_id: uuid.UUID, layout_id: uuid.UUID
    ) -> Sequence[LayoutFieldRule]:
        result = await self._session.execute(
            select(LayoutFieldRule)
            .where(
                LayoutFieldRule.organization_id == organization_id,
                LayoutFieldRule.deleted_at.is_(None),
                LayoutFieldRule.layout_id == layout_id,
            )
            .order_by(LayoutFieldRule.position.asc(), LayoutFieldRule.created_at.asc())
        )
        return result.scalars().all()


__all__ = [
    "LayoutFieldRepository",
    "LayoutFieldRuleRepository",
    "LayoutSectionRepository",
    "RecordLayoutRepository",
]
