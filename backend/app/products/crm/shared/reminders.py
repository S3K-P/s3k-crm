"""The CRM's implementation of ``platform.notifications``' ``ReminderSource``.

Answers one question — *what is due to remind someone about, in this
organization, right now* — for the two CRM records that carry reminder
information today: a meeting's own ``reminder_minutes`` lead time, and a
task's ``due_date``. Registered with the notifications module by
``app/api/router.py`` (the composition root permitted to see both layers),
the same inversion ``crm_entity_access`` uses for attachments — see that
module's docstring, and ``platform.notifications.policies`` for why the
inversion exists at all.

This is a dedicated cross-module read model in the sense
ARCHITECTURE-BOUNDARIES.md rule 6 permits: it reads the activities and tasks
tables and writes nothing, so no module's invariants can be bypassed through
it.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.notifications.policies import ReminderDue
from app.products.crm.activities.models import Activity, ActivityStatus, ActivityType, Meeting
from app.products.crm.tasks.models import Task, TaskStatus

#: How far ahead to consider a meeting at all, before checking its own
#: ``reminder_minutes`` lead time. Bounds the candidate set the query fetches
#: to something a poll tick can afford to scan; the precise "is it inside its
#: own reminder window" check happens in Python below because that window's
#: length varies per row and PostgreSQL's interval arithmetic on a per-row
#: interval is markedly less readable than the equivalent five lines here —
#: an acceptable trade at this data volume (the same call CSV export's own
#: module makes: "the honest trade for UAT").
_MEETING_LOOKAHEAD = dt.timedelta(days=1)

#: Tasks that became due longer ago than this are assumed to have already
#: produced their one due-reminder (or predate this feature); they are not
#: re-scanned indefinitely. A task overdue by more than a month is a case for
#: a report or an escalation workflow — future work, not an inbox
#: notification repeating forever.
_TASK_OVERDUE_HORIZON = dt.timedelta(days=30)

_CLOSED_TASK_STATUSES = (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


class CrmReminderSource:
    """Due meeting reminders and due/overdue tasks, for one organization."""

    async def due_reminders(
        self, session: AsyncSession, *, organization_id: uuid.UUID, now: dt.datetime
    ) -> Sequence[ReminderDue]:
        reminders = list(await self._meeting_reminders(session, now=now))
        reminders.extend(await self._task_due_reminders(session, now=now))
        return reminders

    async def _meeting_reminders(
        self, session: AsyncSession, *, now: dt.datetime
    ) -> Sequence[ReminderDue]:
        """Planned meetings whose own reminder lead time has arrived.

        Due when ``now`` falls inside ``[start_time - reminder_minutes,
        start_time]`` — the lower bound is checked in Python (see
        ``_MEETING_LOOKAHEAD``), the upper bound (``start_time >= now``) is
        the query filter that naturally stops a meeting from matching once it
        has started, with no separate cap needed.

        A meeting with no ``reminder_minutes`` set never matches: ``None``
        minutes is "no reminder wanted", not "remind immediately".
        """
        statement = (
            select(Activity, Meeting)
            .join(Meeting, Meeting.activity_id == Activity.id)
            .where(
                Activity.type == ActivityType.MEETING,
                Activity.status == ActivityStatus.PLANNED,
                Activity.owner_id.is_not(None),
                Meeting.reminder_minutes.is_not(None),
                Meeting.start_time >= now,
                Meeting.start_time <= now + _MEETING_LOOKAHEAD,
            )
        )
        rows = (await session.execute(statement)).all()

        due: list[ReminderDue] = []
        for activity, meeting in rows:
            lead = dt.timedelta(minutes=meeting.reminder_minutes)
            if meeting.start_time - lead > now:
                continue  # not inside its own reminder window yet
            due.append(
                ReminderDue(
                    recipient_user_id=activity.owner_id,
                    kind="MEETING_REMINDER",
                    title=f"Upcoming meeting: {activity.subject}",
                    body=self._meeting_body(activity, meeting, now=now),
                    entity_type="activity",
                    entity_id=activity.id,
                    # Includes start_time so a reschedule is a new key —
                    # yesterday's reminder for the old time is not reissued,
                    # and the new time gets its own reminder when it is due.
                    dedupe_key=f"meeting_reminder:{activity.id}:{meeting.start_time.isoformat()}",
                )
            )
        return due

    async def _task_due_reminders(
        self, session: AsyncSession, *, now: dt.datetime
    ) -> Sequence[ReminderDue]:
        """Open tasks that are due now or overdue, not yet reminded for this due date."""
        statement = select(Task).where(
            Task.status.not_in(_CLOSED_TASK_STATUSES),
            Task.due_date.is_not(None),
            Task.due_date <= now,
            Task.due_date >= now - _TASK_OVERDUE_HORIZON,
        )
        tasks = (await session.execute(statement)).scalars().all()

        due: list[ReminderDue] = []
        for task in tasks:
            recipient = task.assigned_to_id or task.owner_id
            if recipient is None:
                continue  # nobody to tell
            if task.due_date is None:
                continue  # filtered by the query above; guards mypy, not logic
            overdue = task.due_date < now
            due.append(
                ReminderDue(
                    recipient_user_id=recipient,
                    kind="TASK_DUE",
                    title=f"{'Overdue' if overdue else 'Due now'}: {task.title}",
                    body=None,
                    entity_type="task",
                    entity_id=task.id,
                    # Keyed on the due date, not on "overdue" vs "due now": a
                    # task's due date does not change between the two, so one
                    # reminder per due date is one reminder per task, unless
                    # the due date itself is edited — which correctly earns a
                    # fresh key and a fresh reminder.
                    dedupe_key=f"task_due:{task.id}:{task.due_date.date().isoformat()}",
                )
            )
        return due

    @staticmethod
    def _meeting_body(activity: Activity, meeting: Meeting, *, now: dt.datetime) -> str:
        minutes_until = max(0, int((meeting.start_time - now).total_seconds() // 60))
        where = f" at {meeting.location}" if meeting.location else ""
        if minutes_until == 0:
            return f"Starting now{where}."
        return f"Starts in {minutes_until} minute{'s' if minutes_until != 1 else ''}{where}."


def crm_reminder_source() -> CrmReminderSource:
    """Factory the composition root registers with the notifications module."""
    return CrmReminderSource()


__all__ = ["CrmReminderSource", "crm_reminder_source"]
