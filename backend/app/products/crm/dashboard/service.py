"""Dashboard aggregation.

Assembles the single summary payload the dashboard renders. All arithmetic is
done by PostgreSQL inside the tenant scope; this layer only shapes the result.

**On truthfulness.** Every number returned is derived from real rows in the
caller's organization. The dashboard UI also shows per-KPI trend deltas
("+12% this week"). Those are *not* returned here: the schema has no history
table, and computing a real week-over-week delta would need either a snapshot
table or created/updated-window comparisons that the current model cannot
support honestly for values like pipeline total. Rather than invent them, the
API omits deltas and the UI shows a factual subtitle instead — see the Phase 4
report for the limitation.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.common import CrmEntityType
from app.products.crm.dashboard.repository import DashboardRepository
from app.products.crm.dashboard.schemas import (
    DashboardActivity,
    DashboardKpis,
    DashboardMeeting,
    DashboardSummary,
    DashboardTask,
    PipelineStageSummary,
)
from app.products.crm.shared.visibility import DashboardScope
from app.products.crm.tasks.models import TaskStatus


class DashboardService:
    """Builds the organization-scoped dashboard summary."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = DashboardRepository(session)

    async def summary(
        self,
        organization_id: uuid.UUID,
        *,
        now: dt.datetime | None = None,
        scope: DashboardScope | None = None,
    ) -> DashboardSummary:
        """Aggregate everything the dashboard shows for one organization.

        scope narrows the counts to what the caller may actually open. It
        is resolved per module rather than once, because a custom role can
        hold leads.VIEW_ALL without holding opportunities.VIEW_ALL.
        Passing None aggregates organization-wide, which is what an
        internal caller with no principal gets.
        """
        scope = scope or DashboardScope.unrestricted()
        now = now or dt.datetime.now(dt.UTC)
        today = now.date()
        day_start = dt.datetime.combine(today, dt.time.min, tzinfo=dt.UTC)
        day_end = dt.datetime.combine(today, dt.time.max, tzinfo=dt.UTC)

        repository = self._repository

        new_leads = await repository.count_new_leads(
            organization_id, now=now, visibility=scope.leads
        )
        qualified = await repository.count_qualified_leads(
            organization_id, visibility=scope.leads
        )
        open_opportunities = await repository.count_open_opportunities(
            organization_id, visibility=scope.opportunities
        )
        pipeline_value = await repository.sum_open_pipeline_value(
            organization_id, visibility=scope.opportunities
        )
        currencies = await repository.open_pipeline_currencies(
            organization_id, visibility=scope.opportunities
        )
        # One currency in play → name it. Several → the sum has no single
        # symbol, and saying so beats picking one.
        pipeline_currency = currencies[0] if len(currencies) == 1 else None
        closing_soon = await repository.count_opportunities_closing_soon(
            organization_id, today=today, visibility=scope.opportunities
        )
        meetings_today = await repository.count_meetings_today(
            organization_id, day_start=day_start, day_end=day_end
        )
        tasks_due, tasks_due_high = await repository.count_tasks_due(
            organization_id, day_end=day_end, visibility=scope.tasks
        )

        stages = await repository.pipeline_by_stage(
            organization_id, visibility=scope.opportunities
        )
        pipeline = [
            PipelineStageSummary(
                stage_id=stage_id, name=name, sort_order=sort_order, count=count, value=value
            )
            for stage_id, name, sort_order, count, value in stages
        ]

        tasks = [
            DashboardTask(
                id=task.id,
                title=task.title,
                description=task.description,
                priority=task.priority.value,
                status=task.status.value,
                due_date=task.due_date,
                completed=task.status is TaskStatus.COMPLETED,
            )
            for task in await repository.open_tasks(organization_id, visibility=scope.tasks)
        ]

        meeting_rows = await repository.upcoming_meetings(organization_id, now=now)
        activity_rows = await repository.recent_activities(organization_id)

        # Resolve every polymorphic reference across both lists in one pass.
        references = [
            (activity.related_entity_type, activity.related_entity_id)
            for activity, _meeting in meeting_rows
            if activity.related_entity_type and activity.related_entity_id
        ]
        references += [
            (activity.related_entity_type, activity.related_entity_id)
            for activity in activity_rows
            if activity.related_entity_type and activity.related_entity_id
        ]
        labels = await repository.resolve_related_labels(
            organization_id, [(t, i) for t, i in references if isinstance(t, CrmEntityType)]
        )

        meetings = [
            DashboardMeeting(
                id=activity.id,
                title=activity.subject,
                start_time=meeting.start_time if meeting else activity.due_date,
                end_time=meeting.end_time if meeting else None,
                related_label=(
                    labels.get(activity.related_entity_id)
                    if activity.related_entity_id
                    else None
                ),
            )
            for activity, meeting in meeting_rows
        ]

        activities = [
            DashboardActivity(
                id=activity.id,
                type=activity.type.value,
                subject=activity.subject,
                detail=(
                    labels.get(activity.related_entity_id)
                    if activity.related_entity_id
                    else activity.outcome
                ),
                occurred_at=activity.completed_at or activity.created_at,
            )
            for activity in activity_rows
        ]

        return DashboardSummary(
            kpis=DashboardKpis(
                new_leads=new_leads,
                qualified_leads=qualified,
                open_opportunities=open_opportunities,
                pipeline_value=pipeline_value,
                meetings_today=meetings_today,
                tasks_due=tasks_due,
                tasks_due_high_priority=tasks_due_high,
                opportunities_closing_soon=closing_soon,
            ),
            pipeline=pipeline,
            pipeline_total=pipeline_value,
            pipeline_currency=pipeline_currency,
            tasks=tasks,
            meetings=meetings,
            activities=activities,
        )


__all__ = ["DashboardService"]
