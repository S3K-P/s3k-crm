"""Rule-based AI insights (§13) — grounded in real CRM data, never AI text.

Every insight here is the answer to a plain SQL question ("which open deals
close within two weeks with a weak win probability?") rather than a model's
impression of the pipeline. That is what the checkpoint brief's "insights
must be grounded in actual CRM data" means in code: no provider call sits
between the database and the response, so there is nothing here that could
hallucinate a risk that is not in the CRM.

Every category is scoped by the caller's own module permission and
:class:`RecordVisibility` — the same predicate that entity's own list
endpoint would apply — so "deals at risk" never surfaces a deal the caller
could not otherwise see.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.models import Account, AccountStatus
from app.products.crm.activities.models import Activity
from app.products.crm.common import CrmEntityType
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import Task, TaskStatus

#: Items per category. Small on purpose — an insights digest is a triage
#: list, not a report; a caller wanting more runs the report builder or an
#: advanced-filtered list, which already exist.
CATEGORY_LIMIT = 10
STALE_DAYS = 14
ACCOUNT_QUIET_DAYS = 30
LEAD_MIN_AGE_DAYS = 2

_OPEN_TASK_STATUSES = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
_INACTIVE_LEAD_STATUSES = (LeadStatus.CONVERTED, LeadStatus.LOST, LeadStatus.UNQUALIFIED)


class InsightRow:
    """A plain, testable stand-in for ``schemas.InsightItem`` — see service.py
    for where this becomes the API response shape.
    """

    __slots__ = ("detail", "entity_id", "entity_label", "entity_type", "kind", "severity", "title")

    def __init__(
        self,
        *,
        kind: str,
        severity: str,
        title: str,
        detail: str,
        entity_type: str,
        entity_id: uuid.UUID,
        entity_label: str,
    ) -> None:
        self.kind = kind
        self.severity = severity
        self.title = title
        self.detail = detail
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.entity_label = entity_label


async def deals_at_risk(
    session: AsyncSession, *, principal: Principal, today: dt.date | None = None
) -> list[InsightRow]:
    if not principal.has_permission("opportunities", PermissionAction.VIEW):
        return []
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=STALE_DAYS)
    visibility = RecordVisibility.for_module(principal, "opportunities")
    statement = (
        select(Opportunity, PipelineStage.name)
        .join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
        .where(
            Opportunity.organization_id == principal.organization_id,
            Opportunity.deleted_at.is_(None),
            Opportunity.won_at.is_(None),
            Opportunity.lost_at.is_(None),
            Opportunity.expected_close_date.is_not(None),
            Opportunity.expected_close_date <= horizon,
            or_(Opportunity.win_probability.is_(None), Opportunity.win_probability < 50),
        )
        .order_by(Opportunity.expected_close_date.asc())
        .limit(CATEGORY_LIMIT)
    )
    predicate = visibility.filter_for(Opportunity)
    if predicate is not None:
        statement = statement.where(predicate)
    rows = (await session.execute(statement)).all()
    items: list[InsightRow] = []
    for opportunity, stage_name in rows:
        days = (opportunity.expected_close_date - today).days
        when = f"in {days} day(s)" if days >= 0 else f"{-days} day(s) ago"
        probability = (
            f"{opportunity.win_probability}% win probability"
            if opportunity.win_probability is not None
            else "no win probability set"
        )
        items.append(
            InsightRow(
                kind="DEAL_AT_RISK",
                severity="HIGH" if days < 0 else "MEDIUM",
                title=f"{opportunity.name} closes {when} with {probability}",
                detail=f"Stage: {stage_name}.",
                entity_type="OPPORTUNITY",
                entity_id=opportunity.id,
                entity_label=opportunity.name,
            )
        )
    return items


async def stale_opportunities(
    session: AsyncSession, *, principal: Principal, now: dt.datetime | None = None
) -> list[InsightRow]:
    if not principal.has_permission("opportunities", PermissionAction.VIEW):
        return []
    now = now or dt.datetime.now(dt.UTC)
    cutoff = now - dt.timedelta(days=STALE_DAYS)
    visibility = RecordVisibility.for_module(principal, "opportunities")

    recent_activity = (
        select(Activity.id)
        .where(
            Activity.organization_id == Opportunity.organization_id,
            Activity.related_entity_type == CrmEntityType.OPPORTUNITY,
            Activity.related_entity_id == Opportunity.id,
            Activity.created_at >= cutoff,
        )
        .correlate(Opportunity)
        .exists()
    )
    statement = (
        select(Opportunity, PipelineStage.name)
        .join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
        .where(
            Opportunity.organization_id == principal.organization_id,
            Opportunity.deleted_at.is_(None),
            Opportunity.won_at.is_(None),
            Opportunity.lost_at.is_(None),
            Opportunity.updated_at < cutoff,
            not_(recent_activity),
        )
        .order_by(Opportunity.updated_at.asc())
        .limit(CATEGORY_LIMIT)
    )
    predicate = visibility.filter_for(Opportunity)
    if predicate is not None:
        statement = statement.where(predicate)
    rows = (await session.execute(statement)).all()
    items: list[InsightRow] = []
    for opportunity, stage_name in rows:
        days = (now - opportunity.updated_at).days
        items.append(
            InsightRow(
                kind="STALE_OPPORTUNITY",
                severity="MEDIUM",
                title=f"{opportunity.name} has had no recorded activity in {days} days",
                detail=f"Stage: {stage_name}.",
                entity_type="OPPORTUNITY",
                entity_id=opportunity.id,
                entity_label=opportunity.name,
            )
        )
    return items


async def neglected_leads(
    session: AsyncSession, *, principal: Principal, now: dt.datetime | None = None
) -> list[InsightRow]:
    if not principal.has_permission("leads", PermissionAction.VIEW):
        return []
    now = now or dt.datetime.now(dt.UTC)
    cutoff = now - dt.timedelta(days=STALE_DAYS)
    min_age = now - dt.timedelta(days=LEAD_MIN_AGE_DAYS)
    visibility = RecordVisibility.for_module(principal, "leads")

    recent_activity = (
        select(Activity.id)
        .where(
            Activity.organization_id == Lead.organization_id,
            Activity.related_entity_type == CrmEntityType.LEAD,
            Activity.related_entity_id == Lead.id,
            Activity.created_at >= cutoff,
        )
        .correlate(Lead)
        .exists()
    )
    statement = (
        select(Lead)
        .where(
            Lead.organization_id == principal.organization_id,
            Lead.deleted_at.is_(None),
            Lead.status.not_in(_INACTIVE_LEAD_STATUSES),
            Lead.created_at <= min_age,
            not_(recent_activity),
        )
        .order_by(Lead.created_at.asc())
        .limit(CATEGORY_LIMIT)
    )
    predicate = visibility.filter_for(Lead)
    if predicate is not None:
        statement = statement.where(predicate)
    rows = (await session.execute(statement)).scalars().all()
    items: list[InsightRow] = []
    for lead in rows:
        name = f"{lead.first_name} {lead.last_name}".strip()
        days = (now - lead.created_at).days
        items.append(
            InsightRow(
                kind="NEGLECTED_LEAD",
                severity="MEDIUM",
                title=f"{name} has not been contacted in {days} days",
                detail=f"Status: {lead.status.value.replace('_', ' ').title()}.",
                entity_type="LEAD",
                entity_id=lead.id,
                entity_label=name or (lead.company or "Lead"),
            )
        )
    return items


async def accounts_needing_attention(
    session: AsyncSession, *, principal: Principal, now: dt.datetime | None = None
) -> list[InsightRow]:
    if not principal.has_permission("accounts", PermissionAction.VIEW):
        return []
    now = now or dt.datetime.now(dt.UTC)
    cutoff = now - dt.timedelta(days=ACCOUNT_QUIET_DAYS)
    visibility = RecordVisibility.for_module(principal, "accounts")

    recent_activity = (
        select(Activity.id)
        .where(
            Activity.organization_id == Account.organization_id,
            Activity.related_entity_type == CrmEntityType.ACCOUNT,
            Activity.related_entity_id == Account.id,
            Activity.created_at >= cutoff,
        )
        .correlate(Account)
        .exists()
    )
    statement = (
        select(Account)
        .where(
            Account.organization_id == principal.organization_id,
            Account.deleted_at.is_(None),
            Account.status == AccountStatus.ACTIVE,
            Account.updated_at < cutoff,
            not_(recent_activity),
        )
        .order_by(Account.updated_at.asc())
        .limit(CATEGORY_LIMIT)
    )
    predicate = visibility.filter_for(Account)
    if predicate is not None:
        statement = statement.where(predicate)
    rows = (await session.execute(statement)).scalars().all()
    items: list[InsightRow] = []
    for account in rows:
        days = (now - account.updated_at).days
        items.append(
            InsightRow(
                kind="ACCOUNT_NEEDS_ATTENTION",
                severity="LOW",
                title=f"{account.name} has had no recorded activity in {days} days",
                detail="Status: Active.",
                entity_type="ACCOUNT",
                entity_id=account.id,
                entity_label=account.name,
            )
        )
    return items


async def overdue_tasks(
    session: AsyncSession, *, principal: Principal, now: dt.datetime | None = None
) -> list[InsightRow]:
    if not principal.has_permission("tasks", PermissionAction.VIEW):
        return []
    now = now or dt.datetime.now(dt.UTC)
    visibility = RecordVisibility.for_module(principal, "tasks")
    statement = (
        select(Task)
        .where(
            Task.organization_id == principal.organization_id,
            Task.deleted_at.is_(None),
            Task.status.in_(_OPEN_TASK_STATUSES),
            Task.due_date.is_not(None),
            Task.due_date < now,
        )
        .order_by(Task.due_date.asc())
        .limit(CATEGORY_LIMIT)
    )
    predicate = visibility.filter_for(Task)
    if predicate is not None:
        statement = statement.where(predicate)
    rows = (await session.execute(statement)).scalars().all()
    items: list[InsightRow] = []
    for task in rows:
        assert task.due_date is not None  # noqa: S101 - filtered by the query above
        days = (now - task.due_date).days
        items.append(
            InsightRow(
                kind="OVERDUE_TASK",
                severity="HIGH" if days >= 3 else "MEDIUM",
                title=f"{task.title} is {days} day(s) overdue",
                detail=f"Priority: {task.priority.value.title()}." if task.priority else "",
                entity_type="TASK",
                entity_id=task.id,
                entity_label=task.title,
            )
        )
    return items


__all__ = [
    "ACCOUNT_QUIET_DAYS",
    "CATEGORY_LIMIT",
    "STALE_DAYS",
    "InsightRow",
    "accounts_needing_attention",
    "deals_at_risk",
    "neglected_leads",
    "overdue_tasks",
    "stale_opportunities",
]
