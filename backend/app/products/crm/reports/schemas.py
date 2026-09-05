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
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


__all__ = [
    "ChartInfo",
    "ReportColumnInfo",
    "ReportResult",
    "ReportRunRequest",
    "ReportSummary",
]
