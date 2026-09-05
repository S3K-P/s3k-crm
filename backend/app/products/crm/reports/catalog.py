"""What reports exist, and which query each one runs.

One table, nine rows. Each entry names the permission module it reads, the
columns it produces, how it should be drawn, and the repository call that
produces the rows — so adding a tenth report is an entry here plus one method
on :class:`~app.products.crm.reports.repository.ReportRepository`, and
nothing else.

**A report is reviewed code, not user-authored SQL.** The obvious alternative
was a generic builder: store a definition of module + columns + filters +
group-by and translate it at run time. That is the shape Zoho's report builder
has, and it is what "custom reports" will eventually need — but it means
composing SQL from values a client supplied, over tables whose row-level
visibility rules are the product's main security property. Every query here
was written once, read once, and applies ``RecordVisibility`` by construction.
A builder can be layered on later as a further definition kind; starting with
one would have meant securing dynamic SQL before shipping a single number.

**Why there is no ``reports`` permission module.** Reading a report *is*
reading the records it aggregates, so each entry declares the module it draws
from and the route requires ``<module>.VIEW`` against that. This is the same
call ``imports/catalog.py`` makes in the other direction — it requires
``<module>.CREATE`` rather than inventing an ``IMPORT`` action — and for the
same reason: a new action would mean a migration and a role change for every
existing tenant, to express a grant the module permission already covers. It
is also strictly more precise. A rep who cannot see opportunities cannot open
the pipeline report, without anyone having to keep two permissions in step.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.products.crm.reports.repository import ReportRepository
from app.products.crm.shared.visibility import RecordVisibility


class ColumnType(enum.StrEnum):
    """How a column should be formatted, and how a chart should treat it."""

    TEXT = "TEXT"
    #: A backend enum value — ``PROPOSAL_SENT`` — that the client renders in
    #: sentence case through its own ``humanize``. Distinct from ``TEXT``
    #: because plain text must be shown exactly as stored: an account named
    #: "Food & Beverage" would come back as "Food & beverage" if every string
    #: went through that helper.
    STATUS = "STATUS"
    NUMBER = "NUMBER"
    CURRENCY = "CURRENCY"
    PERCENT = "PERCENT"
    DATE = "DATE"
    #: A platform user id the service replaces with a display name before the
    #: response is built. Never reaches the client as a raw identifier.
    PERSON = "PERSON"


class ChartKind(enum.StrEnum):
    BAR = "BAR"
    DONUT = "DONUT"
    FUNNEL = "FUNNEL"


@dataclass(frozen=True, slots=True)
class ReportColumn:
    key: str
    label: str
    type: ColumnType


@dataclass(frozen=True, slots=True)
class ChartHint:
    """How the frontend should draw this report, if it should draw it at all.

    A hint rather than a rendering: the backend has no business knowing what a
    chart library wants, and a report with no hint is a table, which is a
    legitimate answer for a row-per-record listing.
    """

    kind: ChartKind
    #: Column supplying the category axis / segment label.
    category_key: str
    #: Column supplying the magnitude.
    value_key: str


@dataclass(frozen=True, slots=True)
class ReportContext:
    """Everything a runner needs that is not the repository itself.

    ``visibility`` is ``None`` only for a module that is organization-wide by
    definition; every owner-scoped report receives a resolved predicate and
    must pass it to its query.
    """

    organization_id: uuid.UUID
    visibility: RecordVisibility | None
    date_from: dt.date | None
    date_to: dt.date | None
    today: dt.date


Runner = Callable[[ReportRepository, ReportContext], Awaitable[list[dict[str, Any]]]]


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    """One built-in report."""

    #: URL segment and the value the frontend sends, e.g. ``pipeline-by-stage``.
    key: str
    name: str
    description: str
    #: Grouping for the report list. Presentation only.
    category: str
    #: Permission module. The route requires ``<module>.VIEW`` against this,
    #: and resolves ``RecordVisibility`` for the same module — so the rows in
    #: the aggregate are exactly the rows the caller could open one by one.
    module: str
    columns: tuple[ReportColumn, ...]
    run: Runner
    chart: ChartHint | None = None
    #: Whether the report narrows on the requested date window. Surfaced so
    #: the UI can hide a date picker that would do nothing.
    accepts_date_range: bool = False
    #: Columns to total in the summary row, if any.
    totals: tuple[str, ...] = field(default_factory=tuple)


# --- Runners ----------------------------------------------------------------
#
# Thin by design: each one adapts the context to a repository call. Anything
# more interesting than that belongs in the repository, where it can be read
# beside the query it modifies.


async def _pipeline_by_stage(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.pipeline_by_stage(
        context.organization_id, visibility=context.visibility
    )


async def _deals_closing(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.deals_closing(
        context.organization_id,
        visibility=context.visibility,
        date_from=context.date_from,
        date_to=context.date_to,
    )


async def _won_lost(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.won_lost_summary(
        context.organization_id,
        visibility=context.visibility,
        date_from=context.date_from,
        date_to=context.date_to,
    )


async def _sales_cycle(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.sales_cycle_by_owner(
        context.organization_id,
        visibility=context.visibility,
        date_from=context.date_from,
        date_to=context.date_to,
    )


async def _lead_funnel(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.lead_funnel(
        context.organization_id, visibility=context.visibility
    )


async def _lead_conversion_by_source(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.lead_conversion_by_source(
        context.organization_id, visibility=context.visibility
    )


async def _activity_by_owner(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.activity_by_owner(
        context.organization_id, date_from=context.date_from, date_to=context.date_to
    )


async def _overdue_tasks(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.overdue_tasks_by_assignee(
        context.organization_id, visibility=context.visibility, today=context.today
    )


async def _accounts_by_industry(
    repository: ReportRepository, context: ReportContext
) -> list[dict[str, Any]]:
    return await repository.accounts_by_industry(
        context.organization_id, visibility=context.visibility
    )


# --- The catalogue ----------------------------------------------------------

SALES_METRICS = "Sales metrics"
LEAD_METRICS = "Lead metrics"
ACTIVITY_METRICS = "Activity"

_DEFINITIONS: tuple[ReportDefinition, ...] = (
    ReportDefinition(
        key="pipeline-by-stage",
        name="Pipeline by stage",
        description="Open deals and their value in each stage of the pipeline.",
        category=SALES_METRICS,
        module="opportunities",
        columns=(
            ReportColumn("stage", "Stage", ColumnType.TEXT),
            ReportColumn("deals", "Deals", ColumnType.NUMBER),
            ReportColumn("value", "Value", ColumnType.CURRENCY),
        ),
        run=_pipeline_by_stage,
        chart=ChartHint(ChartKind.BAR, category_key="stage", value_key="value"),
        totals=("deals", "value"),
    ),
    ReportDefinition(
        key="deals-closing",
        name="Deals closing",
        description="Open deals with an expected close date in the selected period.",
        category=SALES_METRICS,
        module="opportunities",
        columns=(
            ReportColumn("deal", "Deal", ColumnType.TEXT),
            ReportColumn("account", "Account", ColumnType.TEXT),
            ReportColumn("stage", "Stage", ColumnType.TEXT),
            ReportColumn("owner_id", "Owner", ColumnType.PERSON),
            ReportColumn("close_date", "Close date", ColumnType.DATE),
            ReportColumn("value", "Value", ColumnType.CURRENCY),
            # Declared because this report lists rows rather than aggregating
            # them: a single deal has exactly one currency and can say so,
            # where the total underneath spans several and deliberately
            # carries no symbol.
            ReportColumn("currency", "Currency", ColumnType.TEXT),
        ),
        run=_deals_closing,
        accepts_date_range=True,
        totals=("value",),
    ),
    ReportDefinition(
        key="won-lost-summary",
        name="Won and lost",
        description="Deals closed in the selected period, by outcome.",
        category=SALES_METRICS,
        module="opportunities",
        columns=(
            ReportColumn("outcome", "Outcome", ColumnType.TEXT),
            ReportColumn("deals", "Deals", ColumnType.NUMBER),
            ReportColumn("value", "Value", ColumnType.CURRENCY),
        ),
        run=_won_lost,
        chart=ChartHint(ChartKind.DONUT, category_key="outcome", value_key="value"),
        accepts_date_range=True,
        totals=("deals", "value"),
    ),
    ReportDefinition(
        key="sales-cycle-by-owner",
        name="Sales cycle by owner",
        description="Average days from creation to win, for deals won in the period.",
        category=SALES_METRICS,
        module="opportunities",
        columns=(
            ReportColumn("owner_id", "Owner", ColumnType.PERSON),
            ReportColumn("deals_won", "Deals won", ColumnType.NUMBER),
            ReportColumn("avg_days_to_win", "Avg days to win", ColumnType.NUMBER),
            ReportColumn("value", "Value won", ColumnType.CURRENCY),
        ),
        run=_sales_cycle,
        chart=ChartHint(
            ChartKind.BAR, category_key="owner_id", value_key="avg_days_to_win"
        ),
        accepts_date_range=True,
        totals=("deals_won", "value"),
    ),
    ReportDefinition(
        key="lead-funnel",
        name="Lead funnel",
        description="Live leads at each stage of the lifecycle.",
        category=LEAD_METRICS,
        module="leads",
        columns=(
            ReportColumn("status", "Status", ColumnType.STATUS),
            ReportColumn("leads", "Leads", ColumnType.NUMBER),
        ),
        run=_lead_funnel,
        chart=ChartHint(ChartKind.FUNNEL, category_key="status", value_key="leads"),
    ),
    ReportDefinition(
        key="lead-conversion-by-source",
        name="Lead conversion by source",
        description="How many leads each source produced, and how many converted.",
        category=LEAD_METRICS,
        module="leads",
        columns=(
            ReportColumn("source", "Source", ColumnType.TEXT),
            ReportColumn("leads", "Leads", ColumnType.NUMBER),
            ReportColumn("converted", "Converted", ColumnType.NUMBER),
            ReportColumn("conversion_rate", "Conversion rate", ColumnType.PERCENT),
        ),
        run=_lead_conversion_by_source,
        chart=ChartHint(ChartKind.BAR, category_key="source", value_key="leads"),
        totals=("leads", "converted"),
    ),
    ReportDefinition(
        key="activity-by-owner",
        name="Activity by owner",
        description="Calls, meetings and other activities completed in the period.",
        category=ACTIVITY_METRICS,
        module="activities",
        columns=(
            ReportColumn("owner_id", "Owner", ColumnType.PERSON),
            ReportColumn("activities", "Completed", ColumnType.NUMBER),
        ),
        run=_activity_by_owner,
        chart=ChartHint(ChartKind.BAR, category_key="owner_id", value_key="activities"),
        accepts_date_range=True,
        totals=("activities",),
    ),
    ReportDefinition(
        key="overdue-tasks",
        name="Overdue tasks",
        description="Open tasks past their due date, by the person they sit with.",
        category=ACTIVITY_METRICS,
        module="tasks",
        columns=(
            ReportColumn("owner_id", "Assignee", ColumnType.PERSON),
            ReportColumn("overdue", "Overdue", ColumnType.NUMBER),
            ReportColumn("oldest_due", "Oldest due", ColumnType.DATE),
        ),
        run=_overdue_tasks,
        chart=ChartHint(ChartKind.BAR, category_key="owner_id", value_key="overdue"),
        totals=("overdue",),
    ),
    ReportDefinition(
        key="accounts-by-industry",
        name="Accounts by industry",
        description="Customer accounts and their open pipeline, grouped by industry.",
        category=SALES_METRICS,
        module="accounts",
        columns=(
            ReportColumn("industry", "Industry", ColumnType.TEXT),
            ReportColumn("accounts", "Accounts", ColumnType.NUMBER),
            ReportColumn("open_pipeline", "Open pipeline", ColumnType.CURRENCY),
        ),
        run=_accounts_by_industry,
        chart=ChartHint(ChartKind.BAR, category_key="industry", value_key="accounts"),
        totals=("accounts", "open_pipeline"),
    ),
)

REPORTS: dict[str, ReportDefinition] = {
    definition.key: definition for definition in _DEFINITIONS
}


def person_columns(definition: ReportDefinition) -> tuple[str, ...]:
    """Column keys holding a user id the service must resolve to a name."""
    return tuple(
        column.key for column in definition.columns if column.type is ColumnType.PERSON
    )


__all__ = [
    "REPORTS",
    "ChartHint",
    "ChartKind",
    "ColumnType",
    "ReportColumn",
    "ReportContext",
    "ReportDefinition",
    "person_columns",
]
