"""Pydantic contracts for the CRM dashboard summary.

One response feeds the whole dashboard. A single round trip is deliberate: the
page renders as a unit, and six parallel requests would each pay the same
authentication, membership and tenant-scoping cost.

Every field here is derived from real rows in the caller's organization. Where
the existing data model cannot truthfully support something the UI shows, the
field is absent rather than invented — see the module docstring in
``service.py``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.products.crm.dashboard.models import DASHBOARD_GRID_COLUMNS, ComponentDisplay
from app.products.crm.reports.models import ShareScope
from app.products.crm.reports.schemas import ReportResult


class DashboardKpis(BaseModel):
    """The headline counters."""

    #: Leads created within the trailing window (see ``NEW_LEAD_WINDOW_DAYS``).
    new_leads: int
    #: Leads currently sitting at QUALIFIED.
    qualified_leads: int
    #: Opportunities that are neither won nor lost.
    open_opportunities: int
    #: Summed ``deal_value`` of those open opportunities.
    pipeline_value: Decimal
    #: Activities of type MEETING scheduled for today.
    meetings_today: int
    #: Incomplete tasks due today or earlier.
    tasks_due: int
    #: Of ``tasks_due``, how many are HIGH priority — backs the card's subtitle.
    tasks_due_high_priority: int
    #: Of ``open_opportunities``, how many close within the next 30 days.
    opportunities_closing_soon: int
    #: Checkpoint 5. Open pipeline, each deal counted at its own
    #: ``win_probability`` — see ``DashboardRepository.sum_weighted_pipeline_value``
    #: for why an unset probability contributes zero rather than a guess.
    weighted_pipeline_value: Decimal
    #: Checkpoint 5. Value of deals won in the trailing ``NEW_LEAD_WINDOW_DAYS``
    #: window — the same window ``new_leads`` uses, so the two "since when" on
    #: one screen agree.
    won_revenue: Decimal
    #: Checkpoint 5. Share of this caller's live leads that have converted,
    #: 0-100, all-time.
    lead_conversion_rate: float


class PipelineStageSummary(BaseModel):
    """One open stage of the organization's pipeline, with its loaded value."""

    stage_id: uuid.UUID
    name: str
    sort_order: int
    count: int
    value: Decimal


class DashboardTask(BaseModel):
    """An open task assigned within the organization."""

    id: uuid.UUID
    title: str
    description: str | None
    priority: str
    status: str
    due_date: dt.datetime | None
    completed: bool


class DashboardMeeting(BaseModel):
    """An upcoming meeting, resolved from an activity of type MEETING."""

    id: uuid.UUID
    title: str
    start_time: dt.datetime | None
    end_time: dt.datetime | None
    #: Name of the record the meeting hangs off, when one is linked.
    related_label: str | None


class DashboardActivity(BaseModel):
    """A recent interaction, newest first."""

    id: uuid.UUID
    type: str
    subject: str
    detail: str | None
    occurred_at: dt.datetime


class RevenueMonth(BaseModel):
    """One point of the won-revenue trend (Checkpoint 5)."""

    month: dt.date
    value: Decimal


class OwnerPipelineSummary(BaseModel):
    """One owner's open pipeline (Checkpoint 5)."""

    #: A display name, resolved the same way a report's ``PERSON`` column is —
    #: never a raw id. ``"Unassigned"`` for opportunities with no owner.
    owner: str
    count: int
    value: Decimal


class LeadSourcePerformance(BaseModel):
    """One lead source's funnel (Checkpoint 5).

    Mirrors ``reports.catalog``'s ``lead-conversion-by-source`` row shape —
    deliberately, since ``DashboardService.summary`` computes this by calling
    that report's own repository method rather than a second query. See
    ``dashboard.service`` for why.
    """

    source: str
    leads: int
    converted: int
    conversion_rate: float


