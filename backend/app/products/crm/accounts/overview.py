"""Account 360: the account's own aggregate view (Checkpoint 2).

A "dedicated read model" (ARCHITECTURE-BOUNDARIES.md rule 6): it reads across
contacts, opportunities, tasks and activities to answer two questions the
account detail page needs — "what does this account look like at a glance"
and "what has happened on it" — without one request per related record.
``DashboardRepository`` is the precedent this follows, at the scale of one
account instead of the whole organization.

Every aggregate reuses the same :class:`RecordVisibility` the list endpoint
for that module applies, so an account's summary can never show a bigger
number, or a different name, than the caller could get by opening the
underlying list themselves (Checkpoint 2 §13).

Notes are deliberately excluded from the unified timeline. A note's
visibility (private to its author, team, or organization-wide) is enforced in
the notes module's own policy, not by a column this file could filter on —
re-deriving that rule here would be a second, easier-to-get-wrong copy of a
security check that already exists. The Notes tab, which calls the notes
module directly, remains the correct place to read them.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.organizations.service import organizations_for_session
from app.products.crm.activities.models import Activity, ActivityStatus, ActivityType, Meeting
from app.products.crm.activities.service import ActivityService
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.opportunities.models import (
    Opportunity,
    OpportunityStageHistory,
    PipelineStage,
)
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import Task, TaskStatus

#: How many rows each timeline source contributes before the merge trims to
#: the caller's requested limit. Generous enough that "recent" reflects real
#: recency across every source rather than one source crowding the others out.
_SOURCE_LIMIT = 50

_CLOSED_TASK_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """One event in an account's unified timeline.

    ``detail`` holds only what the source row already stored (a stage name, a
    job title) — never free text lifted from a note or an email body, which
    is exactly the content this file does not have permission to read.
    """

    kind: str
    occurred_at: dt.datetime
    title: str
    detail: str | None
    entity_type: str
    entity_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class AccountOverview:
    """Everything the Account 360 summary header shows. Holds no credential."""

    contacts_count: int
    open_deals_count: int
    open_pipeline_value: Decimal
    open_pipeline_currency: str | None
    won_deals_count: int
    won_revenue: Decimal
    won_revenue_currency: str | None
    open_tasks_count: int
    last_activity_at: dt.datetime | None
    next_meeting_id: uuid.UUID | None
    next_meeting_title: str | None
    next_meeting_at: dt.datetime | None
    owner_name: str | None
    primary_contact_name: str | None
    primary_contact_title: str | None


def merge_timeline_entries(*groups: Sequence[TimelineEntry], limit: int) -> list[TimelineEntry]:
    """Newest-first merge of every source, truncated to ``limit``.

    A pure function on purpose: what has to be right here is the sort and the
    cutoff, which needs no database to prove — see
    ``tests/unit/test_account_timeline.py``.
    """
    combined = [entry for group in groups for entry in group]
    combined.sort(key=lambda entry: entry.occurred_at, reverse=True)
    return combined[:limit]


class AccountOverviewRepository:
    """Scoped aggregate reads for one account.

    Every statement is aggregate SQL or a bounded, indexed select — none of it
    loops over related rows in Python — so the query count for one overview
    stays flat whether the account has three contacts or three thousand.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _scoped(
        statement: Select[Any], visibility: RecordVisibility, model: type[Any]
    ) -> Select[Any]:
        predicate = visibility.filter_for(model)
        return statement if predicate is None else statement.where(predicate)

    async def contacts_count(
        self, account_id: uuid.UUID, organization_id: uuid.UUID, visibility: RecordVisibility
    ) -> int:
        statement = self._scoped(
            select(func.count(Contact.id)).where(
                Contact.organization_id == organization_id,
                Contact.account_id == account_id,
                Contact.deleted_at.is_(None),
            ),
            visibility,
            Contact,
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def deal_summary(
        self, account_id: uuid.UUID, organization_id: uuid.UUID, visibility: RecordVisibility
    ) -> tuple[int, Decimal, list[str], int, Decimal, list[str]]:
        """``(open_count, open_value, open_currencies, won_count, won_value, won_currencies)``."""
        base = self._scoped(
            select(Opportunity).where(
                Opportunity.organization_id == organization_id,
                Opportunity.account_id == account_id,
                Opportunity.deleted_at.is_(None),
            ),
            visibility,
            Opportunity,
        )
        open_where = (Opportunity.won_at.is_(None), Opportunity.lost_at.is_(None))
        won_where = (Opportunity.won_at.is_not(None),)

        open_count = await self._session.execute(
            select(func.count()).select_from(base.where(*open_where).subquery())
        )
        deal_value_sum = func.coalesce(func.sum(Opportunity.deal_value), 0)
        open_value = await self._session.execute(
            base.with_only_columns(deal_value_sum).where(*open_where)
        )
        open_currencies = await self._session.execute(
            base.with_only_columns(Opportunity.currency).where(*open_where).distinct()
        )
        won_count = await self._session.execute(
            select(func.count()).select_from(base.where(*won_where).subquery())
        )
        won_value = await self._session.execute(
            base.with_only_columns(deal_value_sum).where(*won_where)
        )
        won_currencies = await self._session.execute(
            base.with_only_columns(Opportunity.currency).where(*won_where).distinct()
        )
        return (
            int(open_count.scalar_one()),
            Decimal(str(open_value.scalar_one())),
            sorted(str(row[0]) for row in open_currencies.all()),
            int(won_count.scalar_one()),
            Decimal(str(won_value.scalar_one())),
            sorted(str(row[0]) for row in won_currencies.all()),
        )

    async def open_tasks_count(
        self, account_id: uuid.UUID, organization_id: uuid.UUID, visibility: RecordVisibility
    ) -> int:
        statement = self._scoped(
            select(func.count(Task.id)).where(
                Task.organization_id == organization_id,
                Task.related_entity_type == CrmEntityType.ACCOUNT,
                Task.related_entity_id == account_id,
                Task.deleted_at.is_(None),
                Task.status.not_in(_CLOSED_TASK_STATUSES),
            ),
            visibility,
            Task,
        )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def owner_name(
        self, organization_id: uuid.UUID, owner_id: uuid.UUID | None
    ) -> str | None:
        """The owner's display name, through the Platform service interface.

        A product may not read ``platform.users`` itself
        (ARCHITECTURE-BOUNDARIES.md rule 2); ``member_directory`` is the
        sanctioned seam, already used by the reports module for the same
        "id owned by, but not stored in, this module" problem.
        """
        if owner_id is None:
            return None
        directory = await organizations_for_session(self._session).member_directory(
            organization_id, [owner_id]
        )
        identity = directory.get(owner_id)
        return identity.display_name if identity else None

    async def primary_contact(
        self, organization_id: uuid.UUID, contact_id: uuid.UUID | None
    ) -> Contact | None:
        if contact_id is None:
            return None
        result = await self._session.execute(
            select(Contact).where(
                Contact.id == contact_id,
                Contact.organization_id == organization_id,
                Contact.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def next_meeting(
        self, account_id: uuid.UUID, organization_id: uuid.UUID, *, now: dt.datetime
    ) -> tuple[uuid.UUID, str, dt.datetime] | None:
        """The soonest planned *future* meeting logged against this account.

        The future cutoff is a WHERE clause, not a check on the top row after
        ``LIMIT 1``: ordering ascending and taking the first row would instead
        return the *oldest* past meeting whenever no future one exists, since
        that sorts earliest of all. Mirrors
        ``DashboardRepository.upcoming_meetings``, scoped to one account.
        """
        result = await self._session.execute(
            select(Activity.id, Activity.subject, Meeting.start_time, Activity.due_date)
            .outerjoin(Meeting, Meeting.activity_id == Activity.id)
            .where(
                Activity.organization_id == organization_id,
                Activity.deleted_at.is_(None),
                Activity.type == ActivityType.MEETING,
                Activity.status == ActivityStatus.PLANNED,
                Activity.related_entity_type == CrmEntityType.ACCOUNT,
                Activity.related_entity_id == account_id,
                or_(
                    Meeting.start_time >= now,
                    (Meeting.activity_id.is_(None)) & (Activity.due_date >= now),
                ),
            )
            .order_by(func.coalesce(Meeting.start_time, Activity.due_date).asc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None
        activity_id, subject, start_time, due_date = row
        when = start_time or due_date
        if when is None:
            # The WHERE clause above requires one of the two to be >= now.
            raise AssertionError("unreachable: a matched row always has a start time or due date")
        return activity_id, subject, when

    # --- Timeline sources ----------------------------------------------------

    async def activity_entries(
        self, account_id: uuid.UUID, organization_id: uuid.UUID, *, limit: int = _SOURCE_LIMIT
    ) -> list[TimelineEntry]:
        """Delegates to the activities module's own service (a sibling CRM
        service, not a foreign query — ARCHITECTURE-BOUNDARIES.md rule 6/7),
        so "what counts as this account's activity timeline" is defined in
        exactly one place.
        """
        items = await ActivityService(self._session).timeline(
            organization_id,
            entity_type=CrmEntityType.ACCOUNT,
            entity_id=account_id,
            limit=limit,
        )
        return [
            TimelineEntry(
                kind="activity",
                occurred_at=activity.completed_at or activity.due_date or activity.created_at,
                title=activity.subject,
                detail=activity.type.value.title(),
                entity_type="ACTIVITY",
                entity_id=activity.id,
            )
            for activity in items
        ]

    async def deal_created_entries(
        self,
        account_id: uuid.UUID,
        organization_id: uuid.UUID,
        visibility: RecordVisibility,
        *,
        limit: int = _SOURCE_LIMIT,
    ) -> list[TimelineEntry]:
        statement = self._scoped(
            select(Opportunity)
            .where(
                Opportunity.organization_id == organization_id,
                Opportunity.account_id == account_id,
                Opportunity.deleted_at.is_(None),
            )
            .order_by(Opportunity.created_at.desc())
            .limit(limit),
            visibility,
            Opportunity,
        )
        result = await self._session.execute(statement)
        return [
            TimelineEntry(
                kind="deal_created",
                occurred_at=deal.created_at,
                title=f"Deal created: {deal.name}",
                detail=None,
                entity_type="OPPORTUNITY",
                entity_id=deal.id,
            )
            for deal in result.scalars().all()
        ]

    async def stage_changed_entries(
        self,
        account_id: uuid.UUID,
        organization_id: uuid.UUID,
        visibility: RecordVisibility,
        *,
        limit: int = _SOURCE_LIMIT,
    ) -> list[TimelineEntry]:
        """Stage moves for this account's deals, newest first.

        Visibility is applied against ``Opportunity``, the row that actually
        carries ``owner_id`` — history rows have none of their own, so a caller
        restricted to their own deals must not see another rep's stage moves
        leak through this join.
        """
        from_stage = PipelineStage.__table__.alias("from_stage")
        to_stage = PipelineStage.__table__.alias("to_stage")
        statement = self._scoped(
            select(
                OpportunityStageHistory.id,
                OpportunityStageHistory.changed_at,
                Opportunity.id,
                Opportunity.name,
                from_stage.c.name,
                to_stage.c.name,
            )
            .select_from(OpportunityStageHistory)
            .join(Opportunity, Opportunity.id == OpportunityStageHistory.opportunity_id)
            .outerjoin(from_stage, from_stage.c.id == OpportunityStageHistory.from_stage_id)
            .join(to_stage, to_stage.c.id == OpportunityStageHistory.to_stage_id)
            .where(
                Opportunity.organization_id == organization_id,
                Opportunity.account_id == account_id,
                Opportunity.deleted_at.is_(None),
            )
            .order_by(OpportunityStageHistory.changed_at.desc())
            .limit(limit),
            visibility,
            Opportunity,
        )
        result = await self._session.execute(statement)
        entries = []
        for _history_id, changed_at, deal_id, deal_name, from_name, to_name in result.all():
            detail = f"{from_name} → {to_name}" if from_name else f"Started in {to_name}"
            entries.append(
                TimelineEntry(
                    kind="stage_changed",
                    occurred_at=changed_at,
                    title=f"{deal_name}: stage changed",
                    detail=detail,
                    entity_type="OPPORTUNITY",
                    entity_id=deal_id,
                )
            )
        return entries

    async def contact_created_entries(
        self,
        account_id: uuid.UUID,
        organization_id: uuid.UUID,
        visibility: RecordVisibility,
        *,
        limit: int = _SOURCE_LIMIT,
    ) -> list[TimelineEntry]:
        statement = self._scoped(
            select(Contact)
            .where(
                Contact.organization_id == organization_id,
                Contact.account_id == account_id,
                Contact.deleted_at.is_(None),
            )
            .order_by(Contact.created_at.desc())
            .limit(limit),
            visibility,
            Contact,
        )
        result = await self._session.execute(statement)
        return [
            TimelineEntry(
                kind="contact_created",
                occurred_at=contact.created_at,
                title=f"Contact added: {contact.full_name}",
                detail=contact.job_title,
                entity_type="CONTACT",
                entity_id=contact.id,
            )
            for contact in result.scalars().all()
        ]


__all__ = [
    "AccountOverview",
    "AccountOverviewRepository",
    "TimelineEntry",
    "merge_timeline_entries",
]
