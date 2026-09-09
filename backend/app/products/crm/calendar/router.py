"""Calendar routes, mounted at ``/crm/calendar``.

One endpoint, read-only. There is deliberately no ``POST``: a calendar entry is
a meeting or a task, and both are created through their own module's endpoint
where the rules for them live. A writable calendar would be a third place those
rules had to be repeated.

The route names no permission in its dependency, unlike most CRM routes. It
cannot: which halves the caller may see is decided per source inside the
service, against ``activities.VIEW`` and ``tasks.VIEW``. It therefore takes
``PermissionedPrincipal`` — the snapshot-without-assertion dependency global
search was written for, and for the same reason — which still proves
membership and still sits behind the product gate on the parent router.

That dependency moves the authorization decision from the route into the
handler, so it is only sound while the handler actually makes one. Here the
decision is :meth:`CalendarService.entries`, which consults ``has_permission``
before running either query. See ``policies.py`` for why there is no
``calendar.VIEW`` to hold instead.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError

from app.core.database import DbSession
from app.core.exceptions import ValidationFailedError
from app.platform.auth.dependencies import PermissionedPrincipal
from app.products.crm.calendar.schemas import CalendarRange, CalendarResponse
from app.products.crm.calendar.service import CalendarService, sources_from

router = APIRouter()


def calendar_window(
    start: Annotated[str, Query(description="Start of the window, inclusive, with an offset.")],
    end: Annotated[str, Query(description="End of the window, exclusive, with an offset.")],
) -> CalendarRange:
    """Parse and validate the requested window, or refuse with a 422.

    Taken as raw strings and parsed by :class:`CalendarRange` rather than
    declared as ``dt.datetime`` parameters, for two reasons. FastAPI's own
    parameter parsing would consume the value before the model's ``+``-repair
    could see it — and every positive offset arrives with its plus decoded as a
    space, because that is what a query string does. And a model built inside a
    dependency raises a bare ``ValidationError``, which is not the
    ``RequestValidationError`` FastAPI knows how to turn into a 422; left
    untranslated it surfaces as a 500 and an unhelpful "internal error" for
    what is entirely a client mistake.

    So the translation happens here, once, and the message pydantic produced —
    "must include a UTC offset", "end must be after start" — reaches the caller
    intact.
    """
    try:
        return CalendarRange(start=start, end=end)  # type: ignore[arg-type]
    except ValidationError as exc:
        raise ValidationFailedError(
            "; ".join(error["msg"].removeprefix("Value error, ") for error in exc.errors()),
            details={"parameters": ["start", "end"]},
        ) from exc


CalendarWindow = Annotated[CalendarRange, Depends(calendar_window)]


def get_service(session: DbSession) -> CalendarService:
    return CalendarService(session)


ServiceDep = Annotated[CalendarService, Depends(get_service)]


@router.get("", response_model=CalendarResponse)
async def read_calendar(
    principal: PermissionedPrincipal,
    service: ServiceDep,
    window: CalendarWindow,
    source: Annotated[list[str] | None, Query()] = None,
    owner_id: Annotated[uuid.UUID | None, Query()] = None,
) -> CalendarResponse:
    """Meetings and tasks in one window, as a single sorted timeline.

    ``start`` and ``end`` must carry a UTC offset and are half-open. A naive
    value is a 422 rather than being read as UTC: a grid built from a naive
    boundary is silently wrong by the user's offset, which moves entries
    between days, and the customer notices before the logs do.

    ``owner_id`` narrows to one person — what a "my calendar" toggle sends. It
    is applied in addition to record-level visibility, never instead of it, so
    passing a colleague's id cannot widen what comes back.
    """
    entries = await service.entries(
        principal, window, sources=sources_from(source), owner_id=owner_id
    )
    return CalendarResponse(start=window.start, end=window.end, entries=entries)


__all__ = ["router"]
