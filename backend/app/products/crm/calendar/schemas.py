"""The shape a calendar grid renders, and the range it asks for.

One entry type for two kinds of record, because a month grid draws boxes and
does not care which table a box came from. What it *does* care about — where
the box starts, how long it is, whether it is finished, and where clicking it
goes — is exactly the projected fields below.

**Every instant on the wire is timezone-aware, in both directions.** The range
parameters are required to carry an offset and the entries come back in UTC.
That is the whole timezone story and it is deliberately the entire story: a
naive datetime would be reinterpreted by whoever received it, and a "date"
parameter would be one whose day boundary depends on a zone the server does not
know. The client turns its user's local month into two instants; the server
compares instants; the client renders instants back into local time.
"""

from __future__ import annotations

import datetime as dt
import enum
import re
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from app.products.crm.common import CrmEntityType

#: Longest range one request may ask for.
#:
#: A calendar shows a day, a week or a month; 400 days covers a year view with
#: room for the partial months at each end. Beyond that the request is not a
#: calendar render, and answering it would mean scanning years of two tables to
#: build a grid nobody is looking at.
MAX_RANGE_DAYS = 400


class CalendarSource(enum.StrEnum):
    """Which record a calendar entry projects.

    On the wire so a client can style, filter and route by it. The value is
    also what says which endpoint to open the entry through — a meeting is an
    activity, a task is a task — which is why this is an explicit field rather
    than something inferred from whether ``end`` is set.
    """

    MEETING = "MEETING"
    TASK = "TASK"


class CalendarEntry(BaseModel):
    """One box on the grid."""

    id: uuid.UUID
    source: CalendarSource
    title: str
    start: dt.datetime
    #: ``None`` for a task, and for a meeting with no end time. A grid draws
    #: those as a point rather than guessing a duration — an invented
    #: half-hour would be a claim the record does not make.
    end: dt.datetime | None = None
    #: A task occupies its due *day* rather than an instant, so a grid places
    #: it in the day's all-day row instead of at a time the user never chose.
    all_day: bool = False
    status: str
    #: For a meeting, its owner. For a task, whoever it is assigned to —
    #: which is the person the entry is *for*, and the one a "my calendar"
    #: filter has to mean.
    owner_id: uuid.UUID | None = None
    related_entity_type: CrmEntityType | None = None
    related_entity_id: uuid.UUID | None = None
    location: str | None = None
    meeting_link: str | None = None


class CalendarRange(BaseModel):
    """The window a grid is asking about.

    Half-open, ``[start, end)``: the natural expression of "this month" is the
    first instant of one month to the first instant of the next, and a closed
    range would double-count an entry sitting exactly on a boundary between two
    consecutive requests.
    """

    start: dt.datetime = Field(description="Start of the window, inclusive, with an offset.")
    end: dt.datetime = Field(description="End of the window, exclusive, with an offset.")

    #: Built from raw query strings by
    #: :func:`~app.products.crm.calendar.router.calendar_window`, not by
    #: FastAPI's own parameter parsing. Two reasons, and the second is the one
    #: that matters: the ``+``-repair below only sees the string if this model
    #: does the parsing, and a model constructed inside a dependency raises a
    #: bare ``ValidationError`` that would surface as a 500 unless the caller
    #: translates it — which that function does.

    @field_validator("start", "end", mode="before")
    @classmethod
    def _restore_plus_in_offset(cls, value: object) -> object:
        """Repair the ``+`` a query string turns into a space.

        ``+`` means "space" in ``application/x-www-form-urlencoded``, which is
        how query strings are decoded. So a client sending
        ``?start=2026-03-04T12:00:00+05:30`` without percent-encoding the plus
        gets ``2026-03-04T12:00:00 05:30`` here — and every positive offset in
        the world becomes an unparseable value or, worse, a naive one.

        A space in that position is never valid ISO-8601 (the date/time
        separator space appears earlier in the string), so restoring it is
        unambiguous rather than a guess. Doing it here means a correctly
        *intended* request is not refused for a URL-encoding subtlety that has
        caught every timestamp-in-a-query-string API ever written — while a
        genuinely naive value still fails the check below, which is the whole
        point of that check.
        """
        if isinstance(value, str):
            return re.sub(r" (\d{2}:\d{2})$", r"+\g<1>", value)
        return value

    @model_validator(mode="after")
    def _check_window(self) -> CalendarRange:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            # Refused rather than assumed to be UTC. A grid built from a naive
            # boundary is silently wrong by the user's offset — up to a
            # fourteen-hour shift, which moves entries between days — and a
            # loud 422 is the only way that surfaces before a customer notices
            # their Monday meetings on Sunday.
            raise ValueError(
                "start and end must include a UTC offset, e.g. 2026-03-01T00:00:00+05:30."
            )
        if self.end <= self.start:
            raise ValueError("end must be after start.")
        if self.end - self.start > dt.timedelta(days=MAX_RANGE_DAYS):
            raise ValueError(f"A calendar range may span at most {MAX_RANGE_DAYS} days.")
        return self


class CalendarResponse(BaseModel):
    """Entries in the requested window.

    Unpaginated on purpose: a grid draws every box or it draws a lie, and a
    second page of a month nobody scrolls is not a thing. The window is capped
    instead, which bounds the work without ever showing a partial month.
    """

    start: dt.datetime
    end: dt.datetime
    entries: list[CalendarEntry]


__all__ = [
    "MAX_RANGE_DAYS",
    "CalendarEntry",
    "CalendarRange",
    "CalendarResponse",
    "CalendarSource",
]
