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

from app.platform.organizations.service import organizations_for_session
from app.products.crm.common import CrmEntityType
from app.products.crm.dashboard.repository import (
    NEW_LEAD_WINDOW_DAYS,
    DashboardRepository,
)
from app.products.crm.dashboard.schemas import (
    DashboardActivity,
    DashboardKpis,
    DashboardMeeting,
    DashboardSummary,
    DashboardTask,
    LeadSourcePerformance,
    OwnerPipelineSummary,
    PipelineStageSummary,
    RevenueMonth,
)
from app.products.crm.reports.repository import ReportRepository
from app.products.crm.shared.visibility import DashboardScope
from app.products.crm.tasks.models import TaskStatus

#: Months of won-revenue history the trend chart shows.
REVENUE_TREND_MONTHS = 6


class DashboardService:
    """Builds the organization-scoped dashboard summary."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = DashboardRepository(session)
        # Reused rather than re-queried: lead-source performance is exactly
        # `reports.catalog`'s own `lead-conversion-by-source` runner, called
        # directly on its repository so the two numbers can never disagree.
        self._reports = ReportRepository(session)
        self._organizations = organizations_for_session(session)

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
        weighted_pipeline = await repository.sum_weighted_pipeline_value(
            organization_id, visibility=scope.opportunities
        )
        won_revenue = await repository.sum_won_revenue(
            organization_id,
            since=now - dt.timedelta(days=NEW_LEAD_WINDOW_DAYS),
            visibility=scope.opportunities,
        )
        conversion_rate = await repository.lead_conversion_rate(
            organization_id, visibility=scope.leads
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

        trend_rows = await repository.won_revenue_by_month(
            organization_id,
            months=REVENUE_TREND_MONTHS,
            today=today,
            visibility=scope.opportunities,
        )
        revenue_trend = [RevenueMonth(month=month, value=value) for month, value in trend_rows]

        owner_rows = await repository.pipeline_by_owner(
            organization_id, visibility=scope.opportunities
        )
        owner_ids = {owner_id for owner_id, _count, _value in owner_rows if owner_id is not None}
        directory = (
            await self._organizations.member_directory(organization_id, owner_ids)
            if owner_ids
            else {}
        )
        pipeline_by_owner = [
            OwnerPipelineSummary(
                owner=(directory[owner_id].display_name if owner_id in directory else "Unassigned"),
                count=count,
                value=value,
            )
            for owner_id, count, value in owner_rows
        ]

        # The report's own rows, reused verbatim rather than re-derived — see
        # `__init__`'s docstring note. Capped for a dashboard-sized list; the
        # full breakdown is the "Lead conversion by source" report itself.
        source_rows = await self._reports.lead_conversion_by_source(
            organization_id, visibility=scope.leads
        )
        lead_source_performance = [
            LeadSourcePerformance(**row) for row in source_rows[:8]
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
                weighted_pipeline_value=weighted_pipeline,
                won_revenue=won_revenue,
                lead_conversion_rate=conversion_rate,
            ),
            pipeline=pipeline,
            pipeline_total=pipeline_value,
            pipeline_currency=pipeline_currency,
            tasks=tasks,
            meetings=meetings,
            activities=activities,
            revenue_trend=revenue_trend,
            pipeline_by_owner=pipeline_by_owner,
            lead_source_performance=lead_source_performance,
        )


__all__ = ["DashboardService"]
