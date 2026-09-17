"""Data access for market_insights.

Sessions use the generic :class:`~app.products.crm.shared.repository.
TenantScopedRepository` unchanged. The child tables — messages and sources —
have their own reads here, because both are always fetched *for one session*
that the caller has already been authorized against, which is a different
access pattern from the paginated, visibility-filtered one the generic
repository implements.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.market_insights.models import (
    MarketInsightMessage,
    MarketInsightSource,
)


class MarketInsightConversationRepository:
    """Messages and sources belonging to one research session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def messages(
        self, session_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Sequence[MarketInsightMessage]:
        """Every message in the conversation, oldest first.

        Ordered by ``sequence`` rather than ``created_at``: two messages
        written inside one request can share a timestamp to the microsecond,
        and a conversation that renders out of order is worse than useless.
        """
        result = await self._session.execute(
            select(MarketInsightMessage)
            .where(
                MarketInsightMessage.session_id == session_id,
                MarketInsightMessage.organization_id == organization_id,
            )
            .order_by(MarketInsightMessage.sequence.asc())
        )
        return result.scalars().all()

    async def next_sequence(self, session_id: uuid.UUID, organization_id: uuid.UUID) -> int:
        """One past the highest sequence in this conversation, starting at 1."""
        result = await self._session.execute(
            select(func.coalesce(func.max(MarketInsightMessage.sequence), 0)).where(
                MarketInsightMessage.session_id == session_id,
                MarketInsightMessage.organization_id == organization_id,
            )
        )
        return int(result.scalar_one()) + 1

    async def sources(
        self, session_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Sequence[MarketInsightSource]:
        """Every source retrieved across the whole session, newest turn last."""
        result = await self._session.execute(
            select(MarketInsightSource)
            .where(
                MarketInsightSource.session_id == session_id,
                MarketInsightSource.organization_id == organization_id,
            )
            .order_by(
                MarketInsightSource.created_at.asc(), MarketInsightSource.position.asc()
            )
        )
        return result.scalars().all()

    async def known_urls(
        self, session_id: uuid.UUID, organization_id: uuid.UUID
    ) -> set[str]:
        """URLs already recorded for this session.

        A follow-up question routinely re-reads a page the opening report
        already cited. Storing it twice would make the Sources panel grow with
        duplicates the user has to read past.
        """
        result = await self._session.execute(
            select(MarketInsightSource.url).where(
                MarketInsightSource.session_id == session_id,
                MarketInsightSource.organization_id == organization_id,
            )
        )
        return set(result.scalars().all())

    def add(self, entity: MarketInsightMessage | MarketInsightSource) -> None:
        self._session.add(entity)

    async def flush(self) -> None:
        await self._session.flush()


__all__ = ["MarketInsightConversationRepository"]
