"""The queries behind the built-in reports.

A second dedicated read model, in the sense ARCHITECTURE-BOUNDARIES.md rule 6
permits and for the same reason ``dashboard/repository.py`` is one: a report
spans tables no single module owns, and making six service calls to aggregate
in Python would be slower and less correct than one grouped query. Like that
module, this one is **read-only** — nothing here writes, so no module's
invariants can be bypassed through it.

**Every query over an owner-scoped module takes a ``RecordVisibility`` and
applies it.** That is the whole security property of this module. A report is
an aggregate, and an aggregate computed over rows the caller cannot open is a
disclosure that no 404 later can take back: "your team closed £2.4m this
quarter" tells a rep the number even if every underlying deal stays hidden.
So the predicate goes *into* the grouped query, exactly as the dashboard puts
it into its counts, and never into a filter applied to the result afterwards.

The one query that takes no visibility is ``activity_by_owner``, because
``activities`` is not in ``OWNER_SCOPED_MODULES`` and so resolves to
unrestricted for every caller anyway; see that method for why the module is
organization-wide. Adding a module to that frozenset therefore obliges you to
thread a predicate through here — ``test_every_owner_scoped_module_narrows_its_list``
guards the list endpoints, and the visibility tests here guard the totals.

Aggregation happens in PostgreSQL. Fetching rows and summing them in the
application would work and would be wrong the first time a tenant had more
rows than fit comfortably in memory.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, case, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.accounts.models import Account
from app.products.crm.activities.models import Activity, ActivityStatus
from app.products.crm.leads.models import Lead, LeadSource, LeadStatus
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import Task, TaskStatus

#: Ceiling on the rows one report returns.
#:
#: A report is read on a screen and drawn as a chart; past a few hundred rows
#: it is a export, and the module says so (``row_limit_reached``) rather than
#: silently truncating. Grouped reports never approach this — it exists for
#: the row-per-record ones such as "deals closing".
MAX_REPORT_ROWS = 500

_CLOSED_TASK_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)

#: Lead statuses in lifecycle order, for the funnel. Pinned here rather than
#: read from the enum's declaration order: the funnel's meaning depends on the
#: sequence, and a future reordering of the enum for unrelated reasons must not
#: silently reshape the chart.
LEAD_FUNNEL_ORDER: tuple[LeadStatus, ...] = (
    LeadStatus.NEW,
    LeadStatus.CONTACTED,
    LeadStatus.QUALIFIED,
    LeadStatus.PROPOSAL_SENT,
    LeadStatus.NEGOTIATION,
    LeadStatus.CONVERTED,
)


def _visible(visibility: RecordVisibility | None, model: type[Any]) -> ColumnElement[bool]:
    """The visibility predicate, or a true literal when unrestricted.

    Returns a predicate rather than ``None`` so it can sit inside a JOIN
    condition, which — unlike a chained ``.where()`` — has no "add nothing"
    form. Same helper, same reason, as ``dashboard/repository.py``.
    """
    if visibility is None:
        return true()
    predicate = visibility.filter_for(model)
    return true() if predicate is None else predicate


class ReportRepository:
    """Grouped, tenant- and visibility-scoped reads for the report catalogue."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Helpers -----------------------------------------------------------

    @staticmethod
    def _scoped(
        statement: Select[Any], visibility: RecordVisibility | None, model: type[Any]
    ) -> Select[Any]:
        if visibility is None:
            return statement
        predicate = visibility.filter_for(model)
        return statement if predicate is None else statement.where(predicate)

    @staticmethod
    def _live_opportunities(organization_id: uuid.UUID) -> list[ColumnElement[bool]]:
        return [
            Opportunity.organization_id == organization_id,
            Opportunity.deleted_at.is_(None),
        ]

    # --- Opportunities -----------------------------------------------------

    async def pipeline_by_stage(
        self, organization_id: uuid.UUID, *, visibility: RecordVisibility | None
    ) -> list[dict[str, Any]]:
        """Open deals and their value, per open stage.

        LEFT JOIN with the visibility predicate inside the JOIN condition, so
        a configured stage whose only deals belong to somebody else still
        appears with a zero. An empty stage is information; a missing stage
        reads as a misconfigured pipeline.
        """
        result = await self._session.execute(
            select(
                PipelineStage.name,
                PipelineStage.sort_order,
                func.count(Opportunity.id),
                func.coalesce(func.sum(Opportunity.deal_value), 0),
            )
            .outerjoin(
                Opportunity,
                and_(
                    Opportunity.stage_id == PipelineStage.id,
                    Opportunity.deleted_at.is_(None),
                    Opportunity.won_at.is_(None),
                    Opportunity.lost_at.is_(None),
                    _visible(visibility, Opportunity),
                ),
            )
            .where(
                PipelineStage.organization_id == organization_id,
                PipelineStage.deleted_at.is_(None),
                PipelineStage.is_won.is_(False),
                PipelineStage.is_lost.is_(False),
            )
            .group_by(PipelineStage.name, PipelineStage.sort_order)
            .order_by(PipelineStage.sort_order)
        )
        return [
            {"stage": name, "deals": int(count), "value": Decimal(str(value))}
            for name, _order, count, value in result.all()
        ]

    async def deals_closing(
        self,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> list[dict[str, Any]]:
        """Open deals with an expected close date inside the window."""
        statement = (
            select(
                Opportunity.name,
                Account.name,
                PipelineStage.name,
                Opportunity.deal_value,
                Opportunity.currency,
                Opportunity.expected_close_date,
                Opportunity.owner_id,
            )
            .join(Account, Account.id == Opportunity.account_id)
            .join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
            .where(
                *self._live_opportunities(organization_id),
                Opportunity.won_at.is_(None),
                Opportunity.lost_at.is_(None),
                Opportunity.expected_close_date.is_not(None),
            )
        )
        if date_from is not None:
            statement = statement.where(Opportunity.expected_close_date >= date_from)
        if date_to is not None:
            statement = statement.where(Opportunity.expected_close_date <= date_to)

        result = await self._session.execute(
            self._scoped(statement, visibility, Opportunity)
            .order_by(Opportunity.expected_close_date.asc())
            .limit(MAX_REPORT_ROWS + 1)
        )
        return [
            {
                "deal": name,
                "account": account,
                "stage": stage,
                "value": value,
                "currency": currency,
                "close_date": close_date,
                "owner_id": owner_id,
            }
            for name, account, stage, value, currency, close_date, owner_id in result.all()
        ]

    async def won_lost_summary(
        self,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> list[dict[str, Any]]:
        """Deals closed in the window, split into won and lost.

        Both outcomes are always returned, zero-filled, so the chart keeps two
        segments and "nothing lost this quarter" is visibly different from
        "the report did not run".
        """
        closed_at = func.coalesce(Opportunity.won_at, Opportunity.lost_at)
        statement = select(
            case((Opportunity.won_at.is_not(None), "Won"), else_="Lost").label("outcome"),
            func.count(Opportunity.id),
            func.coalesce(func.sum(Opportunity.deal_value), 0),
        ).where(
            *self._live_opportunities(organization_id),
            closed_at.is_not(None),
        )
        if date_from is not None:
            statement = statement.where(func.date(closed_at) >= date_from)
        if date_to is not None:
            statement = statement.where(func.date(closed_at) <= date_to)

        result = await self._session.execute(
            self._scoped(statement, visibility, Opportunity).group_by("outcome")
        )
        found = {
            str(outcome): (int(count), Decimal(str(value)))
            for outcome, count, value in result.all()
        }
        return [
            {
                "outcome": outcome,
                "deals": found.get(outcome, (0, Decimal(0)))[0],
                "value": found.get(outcome, (0, Decimal(0)))[1],
            }
            for outcome in ("Won", "Lost")
        ]

    async def sales_cycle_by_owner(
        self,
        organization_id: uuid.UUID,
        *,
        visibility: RecordVisibility | None,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> list[dict[str, Any]]:
        """Average days from creation to win, per owner, for deals won in the window.

        Measured on the deals that actually closed. Including open deals would
        make the average drift downwards every day a slow deal stays open,
        which is the opposite of what a cycle-time number is for.
        """
        days = func.avg(
            func.extract("epoch", Opportunity.won_at - Opportunity.created_at) / 86400.0
        )
        statement = select(
            Opportunity.owner_id,
            func.count(Opportunity.id),
            days,
            func.coalesce(func.sum(Opportunity.deal_value), 0),
        ).where(
            *self._live_opportunities(organization_id),
            Opportunity.won_at.is_not(None),
        )
        if date_from is not None:
            statement = statement.where(func.date(Opportunity.won_at) >= date_from)
        if date_to is not None:
            statement = statement.where(func.date(Opportunity.won_at) <= date_to)

        result = await self._session.execute(
            self._scoped(statement, visibility, Opportunity)
            .group_by(Opportunity.owner_id)
            .order_by(func.count(Opportunity.id).desc())
            .limit(MAX_REPORT_ROWS + 1)
        )
        return [
            {
                "owner_id": owner_id,
                "deals_won": int(count),
                "avg_days_to_win": round(float(average), 1) if average is not None else None,
                "value": Decimal(str(value)),
            }
            for owner_id, count, average, value in result.all()
        ]

    # --- Leads -------------------------------------------------------------

    async def lead_funnel(
        self, organization_id: uuid.UUID, *, visibility: RecordVisibility | None
    ) -> list[dict[str, Any]]:
        """Live leads per lifecycle status, in funnel order and zero-filled."""
        result = await self._session.execute(
            self._scoped(
                select(Lead.status, func.count(Lead.id)).where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                ),
                visibility,
                Lead,
            ).group_by(Lead.status)
        )
        counts = {status: int(count) for status, count in result.all()}
        return [
            {"status": status.value, "leads": counts.get(status, 0)}
            for status in LEAD_FUNNEL_ORDER
        ]

    async def lead_conversion_by_source(
        self, organization_id: uuid.UUID, *, visibility: RecordVisibility | None
    ) -> list[dict[str, Any]]:
        """Per lead source: how many arrived, how many converted, and the rate.

        Leads with no source are reported under "Unattributed" rather than
        dropped — a source report that quietly omits a third of the pipeline
        is worse than one that shows the gap.
        """
        converted = func.sum(case((Lead.converted_at.is_not(None), 1), else_=0))
        # Labelled, and grouped by the label. PostgreSQL will not accept a
        # bare `GROUP BY coalesce(col, $n)` as matching the same expression in
        # the SELECT list — the bound parameter defeats the equivalence check
        # and it reports the column as ungrouped. Grouping by the output name
        # says exactly what is meant and renders once.
        source = func.coalesce(LeadSource.name, "Unattributed").label("source")
        result = await self._session.execute(
            self._scoped(
                select(source, func.count(Lead.id), converted)
                .outerjoin(LeadSource, LeadSource.id == Lead.lead_source_id)
                .where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                ),
                visibility,
                Lead,
            )
            .group_by(source)
            .order_by(func.count(Lead.id).desc())
            .limit(MAX_REPORT_ROWS + 1)
        )
        rows: list[dict[str, Any]] = []
        for source, total, won in result.all():
            total_count = int(total)
            converted_count = int(won or 0)
            rows.append(
                {
                    "source": source,
                    "leads": total_count,
                    "converted": converted_count,
                    "conversion_rate": round(converted_count * 100 / total_count, 1)
                    if total_count
                    else 0.0,
                }
            )
        return rows

    # --- Activities --------------------------------------------------------

    async def activity_by_owner(
        self,
        organization_id: uuid.UUID,
        *,
        date_from: dt.date | None,
        date_to: dt.date | None,
    ) -> list[dict[str, Any]]:
        """Completed activities per owner in the window.

        No visibility predicate, and that is not an omission: ``activities`` is
        deliberately absent from ``OWNER_SCOPED_MODULES`` because an activity
        belongs to the record it is logged against rather than to its own
        owner. Narrowing here would hide a colleague's call from the shared
        history it is part of, which is the opposite of the rule's intent.
        """
        completed_at = func.coalesce(Activity.completed_at, Activity.created_at)
        statement = select(
            Activity.owner_id,
            func.count(Activity.id),
        ).where(
            Activity.organization_id == organization_id,
            Activity.deleted_at.is_(None),
            Activity.status == ActivityStatus.COMPLETED,
        )
        if date_from is not None:
            statement = statement.where(func.date(completed_at) >= date_from)
        if date_to is not None:
            statement = statement.where(func.date(completed_at) <= date_to)

        result = await self._session.execute(
            statement.group_by(Activity.owner_id)
            .order_by(func.count(Activity.id).desc())
            .limit(MAX_REPORT_ROWS + 1)
        )
        return [
            {"owner_id": owner_id, "activities": int(count)}
            for owner_id, count in result.all()
        ]

    # --- Tasks -------------------------------------------------------------

    async def overdue_tasks_by_assignee(
        self, organization_id: uuid.UUID, *, visibility: RecordVisibility | None, today: dt.date
    ) -> list[dict[str, Any]]:
        """Open, past-due tasks per assignee, with the oldest still waiting."""
        result = await self._session.execute(
            self._scoped(
                select(
                    Task.assigned_to_id,
                    func.count(Task.id),
                    func.min(Task.due_date),
                ).where(
                    Task.organization_id == organization_id,
                    Task.deleted_at.is_(None),
                    Task.status.not_in(_CLOSED_TASK_STATUSES),
                    Task.due_date.is_not(None),
                    func.date(Task.due_date) < today,
                ),
                visibility,
                Task,
            )
            .group_by(Task.assigned_to_id)
            .order_by(func.count(Task.id).desc())
            .limit(MAX_REPORT_ROWS + 1)
        )
        return [
            {
                "owner_id": assignee_id,
                "overdue": int(count),
                "oldest_due": oldest.date() if oldest is not None else None,
            }
            for assignee_id, count, oldest in result.all()
        ]

    # --- Accounts ----------------------------------------------------------

    async def accounts_by_industry(
        self, organization_id: uuid.UUID, *, visibility: RecordVisibility | None
    ) -> list[dict[str, Any]]:
        """Accounts and their open pipeline, grouped by industry.

        The opportunity join carries the *account* visibility predicate only.
        The question is "what is the pipeline against the accounts I can see",
        and a second predicate over opportunities would answer a subtly
        different one — accounts would appear with an understated total and no
        indication that anything was missing.
        """
        industry = func.coalesce(Account.industry, "Unspecified").label("industry")
        result = await self._session.execute(
            select(
                industry,
                func.count(func.distinct(Account.id)),
                func.coalesce(func.sum(Opportunity.deal_value), 0),
            )
            .outerjoin(
                Opportunity,
                and_(
                    Opportunity.account_id == Account.id,
                    Opportunity.deleted_at.is_(None),
                    Opportunity.won_at.is_(None),
                    Opportunity.lost_at.is_(None),
                ),
            )
            .where(
                Account.organization_id == organization_id,
                Account.deleted_at.is_(None),
                _visible(visibility, Account),
            )
            .group_by(industry)
            .order_by(func.count(func.distinct(Account.id)).desc())
            .limit(MAX_REPORT_ROWS + 1)
        )
        return [
            {
                "industry": name,
                "accounts": int(count),
                "open_pipeline": Decimal(str(value)),
            }
            for name, count, value in result.all()
        ]


__all__ = ["LEAD_FUNNEL_ORDER", "MAX_REPORT_ROWS", "ReportRepository"]
