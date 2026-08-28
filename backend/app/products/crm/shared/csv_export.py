"""CSV export for CRM list endpoints (`P3-W23-BE-04`).

**The one rule this module exists to hold.** An export must contain exactly the
rows the caller can already see on the list screen it was launched from, and
exactly the fields the read API already returns for them — never more.

Both halves are structural rather than remembered:

*Rows.* :func:`collect_rows` pages through the module's own
``TenantScopedService.list``, the same call the list endpoint makes, with the
same ``RecordVisibility``. There is no second query path here, so
``VIEW_ALL`` / ``VIEW_TEAM`` / owner-only cannot diverge between what a rep
sees and what they can download. Adding a query here would have been the
easier thing to write and the thing that eventually leaks a colleague's
pipeline.

*Fields.* Rows are serialised through the module's existing ``*Response``
schema. A column the response model deliberately omits — a password hash, a
``search_vector``, an internal flag — cannot appear in a CSV, because the
export never touches the ORM object's attributes directly.

**Why it is not streamed.** ``StreamingResponse`` would keep memory flat, but
its body iterator runs after the endpoint returns, when the request-scoped
database session may already have been closed by FastAPI's exit stack. Paging
into memory under an explicit row cap is the honest trade for UAT: bounded,
obvious, and free of a lifetime bug that would only appear under load. The
async worker that lifts the cap is `P3-W23-BE-02`, deliberately out of scope.
"""

from __future__ import annotations

import csv
import datetime as dt
import decimal
import enum
import io
import uuid
from collections.abc import Sequence
from typing import Any, Protocol

from fastapi import Response
from pydantic import BaseModel

from app.core.exceptions import AppError
from app.products.crm.shared.pagination import MAX_PAGE_SIZE, PageParams, SortDirection
from app.products.crm.shared.visibility import RecordVisibility

#: Ceiling on a single export.
#:
#: Not a performance guess — a promise. The whole result is built in memory, so
#: an unbounded export is an unbounded allocation driven by whoever has the
#: most records. 10 000 rows of a CRM entity is a few megabytes and covers the
#: UAT datasets by a wide margin; past it the caller is told to narrow their
#: filters rather than handed a truncated file that looks complete.
EXPORT_ROW_LIMIT = 10_000

#: Rows fetched per round trip. Deliberately ``MAX_PAGE_SIZE`` rather than a
#: number of this module's own: paging through the list service means obeying
#: the list service's contract, and ``PageParams`` rejects anything larger.
_EXPORT_PAGE_SIZE = MAX_PAGE_SIZE

#: Characters that make a spreadsheet treat a cell as a formula rather than as
#: text (CWE-1236). Every one of these can begin a value that a user typed into
#: an account name, so a cell starting with one is prefixed before it is
#: written -- see :func:`_neutralise`.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class ExportTooLargeError(AppError):
    """The filtered result set exceeds :data:`EXPORT_ROW_LIMIT`."""

    status_code = 413
    code = "export_too_large"
    message = (
        f"This export would contain more than {EXPORT_ROW_LIMIT:,} rows. "
        "Narrow the filters and try again."
    )


class ListService(Protocol):
    """The slice of ``TenantScopedService`` an export needs.

    Typed structurally so this module depends on the *shape* every CRM service
    already has rather than importing the generic base and pinning its type
    parameter -- and so a service that does not page cannot be exported by
    accident.
    """

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[Any] = (),
        visibility: RecordVisibility | None = None,
    ) -> tuple[Sequence[Any], int]: ...


