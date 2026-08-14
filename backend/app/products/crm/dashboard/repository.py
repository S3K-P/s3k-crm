"""Dashboard read model.

This is the one place in CRM that queries tables it does not own. That is
deliberate and sanctioned: ARCHITECTURE-BOUNDARIES.md rule 6 allows a
"dedicated read model" for reads that span modules, precisely so a dashboard
does not have to make six service calls and aggregate in Python.

It is **read-only**. Nothing here writes, so no module's invariants can be
bypassed through it.

Every statement filters on ``organization_id``. Aggregation happens in
PostgreSQL, scoped, rather than fetching rows and filtering in the
application — a dashboard that aggregated globally and trimmed afterwards
would be a tenant leak with extra steps.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.accounts.models import Account
from app.products.crm.activities.models import Activity, ActivityStatus, ActivityType, Meeting
from app.products.crm.common import CrmEntityType, Priority
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.tasks.models import Task, TaskStatus

#: A lead counts as "new" if it was created within this trailing window.
NEW_LEAD_WINDOW_DAYS = 30

#: An opportunity is "closing soon" if its expected close falls within this many days.
CLOSING_SOON_DAYS = 30

#: Row caps for the dashboard's list panels.
TASK_LIMIT = 6
MEETING_LIMIT = 5
ACTIVITY_LIMIT = 8

_CLOSED_TASK_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


class DashboardRepository:
    """Scoped aggregate reads across the CRM tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Helpers -----------------------------------------------------------

    @staticmethod
    def _open_opportunities(organization_id: uuid.UUID) -> Select[tuple[Opportunity]]:
        return select(Opportunity).where(
            Opportunity.organization_id == organization_id,
            Opportunity.deleted_at.is_(None),
            Opportunity.won_at.is_(None),
            Opportunity.lost_at.is_(None),
        )

    async def _scalar_count(self, statement: Select[tuple[Any, ...]]) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(statement.subquery())
        )
        return int(result.scalar_one())

    # --- KPIs --------------------------------------------------------------

    async def count_new_leads(self, organization_id: uuid.UUID, *, now: dt.datetime) -> int:
        cutoff = now - dt.timedelta(days=NEW_LEAD_WINDOW_DAYS)
        return await self._scalar_count(
            select(Lead.id).where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.created_at >= cutoff,
            )
        )

    async def count_qualified_leads(self, organization_id: uuid.UUID) -> int:
        return await self._scalar_count(
            select(Lead.id).where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.status == LeadStatus.QUALIFIED,
            )
        )

    async def count_open_opportunities(self, organization_id: uuid.UUID) -> int:
        return await self._scalar_count(
            self._open_opportunities(organization_id).with_only_columns(Opportunity.id)
        )

    async def sum_open_pipeline_value(self, organization_id: uuid.UUID) -> Decimal:
        """Total value of open opportunities. Zero when there are none."""
        result = await self._session.execute(
            select(func.coalesce(func.sum(Opportunity.deal_value), 0)).where(
                Opportunity.organization_id == organization_id,
                Opportunity.deleted_at.is_(None),
                Opportunity.won_at.is_(None),
                Opportunity.lost_at.is_(None),
            )
        )
        return Decimal(str(result.scalar_one()))

    async def open_pipeline_currencies(self, organization_id: uuid.UUID) -> list[str]:
        """Distinct currencies among the open opportunities.

        ``deal_value`` is per-row and carries its own currency, so a total is
        only meaningful when they all agree. Returning the set lets the caller
        say so rather than silently adding euros to dollars and stamping a
        ``$`` on the result.
        """
        result = await self._session.execute(
            select(Opportunity.currency)
            .where(
                Opportunity.organization_id == organization_id,
                Opportunity.deleted_at.is_(None),
                Opportunity.won_at.is_(None),
                Opportunity.lost_at.is_(None),
            )
            .distinct()
        )
        return sorted(str(row[0]) for row in result.all())

    async def count_opportunities_closing_soon(
        self, organization_id: uuid.UUID, *, today: dt.date
    ) -> int:
        horizon = today + dt.timedelta(days=CLOSING_SOON_DAYS)
        return await self._scalar_count(
            self._open_opportunities(organization_id)
            .with_only_columns(Opportunity.id)
            .where(
                Opportunity.expected_close_date.is_not(None),
                Opportunity.expected_close_date <= horizon,
            )
        )

    async def count_meetings_today(
        self, organization_id: uuid.UUID, *, day_start: dt.datetime, day_end: dt.datetime
    ) -> int:
        """Meetings scheduled for today.

        Counted from ``meetings.start_time`` where a meeting row exists, and
        from the activity's ``due_date`` otherwise, so a MEETING activity
        without scheduling detail is still represented.
        """
        return await self._scalar_count(
            select(Activity.id)
            .outerjoin(Meeting, Meeting.activity_id == Activity.id)
            .where(
                Activity.organization_id == organization_id,
                Activity.deleted_at.is_(None),
                Activity.type == ActivityType.MEETING,
                Activity.status != ActivityStatus.CANCELLED,
                or_(
                    Meeting.start_time.between(day_start, day_end),
                    (Meeting.activity_id.is_(None))
                    & (Activity.due_date.between(day_start, day_end)),
                ),
            )
        )

    async def count_tasks_due(
        self, organization_id: uuid.UUID, *, day_end: dt.datetime
    ) -> tuple[int, int]:
        """Return ``(due_total, high_priority)`` for incomplete tasks."""
        base = (
            select(Task.id)
            .where(
                Task.organization_id == organization_id,
                Task.deleted_at.is_(None),
                Task.status.not_in(_CLOSED_TASK_STATUSES),
                Task.due_date.is_not(None),
                Task.due_date <= day_end,
            )
        )
        total = await self._scalar_count(base)
        high = await self._scalar_count(base.where(Task.priority == Priority.HIGH))
        return total, high

    # --- Pipeline ----------------------------------------------------------

    async def pipeline_by_stage(
        self, organization_id: uuid.UUID
    ) -> Sequence[tuple[uuid.UUID, str, int, int, Decimal]]:
        """Open stages with their loaded opportunity count and value.

        A LEFT JOIN so a configured stage with no deals still appears with a
        zero — an empty column is information, not an absence.
        """
        result = await self._session.execute(
            select(
                PipelineStage.id,
                PipelineStage.name,
                PipelineStage.sort_order,
                func.count(Opportunity.id),
                func.coalesce(func.sum(Opportunity.deal_value), 0),
            )
            .outerjoin(
                Opportunity,
                (Opportunity.stage_id == PipelineStage.id)
                & (Opportunity.deleted_at.is_(None))
                & (Opportunity.won_at.is_(None))
                & (Opportunity.lost_at.is_(None)),
            )
            .where(
                PipelineStage.organization_id == organization_id,
                PipelineStage.deleted_at.is_(None),
                PipelineStage.is_won.is_(False),
                PipelineStage.is_lost.is_(False),
            )
            .group_by(PipelineStage.id, PipelineStage.name, PipelineStage.sort_order)
            .order_by(PipelineStage.sort_order)
        )
        return [
            (row[0], row[1], row[2], int(row[3]), Decimal(str(row[4]))) for row in result.all()
        ]

    # --- Lists -------------------------------------------------------------

    async def open_tasks(
        self, organization_id: uuid.UUID, *, limit: int = TASK_LIMIT
    ) -> Sequence[Task]:
        result = await self._session.execute(
            select(Task)
            .where(
                Task.organization_id == organization_id,
                Task.deleted_at.is_(None),
                Task.status.not_in(_CLOSED_TASK_STATUSES),
            )
            .order_by(Task.due_date.asc().nulls_last(), Task.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def upcoming_meetings(
        self, organization_id: uuid.UUID, *, now: dt.datetime, limit: int = MEETING_LIMIT
    ) -> Sequence[tuple[Activity, Meeting | None]]:
        result = await self._session.execute(
            select(Activity, Meeting)
            .outerjoin(Meeting, Meeting.activity_id == Activity.id)
            .where(
                Activity.organization_id == organization_id,
                Activity.deleted_at.is_(None),
                Activity.type == ActivityType.MEETING,
                Activity.status == ActivityStatus.PLANNED,
                or_(
                    Meeting.start_time >= now,
                    (Meeting.activity_id.is_(None)) & (Activity.due_date >= now),
                ),
            )
            .order_by(
                func.coalesce(Meeting.start_time, Activity.due_date).asc().nulls_last()
            )
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def recent_activities(
        self, organization_id: uuid.UUID, *, limit: int = ACTIVITY_LIMIT
    ) -> Sequence[Activity]:
        """Interactions that actually took place, newest first.

        Restricted to ``COMPLETED``. A planned meeting is scheduled, not
        recorded: including it here would put a *future* appointment in a feed
        headed "recent", timestamped by when someone typed it in. Planned work
        belongs to the upcoming-meetings panel, which is where it goes.
        """
        result = await self._session.execute(
            select(Activity)
            .where(
                Activity.organization_id == organization_id,
                Activity.deleted_at.is_(None),
                Activity.status == ActivityStatus.COMPLETED,
            )
            .order_by(func.coalesce(Activity.completed_at, Activity.created_at).desc())
            .limit(limit)
        )
        return result.scalars().all()

    # --- Label resolution --------------------------------------------------

    async def resolve_related_labels(
        self, organization_id: uuid.UUID, references: Sequence[tuple[CrmEntityType, uuid.UUID]]
    ) -> dict[uuid.UUID, str]:
        """Human-readable names for polymorphic ``related_entity_id`` values.

        Resolved in one query per entity type rather than per row, and scoped
        to the organization so a dangling reference to another tenant's record
        resolves to nothing instead of leaking its name.
        """
        labels: dict[uuid.UUID, str] = {}
        by_type: dict[CrmEntityType, list[uuid.UUID]] = {}
        for entity_type, entity_id in references:
            by_type.setdefault(entity_type, []).append(entity_id)

        if account_ids := by_type.get(CrmEntityType.ACCOUNT):
            result = await self._session.execute(
                select(Account.id, Account.name).where(
                    Account.organization_id == organization_id, Account.id.in_(account_ids)
                )
            )
            labels.update({row[0]: row[1] for row in result.all()})

        if contact_ids := by_type.get(CrmEntityType.CONTACT):
            result = await self._session.execute(
                select(Contact.id, Contact.first_name, Contact.last_name).where(
                    Contact.organization_id == organization_id, Contact.id.in_(contact_ids)
                )
            )
            labels.update({row[0]: f"{row[1]} {row[2]}".strip() for row in result.all()})

        if lead_ids := by_type.get(CrmEntityType.LEAD):
            result = await self._session.execute(
                select(Lead.id, Lead.first_name, Lead.last_name, Lead.company).where(
                    Lead.organization_id == organization_id, Lead.id.in_(lead_ids)
                )
            )
            labels.update(
                {row[0]: (row[3] or f"{row[1]} {row[2]}").strip() for row in result.all()}
            )

        if opportunity_ids := by_type.get(CrmEntityType.OPPORTUNITY):
            result = await self._session.execute(
                select(Opportunity.id, Opportunity.name).where(
                    Opportunity.organization_id == organization_id,
                    Opportunity.id.in_(opportunity_ids),
                )
            )
            labels.update({row[0]: row[1] for row in result.all()})

        return labels


__all__ = [
    "ACTIVITY_LIMIT",
    "CLOSING_SOON_DAYS",
    "MEETING_LIMIT",
    "NEW_LEAD_WINDOW_DAYS",
    "TASK_LIMIT",
    "DashboardRepository",
]
