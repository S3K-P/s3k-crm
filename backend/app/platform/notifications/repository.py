"""Data access for the notifications module.

Every statement filters on ``organization_id`` **and** ``recipient_user_id``
explicitly. RLS on ``platform.notifications`` is the backstop, not the plan
(doc 13, defence in depth) — and recipient scoping has no RLS backstop at all,
because a notification's tenant and its intended reader are different
questions: RLS answers "which organization", this repository answers "which
one of that organization's members". A caller reading only their own rows is
enforced here, in the one place every read goes through, not repeated at each
call site.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, Select, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.platform.notifications.models import Notification


class NotificationRepository:
    """Tenant- and recipient-scoped access to notifications."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """The session this repository writes through.

        Exposed so the service can append an audit record on the same
        transaction as the change it describes, matching every other module's
        repository in this codebase.
        """
        return self._session

    def _query(
        self, organization_id: uuid.UUID, recipient_user_id: uuid.UUID
    ) -> Select[tuple[Notification]]:
        return select(Notification).where(
            Notification.organization_id == organization_id,
            Notification.recipient_user_id == recipient_user_id,
        )

    async def get(
        self, notification_id: uuid.UUID, organization_id: uuid.UUID, recipient_user_id: uuid.UUID
    ) -> Notification | None:
        result = await self._session.execute(
            self._query(organization_id, recipient_user_id).where(
                Notification.id == notification_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_recipient(
        self,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        *,
        params: PageParams,
        unread_only: bool = False,
    ) -> tuple[Sequence[Notification], int]:
        statement = self._query(organization_id, recipient_user_id)
        if unread_only:
            statement = statement.where(Notification.read_at.is_(None))

        total = int(
            (
                await self._session.execute(select(func.count()).select_from(statement.subquery()))
            ).scalar_one()
        )
        ordered = statement.order_by(Notification.created_at.desc(), Notification.id.desc())
        result = await self._session.execute(ordered.limit(params.limit).offset(params.offset))
        return result.scalars().all(), total

    async def unread_count(self, organization_id: uuid.UUID, recipient_user_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(
                self._query(organization_id, recipient_user_id)
                .where(Notification.read_at.is_(None))
                .subquery()
            )
        )
        return int(result.scalar_one())

    async def add(self, notification: Notification) -> Notification:
        self._session.add(notification)
        await self._session.flush()
        return notification

    async def create_deduplicated(self, notification: Notification) -> bool:
        """Insert a reminder notification unless its dedupe key already fired.

        Used only for reminders (:attr:`Notification.dedupe_key` set) — see
        the unique constraint in the migration. A plain ``INSERT`` would raise
        ``IntegrityError`` on the second tick that finds the same reminder
        still due; ``ON CONFLICT DO NOTHING`` makes that tick a no-op instead
        of a caught exception on the common path.

        Returns:
            ``True`` if a new row was written, ``False`` if the dedupe key was
            already present (this reminder already fired).
        """
        statement = (
            pg_insert(Notification)
            .values(
                id=notification.id,
                organization_id=notification.organization_id,
                recipient_user_id=notification.recipient_user_id,
                kind=notification.kind,
                title=notification.title,
                body=notification.body,
                entity_type=notification.entity_type,
                entity_id=notification.entity_id,
                dedupe_key=notification.dedupe_key,
            )
            .on_conflict_do_nothing(
                index_elements=["organization_id", "recipient_user_id", "dedupe_key"]
            )
            .returning(Notification.id)
        )
        result = await self._session.execute(statement)
        inserted = result.first() is not None
        await self._session.flush()
        return inserted

    async def mark_read(
        self, notification: Notification, *, at: dt.datetime | None = None
    ) -> Notification:
        notification.read_at = at or dt.datetime.now(dt.UTC)
        await self._session.flush()
        return notification

    async def mark_all_read(
        self,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        *,
        at: dt.datetime | None = None,
    ) -> int:
        """Mark every unread notification read in one statement.

        Returns the number of rows actually changed, so the service can report
        it without a second query.
        """
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                update(Notification)
                .where(
                    Notification.organization_id == organization_id,
                    Notification.recipient_user_id == recipient_user_id,
                    Notification.read_at.is_(None),
                )
                .values(read_at=at or dt.datetime.now(dt.UTC))
            ),
        )
        await self._session.flush()
        return int(result.rowcount or 0)


__all__ = ["NotificationRepository"]
