"""Reading the delivery log.

Write-side access lives in :mod:`app.platform.email.service`, next to the
sending it is part of. This module is the administrator's view: list what we
tried to send, and count how it went.

**Every query filters on ``organization_id`` explicitly**, even though RLS
filters again underneath. That is the same belt-and-braces the CRM repositories
use, and it matters more here than usual: the table's policy is NULL-aware, so
"no organization in scope" is a *meaningful* scope rather than one that matches
nothing. A read that forgot its organization would therefore return the
untenanted rows instead of an empty page — password resets, addressed to people
who may not be members at all. The explicit predicate makes that impossible to
reach from an administrator's endpoint regardless of what the session's tenant
setting happens to be.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Final

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.platform.email.models import EmailDelivery, EmailDeliveryStatus

#: Columns a caller may sort on. An allow-list rather than "whatever they sent"
#: — an ORDER BY on an unindexed column over a growing log is a slow query a
#: stranger gets to choose.
SORTABLE: Final[frozenset[str]] = frozenset(
    {"created_at", "sent_at", "status", "template", "to_address"}
)


class EmailDeliveryRepository:
    """Queries over ``platform.email_deliveries``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _scoped(self, organization_id: uuid.UUID) -> Select[tuple[EmailDelivery]]:
        return select(EmailDelivery).where(
            EmailDelivery.organization_id == organization_id
        )

    async def list_deliveries(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        status: EmailDeliveryStatus | None = None,
        template: str | None = None,
        to_address: str | None = None,
        sent_from: dt.datetime | None = None,
        sent_to: dt.datetime | None = None,
    ) -> tuple[Sequence[EmailDelivery], int]:
        """One page of the log, with the total the same filters would return.

        The count runs the same predicate as the page rather than counting the
        table, so "showing 25 of 4" cannot happen.
        """
        statement = self._scoped(organization_id)

        if status is not None:
            statement = statement.where(EmailDelivery.status == status)
        if template:
            statement = statement.where(EmailDelivery.template == template)
        if to_address:
            # Case-insensitive contains: an administrator looking for one
            # person types part of an address, not all of it.
            statement = statement.where(
                EmailDelivery.to_address.ilike(f"%{to_address.strip()}%")
            )
        if sent_from is not None:
            statement = statement.where(EmailDelivery.created_at >= sent_from)
        if sent_to is not None:
            statement = statement.where(EmailDelivery.created_at <= sent_to)

        total = await self._session.scalar(
            select(func.count()).select_from(statement.subquery())
        )

        column = getattr(
            EmailDelivery,
            params.sort_by if params.sort_by in SORTABLE else "created_at",
        )
        ordering = column.asc() if params.sort_dir == "asc" else column.desc()
        # A stable tiebreak on the primary key: without one, two rows written
        # in the same millisecond can swap places between page 1 and page 2 and
        # a row is silently skipped.
        rows = await self._session.execute(
            statement.order_by(ordering, EmailDelivery.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        return rows.scalars().all(), int(total or 0)

    async def counts_by_status(
        self, organization_id: uuid.UUID, *, since: dt.datetime | None = None
    ) -> dict[EmailDeliveryStatus, int]:
        """How many messages landed in each state.

        Every state appears, including the ones with no rows: a summary that
        omits FAILED when nothing failed reads identically to one where the
        failure count was never computed.
        """
        statement = select(EmailDelivery.status, func.count()).where(
            EmailDelivery.organization_id == organization_id
        )
        if since is not None:
            statement = statement.where(EmailDelivery.created_at >= since)

        rows = await self._session.execute(statement.group_by(EmailDelivery.status))
        counted: dict[EmailDeliveryStatus, int] = {
            row[0]: int(row[1]) for row in rows.all()
        }
        return {status: counted.get(status, 0) for status in EmailDeliveryStatus}

    async def distinct_templates(self, organization_id: uuid.UUID) -> Sequence[str]:
        """Template names this organization has actually received.

        Offered to the filter control instead of the full registry: a tenant
        that has never sent a meeting reminder should not be given a filter
        that is guaranteed to return nothing.
        """
        rows = await self._session.execute(
            select(EmailDelivery.template)
            .where(EmailDelivery.organization_id == organization_id)
            .distinct()
            .order_by(EmailDelivery.template)
        )
        return list(rows.scalars().all())


__all__ = ["SORTABLE", "EmailDeliveryRepository"]
