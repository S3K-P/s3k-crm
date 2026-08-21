"""Data access for the audit module.

Two properties are the whole job of this file:

**Every statement filters on ``organization_id`` explicitly.** RLS is the
backstop, not the plan (doc 13, "defence in depth"): the query is written to be
correct on its own, so a connection that somehow escaped its tenant scope still
cannot read another organization's trail through this class. There is no method
here that omits the filter, and none may be added.

**Reads are ordered and bounded.** An audit table is the largest table in the
schema by a wide margin, so every list goes through the same offset/limit path
with a sort resolved against known columns rather than against a caller string.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.pagination import PageParams
from app.platform.audit.models import AuditLog

#: Columns a caller may sort on. An allow-list rather than a mapper scan: the
#: audit table is queried with filters that assume the composite indexes, and
#: sorting by an unindexed column on millions of rows is a denial of service
#: with extra steps.
SORTABLE_COLUMNS: dict[str, InstrumentedAttribute[object]] = {
    "created_at": AuditLog.created_at,
    "action": AuditLog.action,
    "module": AuditLog.module,
    "entity_type": AuditLog.entity_type,
    "status": AuditLog.status,
}

DEFAULT_SORT_COLUMN = "created_at"


class AuditRepository:
    """Reads and appends rows of ``platform.audit_logs``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """The session this repository writes through.

        Exposed so the service can apply the tenant setting on the same
        connection the INSERT will use — see ``AuditService._ensure_scope``.
        """
        return self._session

    # --- Writes ------------------------------------------------------------

    async def add(self, entry: AuditLog) -> AuditLog:
        """Append one record.

        Flushed rather than committed: the caller decides the transaction. For
        a successful business action that means the audit row and the change it
        describes commit together or not at all, which is the only way the
        trail can be trusted not to claim something that was rolled back.
        """
        self._session.add(entry)
        await self._session.flush()
        return entry

    # --- Reads -------------------------------------------------------------

    def _base_query(self, organization_id: uuid.UUID) -> Select[tuple[AuditLog]]:
        return select(AuditLog).where(AuditLog.organization_id == organization_id)

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[AuditLog], int]:
        """One page of the organization's trail, plus the total match count."""
        statement = self._base_query(organization_id)
        for condition in filters:
            statement = statement.where(condition)

        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(statement.subquery())
                )
            ).scalar_one()
        )

        column = SORTABLE_COLUMNS.get(params.sort_by or "", AuditLog.created_at)
        ordered = statement.order_by(
            column.asc() if params.sort_dir == "asc" else column.desc(),
            # Ties on a coarse column (two rows in the same second, or the same
            # action) would otherwise page non-deterministically and either
            # repeat or skip rows. The primary key is uuid7, so this is also a
            # chronological tiebreak rather than an arbitrary one.
            AuditLog.id.desc(),
        )

        result = await self._session.execute(
            ordered.limit(params.limit).offset(params.offset)
        )
        return result.scalars().all(), total

    async def get(
        self, entry_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AuditLog | None:
        """One record, **within the organization**.

        An id from another tenant returns ``None``, which the service turns
        into 404 — the same treatment every other module gives a cross-tenant
        identifier.
        """
        result = await self._session.execute(
            self._base_query(organization_id).where(AuditLog.id == entry_id)
        )
        return result.scalar_one_or_none()

    async def distinct_actions(self, organization_id: uuid.UUID) -> Sequence[str]:
        """Actions that actually occur in this organization's trail.

        Drives the filter dropdown from the data rather than from the writer
        enum, so the list offers only choices that can return rows.
        """
        result = await self._session.execute(
            select(AuditLog.action)
            .where(AuditLog.organization_id == organization_id)
            .distinct()
            .order_by(AuditLog.action)
        )
        return list(result.scalars().all())

    async def distinct_entity_types(self, organization_id: uuid.UUID) -> Sequence[str]:
        result = await self._session.execute(
            select(AuditLog.entity_type)
            .where(
                AuditLog.organization_id == organization_id,
                AuditLog.entity_type.is_not(None),
            )
            .distinct()
            .order_by(AuditLog.entity_type)
        )
        return [value for value in result.scalars().all() if value is not None]

    async def earliest_entry_at(self, organization_id: uuid.UUID) -> dt.datetime | None:
        """When this organization's trail begins.

        Lets the screen say "recording since ..." instead of leaving an empty
        table ambiguous between "nothing happened" and "nothing is recorded".
        """
        result = await self._session.execute(
            select(func.min(AuditLog.created_at)).where(
                AuditLog.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()


__all__ = ["DEFAULT_SORT_COLUMN", "SORTABLE_COLUMNS", "AuditRepository"]
