"""Cross-module timeline building blocks (Checkpoint 3).

A "dedicated read model" (ARCHITECTURE-BOUNDARIES.md rule 6): every function
here reads across sibling CRM modules and writes nothing, which is what the
rule requires before a module may read past its own tables. ``accounts``
introduced the pattern in Checkpoint 2 for its own 360 view; this module
lifts the reusable half of it — the entry shape, the merge, and one source
function per event kind — so ``contacts`` and ``opportunities`` can build the
same kind of unified timeline without a second copy of each query.

**Every source function reuses its owning module's own authorization**,
rather than re-deriving it:

* :func:`note_entries` filters with ``NoteService.visibility_filter`` — the
  exact predicate the Notes tab applies — so a private note is excluded here
  the same way it is excluded there, not by a second, easier-to-get-wrong
  copy of that rule.
* :func:`email_entries` filters with ``readable_messages`` from
  ``emails.policies`` for the same reason, and is further restricted to
  ``SENT`` messages: a draft is somebody's unfinished work, not the record's
  history, and does not belong on a timeline other people read.
* :func:`task_entries`, :func:`deal_created_entries` and
  :func:`stage_changed_entries` take the caller's :class:`RecordVisibility`
  for that module, exactly as that module's own list endpoint would.

``detail`` on a :class:`TimelineEntry` holds only what the source row already
stored as structured data — a stage name, a job title — never free text lifted
from a note or an email body, which is exactly the content a shared read model
does not have the module-specific authorization to selectively redact.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.activities.service import ActivityService
from app.products.crm.common import CrmEntityType
from app.products.crm.emails.models import EmailMessage, EmailStatus
from app.products.crm.emails.policies import readable_messages
from app.products.crm.notes.models import Note
from app.products.crm.notes.service import NoteService
from app.products.crm.opportunities.models import (
    Opportunity,
    OpportunityStageHistory,
    PipelineStage,
)
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import Task

#: How many rows each timeline source contributes before the merge trims to
#: the caller's requested limit. Generous enough that "recent" reflects real
#: recency across every source rather than one source crowding the others out.
SOURCE_LIMIT = 50


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """One event in a record's unified timeline."""

    kind: str
    occurred_at: dt.datetime
    title: str
    detail: str | None
    entity_type: str
    entity_id: uuid.UUID


def merge_timeline_entries(*groups: Sequence[TimelineEntry], limit: int) -> list[TimelineEntry]:
    """Newest-first merge of every source, truncated to ``limit``.

    A pure function on purpose: what has to be right here is the sort and the
    cutoff, which needs no database to prove.
    """
    combined = [entry for group in groups for entry in group]
    combined.sort(key=lambda entry: entry.occurred_at, reverse=True)
    return combined[:limit]


def _scoped(
    statement: Select[Any], visibility: RecordVisibility, model: type[Any]
) -> Select[Any]:
    predicate = visibility.filter_for(model)
    return statement if predicate is None else statement.where(predicate)


async def activity_entries(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
    limit: int = SOURCE_LIMIT,
) -> list[TimelineEntry]:
    """Delegates to the activities module's own service (a sibling CRM
    service, not a foreign query — ARCHITECTURE-BOUNDARIES.md rule 6/7), so
    "what counts as this record's activity timeline" is defined once.
    """
    items = await ActivityService(session).timeline(
        organization_id, entity_type=entity_type, entity_id=entity_id, limit=limit
    )
    return [
        TimelineEntry(
            kind="activity",
            occurred_at=activity.completed_at or activity.due_date or activity.created_at,
            title=activity.subject,
            detail=activity.type.value.title(),
            entity_type="ACTIVITY",
            entity_id=activity.id,
        )
        for activity in items
    ]


async def deal_created_entries(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    opportunity_filter: ColumnElement[bool],
    visibility: RecordVisibility,
    limit: int = SOURCE_LIMIT,
) -> list[TimelineEntry]:
    """Deals created against whatever ``opportunity_filter`` selects.

    The predicate is supplied by the caller — ``account_id == …`` for an
    account's timeline, ``primary_contact_id == …`` for a contact's, ``id ==
    …`` for a deal's own — so this one query serves all three without
    guessing which relationship the caller means.
    """
    statement = _scoped(
        select(Opportunity)
        .where(
            Opportunity.organization_id == organization_id,
            Opportunity.deleted_at.is_(None),
            opportunity_filter,
        )
        .order_by(Opportunity.created_at.desc())
        .limit(limit),
        visibility,
        Opportunity,
    )
    result = await session.execute(statement)
    return [
        TimelineEntry(
            kind="deal_created",
            occurred_at=deal.created_at,
            title=f"Deal created: {deal.name}",
            detail=None,
            entity_type="OPPORTUNITY",
            entity_id=deal.id,
        )
        for deal in result.scalars().all()
    ]


