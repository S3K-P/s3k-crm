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
    RecordLayout,
)
from app.products.crm.shared.repository import TenantScopedRepository


class RecordLayoutRepository(TenantScopedRepository[RecordLayout]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RecordLayout)

    async def for_entity(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType
    ) -> Sequence[RecordLayout]:
        result = await self._session.execute(
            self._live(organization_id)
            .where(RecordLayout.entity_type == entity_type)
            .order_by(RecordLayout.created_at.asc())
        )
        return result.scalars().all()

    async def published_for(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType
    ) -> RecordLayout | None:
        """The one live layout for this entity type, or ``None``.

        The read every record write consults (via
        :class:`~app.products.crm.custom_fields.service.CustomFieldValueService`)
        when it needs to know whether a conditional rule governs the field
        being validated — so it is a single indexed lookup, not a join across
        every layout.
        """
        result = await self._session.execute(
            self._live(organization_id).where(
                RecordLayout.entity_type == entity_type,
                RecordLayout.status == LayoutStatus.PUBLISHED,
            )
        )
        return result.scalar_one_or_none()

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
