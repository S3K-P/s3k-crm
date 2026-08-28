"""Serialisation and the row cap, without a database.

The enforcement that matters — permission, visibility, audit — is proven at the
HTTP boundary in ``tests/integration/test_csv_export.py``. What is left here is
the part that is pure and would be tedious to reach through a request: how each
type renders, how a hostile cell is defused, and the ceiling that stops one
caller allocating the process's memory.
"""

from __future__ import annotations

import csv
import datetime as dt
import decimal
import enum
import io
import uuid
from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from app.products.crm.shared.csv_export import (
    EXPORT_ROW_LIMIT,
    ExportTooLargeError,
    collect_rows,
    content_disposition,
    render_csv,
)
from app.products.crm.shared.pagination import MAX_PAGE_SIZE, PageParams


class Colour(enum.StrEnum):
    RED = "RED"


class Row(BaseModel):
    id: uuid.UUID
    name: str
    amount: decimal.Decimal | None
    active: bool
    colour: Colour
    due: dt.date | None
    created_at: dt.datetime


def _row(**overrides: Any) -> Row:
    values: dict[str, Any] = {
        "id": uuid.UUID("01a04317-5adc-7627-a9be-2a63d12d9b52"),
        "name": "Acme",
        "amount": decimal.Decimal("1234.50"),
        "active": True,
        "colour": Colour.RED,
        "due": dt.date(2026, 8, 28),
        "created_at": dt.datetime(2026, 8, 28, 9, 30, tzinfo=dt.UTC),
    }
    values.update(overrides)
    return Row(**values)


def _parsed(rows: Sequence[Row]) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(render_csv(rows, Row))))


# --- Columns ----------------------------------------------------------------


def test_the_header_is_the_schemas_fields_in_order() -> None:
    header = next(csv.reader(io.StringIO(render_csv([], Row))))

    assert header == list(Row.model_fields)


def test_an_empty_export_is_a_header_and_nothing_else() -> None:
    assert render_csv([], Row).strip() == ",".join(Row.model_fields)


# --- Value rendering --------------------------------------------------------


def test_none_becomes_an_empty_cell() -> None:
    assert _parsed([_row(amount=None, due=None)])[0]["amount"] == ""


def test_a_boolean_is_not_rendered_as_a_number() -> None:
    """``bool`` is a subclass of ``int``; the naive branch order prints 1/0."""
    assert _parsed([_row(active=True)])[0]["active"] == "true"
    assert _parsed([_row(active=False)])[0]["active"] == "false"


def test_an_enum_writes_its_wire_value() -> None:
    assert _parsed([_row()])[0]["colour"] == "RED"


def test_a_decimal_never_reaches_scientific_notation() -> None:
    tiny = _parsed([_row(amount=decimal.Decimal("0.00000001"))])[0]["amount"]

    assert tiny == "0.00000001"
    assert "E" not in tiny.upper()


def test_dates_and_datetimes_are_iso_8601() -> None:
    row = _parsed([_row()])[0]

    assert row["due"] == "2026-08-28"
    assert row["created_at"].startswith("2026-08-28T09:30:00")


def test_a_value_containing_a_comma_survives_a_round_trip() -> None:
    assert _parsed([_row(name="Acme, Inc.")])[0]["name"] == "Acme, Inc."


def test_a_value_containing_a_quote_survives_a_round_trip() -> None:
    assert _parsed([_row(name='The "Big" Co')])[0]["name"] == 'The "Big" Co'


def test_a_value_containing_a_newline_survives_a_round_trip() -> None:
    assert _parsed([_row(name="Line one\nLine two")])[0]["name"] == "Line one\nLine two"


# --- Formula injection (CWE-1236) -------------------------------------------


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_a_cell_that_would_execute_is_prefixed(prefix: str) -> None:
    """Every character a spreadsheet treats as the start of a formula."""
    rendered = _parsed([_row(name=f"{prefix}HYPERLINK()")])[0]["name"]

    assert rendered.startswith("'")


def test_an_ordinary_value_is_left_alone() -> None:
    """The apostrophe is visible in the data, so it is not applied blindly."""
    assert _parsed([_row(name="Acme")])[0]["name"] == "Acme"


# --- The row cap ------------------------------------------------------------


class _FakeService:
    """Pages like ``TenantScopedService`` without touching a database."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.pages_served = 0

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[Any] = (),
        visibility: Any = None,
    ) -> tuple[Sequence[Any], int]:
        self.pages_served += 1
        start = params.offset
        end = min(start + params.limit, self.total)
        return [_row(name=f"Row {index}") for index in range(start, end)], self.total


async def test_a_result_over_the_cap_is_refused() -> None:
    service = _FakeService(total=EXPORT_ROW_LIMIT + 1)

    with pytest.raises(ExportTooLargeError):
        await collect_rows(service, uuid.uuid4())


async def test_the_refusal_costs_one_round_trip() -> None:
    """The first page already reports the total; there is no reason to fetch on."""
    service = _FakeService(total=EXPORT_ROW_LIMIT + 1)

    with pytest.raises(ExportTooLargeError):
        await collect_rows(service, uuid.uuid4())

    assert service.pages_served == 1


async def test_a_result_at_the_cap_is_allowed() -> None:
    """The limit is inclusive — an export of exactly the cap is not an error."""
    service = _FakeService(total=EXPORT_ROW_LIMIT)

    assert len(await collect_rows(service, uuid.uuid4())) == EXPORT_ROW_LIMIT


async def test_every_page_is_collected() -> None:
    service = _FakeService(total=MAX_PAGE_SIZE * 2 + 7)

    rows = await collect_rows(service, uuid.uuid4())

    assert len(rows) == MAX_PAGE_SIZE * 2 + 7
    assert service.pages_served == 3


async def test_an_empty_result_needs_no_second_page() -> None:
    service = _FakeService(total=0)

    assert await collect_rows(service, uuid.uuid4()) == []
    assert service.pages_served == 1


# --- Download naming --------------------------------------------------------


def test_the_filename_is_dated() -> None:
    value = content_disposition("accounts", now=dt.datetime(2026, 8, 28, tzinfo=dt.UTC))

    assert value == 'attachment; filename="s3k-accounts-20260828.csv"'


def test_the_filename_cannot_carry_a_header_injection() -> None:
    """The name is built from a fixed vocabulary, but strip anyway."""
    value = content_disposition('acc"\r\nX-Evil: 1')

    assert "\r" not in value
    assert "\n" not in value
    assert '"' not in value.removeprefix('attachment; filename="').removesuffix('.csv"')