async def stage_changed_entries(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    opportunity_filter: ColumnElement[bool],
    visibility: RecordVisibility,
    limit: int = SOURCE_LIMIT,
) -> list[TimelineEntry]:
    """Stage moves for whatever ``opportunity_filter`` selects, newest first.

    Visibility is applied against ``Opportunity``, the row that actually
    carries ``owner_id`` — history rows have none of their own, so a caller
    restricted to their own deals must not see another rep's stage moves leak
    through this join.
    """
    from_stage = PipelineStage.__table__.alias("from_stage")
    to_stage = PipelineStage.__table__.alias("to_stage")
    statement = _scoped(
        select(
            OpportunityStageHistory.changed_at,
            Opportunity.id,
            Opportunity.name,
            from_stage.c.name,
            to_stage.c.name,
        )
        .select_from(OpportunityStageHistory)
        .join(Opportunity, Opportunity.id == OpportunityStageHistory.opportunity_id)
        .outerjoin(from_stage, from_stage.c.id == OpportunityStageHistory.from_stage_id)
        .join(to_stage, to_stage.c.id == OpportunityStageHistory.to_stage_id)
        .where(
            Opportunity.organization_id == organization_id,
            Opportunity.deleted_at.is_(None),
            opportunity_filter,
        )
        .order_by(OpportunityStageHistory.changed_at.desc())
        .limit(limit),
        visibility,
        Opportunity,
    )
    result = await session.execute(statement)
    entries: list[TimelineEntry] = []
    for changed_at, deal_id, deal_name, from_name, to_name in result.all():
        detail = f"{from_name} → {to_name}" if from_name else f"Started in {to_name}"
        entries.append(
            TimelineEntry(
                kind="stage_changed",
                occurred_at=changed_at,
                title=f"{deal_name}: stage changed",
                detail=detail,
                entity_type="OPPORTUNITY",
                entity_id=deal_id,
            )
        )
    return entries


async def task_entries(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
    visibility: RecordVisibility,
    limit: int = SOURCE_LIMIT,
) -> list[TimelineEntry]:
    """Task created, and task completed when it has been.

    Two entries can come from one row, so the fetch is capped at ``limit``
    tasks rather than ``limit`` entries — the caller's overall merge already
    trims to what it actually shows, and a board with fifty open tasks should
    not crowd out every other source by doubling its own row count first.
    """
    statement = _scoped(
        select(Task)
        .where(
            Task.organization_id == organization_id,
            Task.related_entity_type == entity_type,
            Task.related_entity_id == entity_id,
            Task.deleted_at.is_(None),
        )
        .order_by(Task.created_at.desc())
        .limit(limit),
        visibility,
        Task,
    )
    result = await session.execute(statement)
    entries: list[TimelineEntry] = []
    for task in result.scalars().all():
        entries.append(
            TimelineEntry(
                kind="task_created",
                occurred_at=task.created_at,
                title=f"Task created: {task.title}",
                detail=None,
                entity_type="TASK",
                entity_id=task.id,
            )
        )
        if task.completed_at is not None:
            entries.append(
                TimelineEntry(
                    kind="task_completed",
                    occurred_at=task.completed_at,
                    title=f"Task completed: {task.title}",
                    detail=None,
                    entity_type="TASK",
                    entity_id=task.id,
                )
            )
    return entries


async def email_entries(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
    viewer_id: uuid.UUID | None,
    limit: int = SOURCE_LIMIT,
) -> list[TimelineEntry]:
    """Sent mail against this record.

    Reuses the emails module's own ``readable_messages`` predicate rather
    than re-deriving which drafts are private, and is further restricted to
    ``SENT``: a draft — even the viewer's own — is unfinished work, not the
    record's history, and does not belong on a timeline other people read.
    """
    statement = (
        select(EmailMessage)
        .where(
            EmailMessage.organization_id == organization_id,
            EmailMessage.related_entity_type == entity_type,
            EmailMessage.related_entity_id == entity_id,
            EmailMessage.deleted_at.is_(None),
            EmailMessage.status == EmailStatus.SENT,
            readable_messages(viewer_id),
        )
        .order_by(EmailMessage.sent_at.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return [
        TimelineEntry(
            kind="email_sent",
            occurred_at=message.sent_at or message.created_at,
            title=f"Email sent: {message.subject}",
            detail=None,
            entity_type="EMAIL_MESSAGE",
            entity_id=message.id,
        )
        for message in result.scalars().all()
    ]


async def note_entries(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
    viewer_id: uuid.UUID | None,
    limit: int = SOURCE_LIMIT,
) -> list[TimelineEntry]:
    """Notes against this record, reusing the notes module's own visibility.

    Deliberately titled without echoing content: the Notes tab, which calls
    the notes module directly, is where the text itself is read. Visibility
    is enforced by ``NoteService.visibility_filter`` — the identical
    predicate the Notes tab's own query applies — so a private note is
    excluded here exactly as it is excluded there.
    """
    statement = (
        select(Note)
        .where(
            Note.organization_id == organization_id,
            Note.related_entity_type == entity_type,
            Note.related_entity_id == entity_id,
            Note.deleted_at.is_(None),
            NoteService.visibility_filter(viewer_id),
        )
        .order_by(Note.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return [
        TimelineEntry(
            kind="note_added",
            occurred_at=note.created_at,
            title="Note added",
            detail=None,
            entity_type="NOTE",
            entity_id=note.id,
        )
        for note in result.scalars().all()
    ]


__all__ = [
    "SOURCE_LIMIT",
    "TimelineEntry",
    "activity_entries",
    "deal_created_entries",
    "email_entries",
    "merge_timeline_entries",
    "note_entries",
    "stage_changed_entries",
    "task_entries",
]
