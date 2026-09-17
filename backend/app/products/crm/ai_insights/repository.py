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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.ai_insights.models import AiFeature, AiGeneration, NbaActionLog, NbaRule
from app.products.crm.shared.repository import TenantScopedRepository


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

    async def latest_for_many(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: str,
        entity_ids: Sequence[uuid.UUID],
        feature: AiFeature,
    ) -> dict[uuid.UUID, AiGeneration]:
        """``latest_for`` over many records of one type, in one query.

        For a screen listing many records' cached results at once — the Next
        Best Action queue — rather than one query per row. PostgreSQL's
        ``DISTINCT ON`` keeps the first row per ``entity_id`` in the ordering,
        which is the newest.
        """
        if not entity_ids:
            return {}
        result = await self._session.execute(
            select(AiGeneration)
            .where(
                AiGeneration.organization_id == organization_id,
                AiGeneration.entity_type == entity_type,
                AiGeneration.entity_id.in_(entity_ids),
                AiGeneration.feature == feature,
            )
            .order_by(AiGeneration.entity_id, AiGeneration.created_at.desc())
            .distinct(AiGeneration.entity_id)
        )
        return {
            generation.entity_id: generation
            for generation in result.scalars().all()
            if generation.entity_id is not None
        }

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


class NbaRuleRepository(TenantScopedRepository[NbaRule]):
    """Queries over ``crm.nba_rules`` — tenant rules and built-in overrides."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NbaRule)

    async def all_live(self, organization_id: uuid.UUID) -> Sequence[NbaRule]:
        result = await self._session.execute(
            self._base_query(organization_id).order_by(
                NbaRule.position.asc(), NbaRule.created_at.asc()
            )
        )
        return result.scalars().all()

    async def builtin_override(self, organization_id: uuid.UUID, key: str) -> NbaRule | None:
        result = await self._session.execute(
            self._base_query(organization_id).where(NbaRule.builtin_key == key)
        )
        return result.scalar_one_or_none()

    async def name_taken(
        self, organization_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None
    ) -> bool:
        statement = self._base_query(organization_id).where(
            NbaRule.builtin_key.is_(None), func.lower(NbaRule.name) == name.lower()
        )
        if exclude_id is not None:
            statement = statement.where(NbaRule.id != exclude_id)
        result = await self._session.execute(statement.limit(1))
        return result.scalar_one_or_none() is not None


class NbaActionLogRepository:
    """Append-only writes to ``crm.nba_action_logs``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, log: NbaActionLog) -> NbaActionLog:
        self._session.add(log)
        await self._session.flush()
        return log


__all__ = ["AiGenerationRepository", "NbaActionLogRepository", "NbaRuleRepository"]
