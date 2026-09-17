"""Data access for the AI gateway.

Only the prompt library is persisted here. Every statement filters on
``organization_id`` explicitly — PostgreSQL RLS is the backstop, not the
primary control (see :mod:`app.products.crm.shared.repository` for the same
reasoning applied to CRM tables).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.ai.models import AiPromptVersion


class AiPromptRepository:
    """Reads and writes the versioned prompt library."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, organization_id: uuid.UUID, key: str) -> AiPromptVersion | None:
        """The version currently in force for ``key``, if one has been published."""
        result = await self._session.execute(
            select(AiPromptVersion).where(
                AiPromptVersion.organization_id == organization_id,
                AiPromptVersion.key == key,
                AiPromptVersion.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get(
        self, version_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AiPromptVersion | None:
        """One version by id, scoped to the organization that owns it."""
        result = await self._session.execute(
            select(AiPromptVersion).where(
                AiPromptVersion.id == version_id,
                AiPromptVersion.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_versions(
        self, organization_id: uuid.UUID, key: str, *, limit: int = 50
    ) -> Sequence[AiPromptVersion]:
        """Published versions for ``key``, newest first."""
        result = await self._session.execute(
            select(AiPromptVersion)
            .where(
                AiPromptVersion.organization_id == organization_id,
                AiPromptVersion.key == key,
            )
            .order_by(AiPromptVersion.version.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def next_version_number(self, organization_id: uuid.UUID, key: str) -> int:
        """One past the highest version yet published, starting at 1."""
        result = await self._session.execute(
            select(func.coalesce(func.max(AiPromptVersion.version), 0)).where(
                AiPromptVersion.organization_id == organization_id,
                AiPromptVersion.key == key,
            )
        )
        return int(result.scalar_one()) + 1

    async def deactivate_all(self, organization_id: uuid.UUID, key: str) -> None:
        """Clear the active flag across ``key``.

        Run immediately before inserting the new active row, in the same
        transaction, so the partial unique index never sees two live rows.
        """
        await self._session.execute(
            update(AiPromptVersion)
            .where(
                AiPromptVersion.organization_id == organization_id,
                AiPromptVersion.key == key,
                AiPromptVersion.is_active.is_(True),
            )
            .values(is_active=False)
        )

    async def add(self, version: AiPromptVersion) -> AiPromptVersion:
        self._session.add(version)
        await self._session.flush()
        return version


__all__ = ["AiPromptRepository"]
