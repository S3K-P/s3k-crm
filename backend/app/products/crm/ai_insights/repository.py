"""Data access for ``ai_generations``.

A hand-written repository rather than :class:`TenantScopedRepository`: that
class requires a ``deleted_at`` column (soft delete), and a generation is
never deleted — it is superseded by a newer row, the same append-only shape
``AiPromptRepository`` already uses for the same reason. Every statement
filters on ``organization_id`` explicitly, the same defence-in-depth rule
every other CRM repository follows.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.ai_insights.models import AiFeature, AiGeneration


class AiGenerationRepository:
    """Reads and writes AI-generated records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, generation: AiGeneration) -> AiGeneration:
        self._session.add(generation)
        await self._session.flush()
        return generation

    async def flush(self) -> None:
        await self._session.flush()

    async def get(
        self, generation_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AiGeneration | None:
        result = await self._session.execute(
            select(AiGeneration).where(
                AiGeneration.id == generation_id,
                AiGeneration.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def latest_for(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        feature: AiFeature,
    ) -> AiGeneration | None:
        """The most recent generation for one record and feature, if any.

        What an "AI panel" on a record shows on load, without calling the
        model — see the module docstring on caching (§15 of the brief).
        """
        result = await self._session.execute(
            select(AiGeneration)
            .where(
                AiGeneration.organization_id == organization_id,
                AiGeneration.entity_type == entity_type,
                AiGeneration.entity_id == entity_id,
                AiGeneration.feature == feature,
            )
            .order_by(AiGeneration.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def history_for(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        feature: AiFeature | None = None,
        limit: int = 20,
    ) -> Sequence[AiGeneration]:
        """Every generation for one record, newest first (§16 AI history)."""
        statement = select(AiGeneration).where(
            AiGeneration.organization_id == organization_id,
            AiGeneration.entity_type == entity_type,
            AiGeneration.entity_id == entity_id,
        )
        if feature is not None:
            statement = statement.where(AiGeneration.feature == feature)
        statement = statement.order_by(AiGeneration.created_at.desc()).limit(limit)
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def recent_by_feature(
        self,
        organization_id: uuid.UUID,
        *,
        feature: AiFeature,
        since: dt.datetime | None = None,
        limit: int = 50,
    ) -> Sequence[AiGeneration]:
        """Recent calls to one feature across every record — an audit view."""
        statement = select(AiGeneration).where(
            AiGeneration.organization_id == organization_id,
            AiGeneration.feature == feature,
        )
        if since is not None:
            statement = statement.where(AiGeneration.created_at >= since)
        statement = statement.order_by(AiGeneration.created_at.desc()).limit(limit)
        result = await self._session.execute(statement)
        return result.scalars().all()


__all__ = ["AiGenerationRepository"]
