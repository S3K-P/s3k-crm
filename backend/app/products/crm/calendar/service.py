"""Projecting meetings and tasks onto one timeline (Phase F).

A read model, in the sense ARCHITECTURE-BOUNDARIES.md rule 6 permits: it reads
across two modules and writes nothing, so no module's invariants can be
bypassed through it. Creating and editing still happen on the activities and
tasks endpoints, which is why there is no ``POST /crm/calendar`` — a calendar
that could write would be a third place the meeting rules live.

**Each half is authorized on its own terms**, which is the part that would be
easy to get subtly wrong. Meetings are activities: organization-wide by design,
because an activity is a child of the record it is logged against and hiding a
colleague's call from an account's history is the opposite of what a shared
customer record is for. Tasks are owner-scoped. So the two halves are fetched
through their own services with their own visibility, and a caller holding one
permission and not the other gets the half they are entitled to rather than an
error — a rep who cannot see activities still has a calendar of their tasks.

**Everything is compared as an instant.** The window arrives with an offset and
is normalized to UTC before any query; both underlying columns are
``timestamptz``. Nothing here constructs a date, a midnight, or a "day" — the
only code that knows what day it is locally is the browser that asked.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.activities.models import Activity, Meeting
from app.products.crm.activities.service import ActivityService
from app.products.crm.calendar.schemas import (
    CalendarEntry,
    CalendarRange,
    CalendarSource,
)
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import Task
from app.products.crm.tasks.service import TaskService

#: Ceiling on entries one response may carry, across both sources.
#:
#: The per-source limits already bound each query; this bounds their sum, so a
#: pathological range cannot produce a four-thousand-entry payload for a grid
#: that can draw a few hundred. Reached only by a request the cap on window
#: length has already let through, so in practice it never fires.
MAX_ENTRIES = 2_000


class CalendarService:
    """Assembles the calendar for one caller and one window."""

    def __init__(self, session: AsyncSession) -> None:
        self._activities = ActivityService(session)
        self._tasks = TaskService(session)

    async def entries(
        self,
        principal: Principal,
        window: CalendarRange,
        *,
        sources: frozenset[CalendarSource] | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> list[CalendarEntry]:
        """Every entry in ``window`` this caller may see.

        Args:
            principal: the caller, whose permissions decide which halves run.
            window: the half-open range, already validated to carry offsets.
            sources: restrict to some kinds. ``None`` means both.
            owner_id: narrow to one person's entries — what a "my calendar"
                toggle sends. Applied *in addition to* record-level
                visibility, never instead of it: passing a colleague's id
                cannot widen what the caller may see, it can only narrow it.
        """
        wanted = sources or frozenset(CalendarSource)
        # Normalized once, here, so neither query has to think about offsets
        # and the two halves cannot disagree about where the window is.
        start = window.start.astimezone(dt.UTC)
        end = window.end.astimezone(dt.UTC)

        entries: list[CalendarEntry] = []

        if CalendarSource.MEETING in wanted and principal.has_permission(
            "activities", PermissionAction.VIEW
        ):
            scheduled = await self._activities.scheduled_between(
                principal.organization_id, start=start, end=end, owner_id=owner_id
            )
            entries.extend(_meeting_entry(activity, meeting) for activity, meeting in scheduled)

        if CalendarSource.TASK in wanted and principal.has_permission(
            "tasks", PermissionAction.VIEW
        ):
            due = await self._tasks.due_between(
                principal.organization_id,
                start=start,
                end=end,
                visibility=RecordVisibility.for_module(principal, "tasks"),
                assigned_to_id=owner_id,
            )
            entries.extend(_task_entry(task) for task in due)

        # Sorted across both sources: the two arrived from separate queries,
        # each ordered within itself, and a grid that groups by day needs one
        # sequence. Tie-broken by id so a day's boxes keep a stable order
        # between renders rather than shuffling on every refresh.
        entries.sort(key=lambda entry: (entry.start, str(entry.id)))
        return entries[:MAX_ENTRIES]


def _meeting_entry(activity: Activity, meeting: Meeting) -> CalendarEntry:
    """One meeting, projected.

    ``end`` stays ``None`` when the meeting has no end time rather than being
    filled with a guessed duration: the grid draws a point, which is what the
    record actually says.
    """
    return CalendarEntry(
        id=activity.id,
        source=CalendarSource.MEETING,
        title=activity.subject,
        start=meeting.start_time,
        end=meeting.end_time,
        all_day=False,
        status=activity.status.value,
        owner_id=activity.owner_id,
        related_entity_type=activity.related_entity_type,
        related_entity_id=activity.related_entity_id,
        location=meeting.location,
        meeting_link=meeting.meeting_link,
    )


def _task_entry(task: Task) -> CalendarEntry:
    """One task, projected onto its due date.

    ``all_day`` is set because a due date is a *deadline*, not an appointment:
    placing it at whatever time the column happens to hold would put "due
    Friday" at 00:00 in the small hours of a grid, above every real meeting
    that day, and imply a precision the user never entered.

    ``owner_id`` carries ``assigned_to_id``, falling back to the owner. The
    person a task is *for* is who a "my calendar" filter has to mean, and on a
    delegated task that is the assignee rather than whoever created it.
    """
    assert task.due_date is not None  # noqa: S101 - the query filters on it
    return CalendarEntry(
        id=task.id,
        source=CalendarSource.TASK,
        title=task.title,
        start=task.due_date,
        end=None,
        all_day=True,
        status=task.status.value,
        owner_id=task.assigned_to_id or task.owner_id,
        related_entity_type=task.related_entity_type,
        related_entity_id=task.related_entity_id,
        location=None,
        meeting_link=None,
    )


def sources_from(values: Sequence[str] | None) -> frozenset[CalendarSource] | None:
    """Parse a repeated ``?source=`` parameter, or ``None`` for "everything".

    An unrecognised value is ignored rather than refused, and the empty result
    falls back to everything: a client sending a source this version does not
    know should get a calendar, not a 422. The set is closed and small, so
    there is nothing an ignored value could smuggle past.
    """
    if not values:
        return None
    known = {CalendarSource(value) for value in values if value in set(CalendarSource)}
    return frozenset(known) or None


__all__ = ["MAX_ENTRIES", "CalendarService", "sources_from"]