async def collect_rows(
    service: ListService,
    organization_id: uuid.UUID,
    *,
    filters: Sequence[Any] = (),
    visibility: RecordVisibility | None = None,
    sort_by: str | None = None,
    sort_dir: SortDirection = "desc",
) -> list[Any]:
    """Every row the caller may see for these filters, up to the cap.

    Refuses before fetching anything when the total is over the limit: the
    first page already reports it, so a caller who has asked for too much
    learns that in one round trip instead of after ten.

    Raises:
        ExportTooLargeError: the filtered result exceeds :data:`EXPORT_ROW_LIMIT`.
    """
    collected: list[Any] = []
    page = 1

    while True:
        params = PageParams(
            page=page, page_size=_EXPORT_PAGE_SIZE, sort_by=sort_by, sort_dir=sort_dir
        )
        items, total = await service.list(
            organization_id, params=params, filters=filters, visibility=visibility
        )
        if page == 1 and total > EXPORT_ROW_LIMIT:
            raise ExportTooLargeError

        collected.extend(items)
        if len(collected) >= total or not items:
            return collected
        page += 1


def _neutralise(value: str) -> str:
    """Stop a spreadsheet executing a cell that came from user input.

    ``=HYPERLINK("http://attacker","click")`` typed into an account name is
    inert in the application and live the moment somebody opens the export in
    Excel or Sheets. Prefixing with an apostrophe forces the cell to text; the
    apostrophe is not shown by either program and survives a round trip back
    through import as part of the string, which is the visible cost and the
    reason it is applied only to values that actually start with one of these.
    """
    if value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _format(value: Any) -> str:
    """Render one field as CSV text.

    Types are handled explicitly rather than by ``str()`` so a column's
    representation is stable: a date is always ISO 8601, a decimal never
    reaches scientific notation, and an enum writes its wire value rather than
    ``AccountStatus.ACTIVE``.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        # Before int: bool is a subclass of int and would otherwise print 1/0.
        return "true" if value else "false"
    if isinstance(value, enum.Enum):
        return _format(value.value)
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return format(value, "f")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_format(item) for item in value)
    return _neutralise(str(value))


def render_csv(rows: Sequence[Any], schema: type[BaseModel]) -> str:
    """Serialise ``rows`` through ``schema`` into CSV text.

    ``schema`` is the module's own ``*Response`` model, which is what makes the
    file's columns identical to the read API's fields -- including the fields
    it chooses not to expose.

    An empty result still returns the header row. A CSV with no columns is
    indistinguishable from a failed download; a header alone reads correctly as
    "nothing matched".
    """
    headers = list(schema.model_fields)
    buffer = io.StringIO()
    # QUOTE_MINIMAL with the default dialect: Excel, Sheets and Python's own
    # reader all agree on it, which matters because the import side of this
    # feature has to read back what the export side wrote.
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)

    for row in rows:
        serialised = schema.model_validate(row).model_dump()
        writer.writerow([_format(serialised[header]) for header in headers])

    return buffer.getvalue()


def content_disposition(entity_plural: str, *, now: dt.datetime | None = None) -> str:
    """A ``Content-Disposition`` value naming a dated file.

    The name is built here from a fixed vocabulary rather than from anything
    the client sent: a filename that reflected a query parameter would let a
    caller steer a header, and header injection through a download name is a
    well-worn trick.
    """
    stamp = (now or dt.datetime.now(dt.UTC)).strftime("%Y%m%d")
    safe = "".join(char for char in entity_plural if char.isalnum() or char in "-_")
    return f'attachment; filename="s3k-{safe}-{stamp}.csv"'


def csv_response(
    rows: Sequence[Any], schema: type[BaseModel], *, entity_plural: str
) -> Response:
    """Render ``rows`` and wrap them in a download response.

    ``charset=utf-8`` is stated explicitly and the body carries a BOM. Excel on
    Windows reads a UTF-8 CSV as the system code page unless one is present,
    which turns every accented name in the file into mojibake -- and the first
    thing a UAT tester does with an export is open it in Excel.
    """
    body = "﻿" + render_csv(rows, schema)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": content_disposition(entity_plural)},
    )


__all__ = [
    "EXPORT_ROW_LIMIT",
    "ExportTooLargeError",
    "collect_rows",
    "content_disposition",
    "csv_response",
    "render_csv",
]
