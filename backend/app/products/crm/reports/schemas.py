"""Pydantic v2 contracts for the reports module.

A report result is deliberately *not* the paginated envelope every list
endpoint returns. A list is a page of one entity; a report is a small,
whole, self-describing table — its columns vary by report, its rows are
already aggregated, and paging through nine rows of a funnel would be
ceremony without a purpose. The shape carries its own column metadata so the
frontend can render any report, including ones added later, without knowing
their names.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.products.crm.reports.models import ReportPeriod, ShareScope


class ReportColumnInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    type: str


class ChartInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    category_key: str
    value_key: str


class ReportSummary(BaseModel):
    """One entry in the report catalogue."""

    key: str
    name: str
    description: str
    category: str
    module: str
    accepts_date_range: bool
    chart: ChartInfo | None


class ReportRunRequest(BaseModel):
    """Parameters a report is run with.

    Both dates are optional and inclusive. A report whose
    ``accepts_date_range`` is false ignores them rather than rejecting the
    request: the same saved parameters may be replayed against several
    reports, and failing one of them for carrying a harmless field would be
    the less useful behaviour.
    """

    date_from: dt.date | None = None
    date_to: dt.date | None = None

    @model_validator(mode="after")
    def _ordered(self) -> ReportRunRequest:
        if self.date_from and self.date_to and self.date_to < self.date_from:
            msg = "date_to must not be earlier than date_from."
            raise ValueError(msg)
        return self


class ReportResult(BaseModel):
    """A rendered report: what it is, what its columns mean, and its rows."""

    key: str
    name: str
    description: str
    category: str
    generated_at: dt.datetime
    columns: list[ReportColumnInfo]
    #: Values are JSON scalars — numbers, strings, dates, or null. Keys are
    #: exactly the column keys above.
    rows: list[dict[str, Any]]
    #: Column-key to total, for the columns the definition marks summable.
    #: Empty when the report has no meaningful totals (a funnel's stages do
    #: not add up to anything).
    totals: dict[str, Any] = Field(default_factory=dict)
    chart: ChartInfo | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    #: True when the query hit its row ceiling and the table is a prefix
    #: rather than the whole answer. The UI says so rather than implying a
    #: complete picture.
    row_limit_reached: bool = False


# ---------------------------------------------------------------------------
# The saved-report library
# ---------------------------------------------------------------------------


class ReportFolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ReportFolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ReportFolderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime


class SavedReportBase(BaseModel):
    """Fields shared by create and update, with the period rule stated once."""

    @model_validator(mode="after")
    def _custom_period_needs_dates(self) -> SavedReportBase:
        """``CUSTOM`` without dates is a report that silently means ALL_TIME.

        Rejected at the edge rather than normalised, because the two are
        different intentions and guessing which one was meant is how a saved
        report ends up quietly reporting the wrong window.
        """
        period = getattr(self, "period", None)
        date_from = getattr(self, "date_from", None)
        date_to = getattr(self, "date_to", None)
        if period == ReportPeriod.CUSTOM and date_from is None and date_to is None:
            msg = "A custom period needs date_from, date_to, or both."
            raise ValueError(msg)
        if date_from and date_to and date_to < date_from:
            msg = "date_to must not be earlier than date_from."
            raise ValueError(msg)
        return self


class SavedReportCreate(SavedReportBase):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_report_key: str = Field(min_length=1, max_length=64)
    folder_id: uuid.UUID | None = None
    period: ReportPeriod = ReportPeriod.ALL_TIME
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    visibility: ShareScope = ShareScope.PRIVATE


class SavedReportUpdate(SavedReportBase):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_report_key: str | None = Field(default=None, min_length=1, max_length=64)
    folder_id: uuid.UUID | None = None
    period: ReportPeriod | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    visibility: ShareScope | None = None


class SavedReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    base_report_key: str
    folder_id: uuid.UUID | None
    period: ReportPeriod
    date_from: dt.date | None
    date_to: dt.date | None
    owner_id: uuid.UUID | None
    visibility: ShareScope
    created_at: dt.datetime
    updated_at: dt.datetime


__all__ = [
    "ChartInfo",
    "ReportColumnInfo",
    "ReportFolderCreate",
    "ReportFolderResponse",
    "ReportFolderUpdate",
    "ReportResult",
    "ReportRunRequest",
    "ReportSummary",
    "SavedReportCreate",
    "SavedReportResponse",
    "SavedReportUpdate",
]
