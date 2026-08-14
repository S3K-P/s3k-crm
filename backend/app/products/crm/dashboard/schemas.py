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

from pydantic import BaseModel


class DashboardKpis(BaseModel):
    """The six headline counters."""

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


__all__ = [
    "DashboardActivity",
    "DashboardKpis",
    "DashboardMeeting",
    "DashboardSummary",
    "DashboardTask",
    "PipelineStageSummary",
]
