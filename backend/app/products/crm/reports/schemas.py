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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.products.crm.reports.conditions import ReportFilterGroup
from app.products.crm.reports.fields import AggOp, DateInterval, ReportEntity
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
# Custom (ad-hoc) reports — the report builder's own definition shape
# ---------------------------------------------------------------------------


class ReportAggregation(BaseModel):
    """One summary column: ``COUNT()`` needs no field, everything else does."""

    field: str | None = Field(default=None, max_length=80)
    op: AggOp

    @model_validator(mode="after")
    def _field_required_unless_count(self) -> ReportAggregation:
        if self.op is not AggOp.COUNT and self.field is None:
            msg = f"'{self.op.value}' needs a field to aggregate."
            raise ValueError(msg)
        return self


class CustomReportDefinition(BaseModel):
    """A user-authored report: entity, shape, filters — never SQL.

    Two output shapes, chosen by whether ``group_by`` is set:

    * **Grouped** — one row per distinct value of ``group_by`` (or per
      ``group_by_interval`` bucket, for a date field), with one column per
      entry in ``aggregations``. ``fields`` is ignored.
    * **Row listing** — one row per record, showing exactly ``fields``, sorted
      and capped the same way the built-in catalogue's row-per-record reports
      are (see ``reports.repository.MAX_REPORT_ROWS``). ``aggregations`` is
      ignored.
    """

    entity: ReportEntity
    fields: list[str] = Field(default_factory=list, max_length=20)
    filters: ReportFilterGroup | None = None
    group_by: str | None = Field(default=None, max_length=80)
    group_by_interval: DateInterval | None = None
    aggregations: list[ReportAggregation] = Field(default_factory=list, max_length=10)
    sort_by: str | None = Field(default=None, max_length=80)
    sort_dir: Literal["asc", "desc"] = "asc"
    #: Which date-typed field ``date_from``/``date_to`` narrow by. Defaults to
    #: ``reports.fields.DEFAULT_DATE_FIELD`` (``created_at``) when unset.
    date_field: str | None = Field(default=None, max_length=80)
    chart_kind: Literal["BAR", "DONUT", "FUNNEL"] | None = None

    @model_validator(mode="after")
    def _shape_is_coherent(self) -> CustomReportDefinition:
        if self.group_by is None:
            if self.group_by_interval is not None:
                msg = "group_by_interval needs a group_by field."
                raise ValueError(msg)
            if self.chart_kind is not None:
                msg = "A chart needs group_by — a row listing has no category axis."
                raise ValueError(msg)
            if not self.fields:
                msg = "Select at least one field, or set group_by to summarise instead."
                raise ValueError(msg)
        elif not self.aggregations:
            msg = "A grouped report needs at least one aggregation."
            raise ValueError(msg)
        return self


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
    #: Exactly one of these two must be set — see ``_exactly_one_definition``.
    base_report_key: str | None = Field(default=None, min_length=1, max_length=64)
    custom_definition: CustomReportDefinition | None = None
    folder_id: uuid.UUID | None = None
    period: ReportPeriod = ReportPeriod.ALL_TIME
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    visibility: ShareScope = ShareScope.PRIVATE

    @model_validator(mode="after")
    def _exactly_one_definition(self) -> SavedReportCreate:
        if (self.base_report_key is None) == (self.custom_definition is None):
            msg = "A saved report needs exactly one of base_report_key or custom_definition."
            raise ValueError(msg)
        return self


class SavedReportUpdate(SavedReportBase):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_report_key: str | None = Field(default=None, min_length=1, max_length=64)
    custom_definition: CustomReportDefinition | None = None
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
    base_report_key: str | None
    custom_definition: CustomReportDefinition | None
    folder_id: uuid.UUID | None
    period: ReportPeriod
    date_from: dt.date | None
    date_to: dt.date | None
    owner_id: uuid.UUID | None
    visibility: ShareScope
    created_at: dt.datetime
    updated_at: dt.datetime


class AvailableFieldInfo(BaseModel):
    """One field a custom report over an entity may select, filter or group by.

    Mirrors ``layouts.schemas.AvailableFieldInfo`` in spirit — a field, its
    label, and whether it is a tenant-defined one — with the extra capability
    flags a report builder needs that a form builder does not.
    """

    key: str
    label: str
    type: str
    is_custom: bool
    filterable: bool
    groupable: bool
    sortable: bool
    aggregations: list[str]


class CustomReportPreviewRequest(BaseModel):
    """Run a definition that has not been saved yet — the builder's preview step."""

    definition: CustomReportDefinition
    date_from: dt.date | None = None
    date_to: dt.date | None = None


__all__ = [
    "AvailableFieldInfo",
    "ChartInfo",
    "CustomReportDefinition",
    "CustomReportPreviewRequest",
    "ReportAggregation",
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
