"""Activity and meeting business rules (plan P2-W18-BE-01/02/03).

Three things this module is responsible for:

* **The meeting extension stays in step with its activity.** A ``MEETING``
  activity always has exactly one ``meetings`` row; anything else does not have
  one at all. Both are written in the caller's transaction, so a half-created
  meeting cannot survive a failure.
* **``completed_at`` is derived from status**, never accepted from the client,
  so it cannot contradict the state it describes.
* **The entity timeline** (P2-W18-BE-03) that every CRM detail page reads is
  built here, org-scoped, rather than in each consumer.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.activities.models import (
    Activity,
    ActivityStatus,
    ActivityType,
    Meeting,
)
from app.products.crm.common import CrmEntityType
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.relations import validate_related_entity
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService


class ActivityService(TenantScopedService[Activity]):
    entity_name = "Activity"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Activity), Activity)
        self._session = session

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        activity_type: ActivityType | None = None,
        status: ActivityStatus | None = None,
        owner_id: uuid.UUID | None = None,
        related_entity_type: CrmEntityType | None = None,
        related_entity_id: uuid.UUID | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Activity.subject).like(term),
                    func.lower(func.coalesce(Activity.description, "")).like(term),
                )
            )
        if activity_type is not None:
            filters.append(Activity.type == activity_type)
        if status is not None:
            filters.append(Activity.status == status)
        if owner_id is not None:
            filters.append(Activity.owner_id == owner_id)
        if related_entity_type is not None:
            filters.append(Activity.related_entity_type == related_entity_type)
        if related_entity_id is not None:
            filters.append(Activity.related_entity_id == related_entity_id)
        return filters

    async def list_activities(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[Activity], int]:
        return await self.list(organization_id, params=params, filters=filters)

    async def get_meeting(self, activity: Activity) -> Meeting | None:
        """Scheduling detail for a meeting activity, or ``None``.

        Reached only through an already-authorized activity, which is what
        keeps the un-tenanted ``meetings`` table safe.
        """
        if activity.type is not ActivityType.MEETING:
            return None
        result = await self._session.execute(
            select(Meeting).where(Meeting.activity_id == activity.id)
        )
        return result.scalar_one_or_none()

    async def load_meetings(
        self, activities: Sequence[Activity]
    ) -> dict[uuid.UUID, Meeting]:
        """Meeting rows for a page of activities, keyed by activity id.

        One query for the whole page rather than one per row: a list of 25
        meetings should not cost 26 round trips.
        """
        meeting_ids = [a.id for a in activities if a.type is ActivityType.MEETING]
        if not meeting_ids:
            return {}
        result = await self._session.execute(
            select(Meeting).where(Meeting.activity_id.in_(meeting_ids))
        )
        return {meeting.activity_id: meeting for meeting in result.scalars().all()}

    async def scheduled_between(
        self,
        organization_id: uuid.UUID,
        *,
        start: dt.datetime,
        end: dt.datetime,
        owner_id: uuid.UUID | None = None,
        limit: int = 2_000,
    ) -> Sequence[tuple[Activity, Meeting]]:
        """Meetings whose scheduled window overlaps ``[start, end)`` (Phase F).

        Lives here rather than in the calendar module because this module owns
        both tables: ``crm.meetings`` carries no tenant column of its own and
        is only ever safe to read through its parent activity, which this join
        does inside the organization filter.

        **Overlap, not containment.** A meeting that starts before the window
        and ends inside it belongs on the grid — a Monday-morning view has to
        show the call that began on Sunday night. The condition is therefore
        ``start_time < end AND coalesce(end_time, start_time) >= start``, which
        is the standard half-open overlap and treats a meeting with no end time
        as an instant rather than as one running forever.

        ``limit`` bounds a request for an absurd range. A month of a busy
        team's meetings is in the low hundreds; two thousand is far above that
        and low enough that a client asking for a decade gets a bounded answer
        instead of the whole table.
        """
        result = await self._session.execute(
            select(Activity, Meeting)
            .join(Meeting, Meeting.activity_id == Activity.id)
            .where(
                Activity.organization_id == organization_id,
                Activity.deleted_at.is_(None),
                Meeting.start_time < end,
                func.coalesce(Meeting.end_time, Meeting.start_time) >= start,
                *([Activity.owner_id == owner_id] if owner_id is not None else []),
            )
            .order_by(Meeting.start_time.asc())
            .limit(limit)
        )
        return [(activity, meeting) for activity, meeting in result.all()]

    async def timeline(
        self,
        organization_id: uuid.UUID,
        *,
        entity_type: CrmEntityType,
        entity_id: uuid.UUID,
        limit: int = 50,
    ) -> Sequence[Activity]:
        """Everything recorded against one record, most recent first.

        Ordered by when the activity actually happened — completion time where
        known, otherwise the scheduled date, otherwise when it was written
        down. Sorting purely by ``created_at`` would put a meeting logged late
        above one that happened yesterday.
        """
        result = await self._session.execute(
            select(Activity)
            .where(
                Activity.organization_id == organization_id,
                Activity.deleted_at.is_(None),
                Activity.related_entity_type == entity_type,
                Activity.related_entity_id == entity_id,
            )
            .order_by(
                func.coalesce(
                    Activity.completed_at, Activity.due_date, Activity.created_at
                ).desc()
            )
            .limit(limit)
        )
        return result.scalars().all()

    # --- Commands ----------------------------------------------------------

    async def create_activity(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> Activity:
        """Create an activity and, for meetings, its scheduling row."""
        payload = dict(values)
        meeting_detail = payload.pop("meeting", None)
        payload.pop("completed_at", None)

        await validate_related_entity(
            self._session,
            entity_type=payload.get("related_entity_type"),
            entity_id=payload.get("related_entity_id"),
            organization_id=organization_id,
        )

        if payload.get("status") is ActivityStatus.COMPLETED:
            payload["completed_at"] = dt.datetime.now(dt.UTC)

        activity = await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )

        if meeting_detail is not None:
            self._session.add(Meeting(activity_id=activity.id, **dict(meeting_detail)))
            await self._session.flush()

        return activity

    async def update_activity(
        self,
        activity: Activity,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> Activity:
        """Patch an activity and any meeting detail supplied alongside it."""
        payload = dict(values)
        meeting_detail = payload.pop("meeting", None)
        payload.pop("completed_at", None)
        # ``type`` decides whether a meetings row must exist; changing it after
        # the fact would leave that relationship inconsistent.
        payload.pop("type", None)

        if "related_entity_type" in payload or "related_entity_id" in payload:
            await validate_related_entity(
                self._session,
                entity_type=payload.get("related_entity_type", activity.related_entity_type),
                entity_id=payload.get("related_entity_id", activity.related_entity_id),
                organization_id=activity.organization_id,
            )

        new_status = payload.get("status")
        if new_status is not None and new_status != activity.status:
            payload["completed_at"] = (
                dt.datetime.now(dt.UTC) if new_status is ActivityStatus.COMPLETED else None
            )

        updated = await self.update(activity, actor_id=actor_id, values=payload)

        if meeting_detail is not None and updated.type is ActivityType.MEETING:
            await self._upsert_meeting(updated, dict(meeting_detail))

        return updated

    async def archive_activity(
        self, activity: Activity, *, actor_id: uuid.UUID | None
    ) -> Activity:
        """Soft-delete an activity.

        The meetings row is left in place: it is reachable only through the
        parent, which no longer appears in any list, and keeping it means an
        undelete restores the full record rather than a meeting with no time.
        """
        return await self.soft_delete(activity, actor_id=actor_id)

    # --- Internals ---------------------------------------------------------

    async def _upsert_meeting(self, activity: Activity, detail: dict[str, Any]) -> None:
        existing = await self.get_meeting(activity)
        if existing is None:
            self._session.add(Meeting(activity_id=activity.id, **detail))
        else:
            for field, value in detail.items():
                setattr(existing, field, value)
        await self._session.flush()


__all__ = ["ActivityService"]