class DashboardSummary(BaseModel):
    """Everything the dashboard renders, for one organization."""

    kpis: DashboardKpis
    pipeline: list[PipelineStageSummary]
    pipeline_total: Decimal
    #: ISO code the totals are denominated in, or ``None`` when the open deals
    #: use more than one currency and no single symbol would be truthful.
    pipeline_currency: str | None
    tasks: list[DashboardTask]
    meetings: list[DashboardMeeting]
    activities: list[DashboardActivity]
    #: Checkpoint 5. Won revenue for the trailing 6 calendar months, oldest
    #: first, zero-filled — see ``DashboardRepository.won_revenue_by_month``.
    revenue_trend: list[RevenueMonth]
    #: Checkpoint 5. Open pipeline per owner, busiest first, capped at 10.
    pipeline_by_owner: list[OwnerPipelineSummary]
    #: Checkpoint 5. How each lead source is performing, by volume.
    lead_source_performance: list[LeadSourcePerformance]


# ---------------------------------------------------------------------------
# Configurable dashboards
# ---------------------------------------------------------------------------


class DashboardCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    visibility: ShareScope = ShareScope.PRIVATE
    is_default: bool = False


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    visibility: ShareScope | None = None
    is_default: bool | None = None


class DashboardComponentCreate(BaseModel):
    saved_report_id: uuid.UUID
    title: str | None = Field(default=None, max_length=120)
    display: ComponentDisplay = ComponentDisplay.CHART
    width: int = Field(default=6, ge=1, le=DASHBOARD_GRID_COLUMNS)
    #: Omitted means "append". Explicit positions are for a client restoring a
    #: known layout, not for ordinary tile creation.
    sort_order: int | None = Field(default=None, ge=0)


class DashboardComponentUpdate(BaseModel):
    saved_report_id: uuid.UUID | None = None
    title: str | None = Field(default=None, max_length=120)
    display: ComponentDisplay | None = None
    width: int | None = Field(default=None, ge=1, le=DASHBOARD_GRID_COLUMNS)
    sort_order: int | None = Field(default=None, ge=0)


class DashboardReorder(BaseModel):
    """The complete new order, as tile ids.

    Whole-list rather than a set of moves: a drag that shifts one tile changes
    the index of every tile after it, and applying that as N patches would be
    both chatty and non-atomic.
    """

    order: list[uuid.UUID] = Field(min_length=1)


class DashboardComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dashboard_id: uuid.UUID
    saved_report_id: uuid.UUID
    title: str | None
    display: ComponentDisplay
    sort_order: int
    width: int


class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID | None
    visibility: ShareScope
    is_default: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class DashboardDetail(DashboardResponse):
    """A dashboard and its layout, without running anything."""

    components: list[DashboardComponentResponse]


class DashboardComponentData(BaseModel):
    """One rendered tile.

    Exactly one of ``result`` and ``unavailable`` is set. ``unavailable`` is a
    short code rather than a sentence so the client can phrase it — and so the
    server never composes a message that might describe data the viewer cannot
    see.
    """

    id: uuid.UUID
    saved_report_id: uuid.UUID
    title: str
    display: ComponentDisplay
    sort_order: int
    width: int
    result: ReportResult | None = None
    unavailable: str | None = None
    #: Checkpoint 5. Whether a dashboard-wide date filter (see
    #: ``GET /boards/{id}/data?date_from=&date_to=``) was actually applied to
    #: this tile. A tile whose report has no date dimension — ``lead-funnel``,
    #: any report with ``accepts_date_range=False``, a custom report with no
    #: ``date_field`` — ignores the dashboard filter rather than erroring,
    #: and this is how the UI tells "unaffected" apart from "no filter was
    #: set" instead of leaving every viewer to guess from the numbers alone.
    date_filter_applied: bool = False


class DashboardData(BaseModel):
    """A dashboard with every tile run as the caller."""

    id: uuid.UUID
    name: str
    description: str | None
    generated_at: dt.datetime
    components: list[DashboardComponentData]


__all__ = [
    "DashboardActivity",
    "DashboardComponentCreate",
    "DashboardComponentData",
    "DashboardComponentResponse",
    "DashboardComponentUpdate",
    "DashboardCreate",
    "DashboardData",
    "DashboardDetail",
    "DashboardKpis",
    "DashboardMeeting",
    "DashboardReorder",
    "DashboardResponse",
    "DashboardSummary",
    "DashboardTask",
    "DashboardUpdate",
    "LeadSourcePerformance",
    "OwnerPipelineSummary",
    "PipelineStageSummary",
    "RevenueMonth",
]
