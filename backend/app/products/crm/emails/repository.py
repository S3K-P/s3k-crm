"""Data access for the emails module.

Template CRUD goes through
:class:`~app.products.crm.shared.repository.TenantScopedRepository` like every
other CRM entity, and gets tenant scoping, soft deletion and pagination from
it. What is here is the handful of queries that repository cannot express: the
conversation read, the thread rollup, and the locked load the delivery handler
makes outside any request.

**Every query filters on ``organization_id`` explicitly**, even though RLS
filters again underneath. That is the belt-and-braces the rest of the CRM
uses, and it matters most on the two methods below that run in the *worker*,
where the session's tenant is set from an outbox event rather than from a
verified principal.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Final

from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.emails.models import EmailMessage, EmailStatus, EmailThread
from app.products.crm.shared.pagination import PageParams

#: Columns a caller may sort messages on. An allow-list rather than "whatever
#: they sent" — an ORDER BY on an unindexed column over a growing table is a
#: slow query a stranger gets to choose.
SORTABLE_MESSAGES: Final[frozenset[str]] = frozenset(
    {"created_at", "sent_at", "subject", "status", "direction"}
)

#: The same, for threads. ``last_message_at`` is the useful default and the
#: one the composite index leads to.
SORTABLE_THREADS: Final[frozenset[str]] = frozenset(
    {"last_message_at", "created_at", "subject", "message_count"}
)


class EmailRepository:
    """Queries over ``crm.email_threads`` and ``crm.email_messages``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    # --- Messages ----------------------------------------------------------

    def _messages(self, organization_id: uuid.UUID) -> Select[tuple[EmailMessage]]:
        return select(EmailMessage).where(
            EmailMessage.organization_id == organization_id,
            EmailMessage.deleted_at.is_(None),
        )

    async def list_messages(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[EmailMessage], int]:
        """One page of messages, with the total the same filters would return.

        The count runs the same predicate as the page rather than counting the
        table, so "showing 25 of 4" cannot happen.
        """
        statement = self._messages(organization_id)
        for predicate in filters:
            statement = statement.where(predicate)

        total = await self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )

        column = getattr(
            EmailMessage,
            params.sort_by if params.sort_by in SORTABLE_MESSAGES else "created_at",
        )
        ordering = column.asc() if params.sort_dir == "asc" else column.desc()
        rows = await self._session.execute(
            # A stable tiebreak on the primary key: without one, two rows
            # written in the same millisecond can swap places between page 1
            # and page 2 and a message is silently skipped.
            statement.order_by(ordering, EmailMessage.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        return rows.scalars().all(), int(total or 0)

    async def thread_messages(
        self,
        thread_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        readable: ColumnElement[bool],
    ) -> Sequence[EmailMessage]:
        """Every message in one conversation, oldest first.

        Ascending, unlike every list endpoint in the product: a conversation
        reads forwards. Deliberately not paginated — a thread is a bounded
        thing, and paging it would break the reply chain across requests for
        no benefit.
        """
        rows = await self._session.execute(
            self._messages(organization_id)
            .where(EmailMessage.thread_id == thread_id, readable)
            .order_by(EmailMessage.created_at.asc(), EmailMessage.id.asc())
        )
        return rows.scalars().all()

    async def lock_message_for_delivery(
        self, message_id: uuid.UUID, organization_id: uuid.UUID
    ) -> EmailMessage | None:
        """Load one message for the worker, locked against a concurrent send.

        ``FOR UPDATE`` rather than a plain read. The outbox's own claim stops
        two workers running the *same* event, but nothing stops a user pressing
        send twice and producing two events for one message: this is what
        serialises them, and the status check the handler makes afterwards is
        only sound while the row is held.

        Soft-deleted rows are deliberately included. A message archived
        between the enqueue and the drain still has an event pointing at it,
        and the handler needs to see the row in order to decide not to send it
        — filtering it out here would produce "message not found" and a
        dead-lettered event instead of a clean skip.
        """
        rows = await self._session.execute(
            select(EmailMessage)
            .where(
                EmailMessage.id == message_id,
                EmailMessage.organization_id == organization_id,
            )
            .with_for_update()
        )
        return rows.scalar_one_or_none()

    # --- Threads -----------------------------------------------------------

    def _threads(self, organization_id: uuid.UUID) -> Select[tuple[EmailThread]]:
        return select(EmailThread).where(
            EmailThread.organization_id == organization_id,
            EmailThread.deleted_at.is_(None),
        )

    async def list_threads(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[EmailThread], int]:
        """One page of conversations, most recently active first."""
        statement = self._threads(organization_id)
        for predicate in filters:
            statement = statement.where(predicate)

        total = await self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )

        column = getattr(
            EmailThread,
            params.sort_by if params.sort_by in SORTABLE_THREADS else "last_message_at",
        )
        # NULLs last in both directions: a thread holding only an unsent draft
        # has no last-message time, and it belongs at the bottom of a list of
        # recent activity rather than at the top of it.
        ordering = (
            column.asc().nullslast()
            if params.sort_dir == "asc"
            else column.desc().nullslast()
        )
        rows = await self._session.execute(
            statement.order_by(ordering, EmailThread.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        return rows.scalars().all(), int(total or 0)

    async def get_thread(
        self, thread_id: uuid.UUID, organization_id: uuid.UUID
    ) -> EmailThread | None:
        rows = await self._session.execute(
            self._threads(organization_id).where(EmailThread.id == thread_id)
        )
        return rows.scalar_one_or_none()

    async def find_thread_by_subject(
        self,
        organization_id: uuid.UUID,
        *,
        normalized_subject: str,
        related_entity_type: str | None,
        related_entity_id: uuid.UUID | None,
    ) -> EmailThread | None:
        """An existing conversation this subject belongs to, if there is one.

        Matched on the normalized subject **and** the record together. Subject
        alone would merge "Following up" to two different customers into one
        thread, which is exactly how a CRM ends up showing one account's mail
        on another account's timeline.
        """
        statement = self._threads(organization_id).where(
            EmailThread.normalized_subject == normalized_subject
        )
        if related_entity_id is None:
            # An unfiled conversation groups only with other unfiled ones.
            statement = statement.where(EmailThread.related_entity_id.is_(None))
        else:
            statement = statement.where(
                EmailThread.related_entity_type == related_entity_type,
                EmailThread.related_entity_id == related_entity_id,
            )
        rows = await self._session.execute(
            statement.order_by(EmailThread.last_message_at.desc().nullslast()).limit(1)
        )
        return rows.scalar_one_or_none()

    async def refresh_thread_rollup(self, thread: EmailThread) -> None:
        """Recompute ``message_count`` and ``last_message_at`` from the messages.

        Recomputed rather than incremented. An increment is wrong the first
        time a send fails, a draft is discarded or a message is archived, and a
        counter that drifts is worse than no counter at all — this is one
        indexed aggregate over a handful of rows.

        Drafts are excluded, which is what keeps one person's unsent work out
        of a count everybody sees.
        """
        row = (
            await self._session.execute(
                select(
                    func.count(EmailMessage.id),
                    func.max(
                        func.coalesce(EmailMessage.sent_at, EmailMessage.created_at)
                    ),
                ).where(
                    EmailMessage.thread_id == thread.id,
                    EmailMessage.deleted_at.is_(None),
                    EmailMessage.status != EmailStatus.DRAFT,
                )
            )
        ).one()
        thread.message_count = int(row[0] or 0)
        thread.last_message_at = row[1]
        await self._session.flush()


__all__ = ["SORTABLE_MESSAGES", "SORTABLE_THREADS", "EmailRepository"]
