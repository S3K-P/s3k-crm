"""Pydantic contracts for activities and their meeting extension."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.products.crm.activities.models import ActivityStatus, ActivityType, MeetingType
from app.products.crm.common import CrmEntityType


class MeetingDetail(BaseModel):
    """Scheduling detail, required when the activity is a MEETING."""

    model_config = ConfigDict(from_attributes=True)

    meeting_type: MeetingType = MeetingType.VIDEO
    start_time: dt.datetime
    end_time: dt.datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    meeting_link: str | None = Field(default=None, max_length=1024)
    agenda: str | None = None
    reminder_minutes: int | None = Field(default=None, ge=0, le=10080)
    internal_participant_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _end_after_start(self) -> MeetingDetail:
        if self.end_time is not None and self.end_time <= self.start_time:
            msg = "end_time must be after start_time."
            raise ValueError(msg)
        return self


class ActivityBase(BaseModel):
    type: ActivityType
    subject: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: ActivityStatus = ActivityStatus.PLANNED
    due_date: dt.datetime | None = None
    outcome: str | None = None
    owner_id: uuid.UUID | None = None
    related_entity_type: CrmEntityType | None = None
    related_entity_id: uuid.UUID | None = None


class ActivityCreate(ActivityBase):
    """An activity, plus scheduling detail when it is a meeting."""

    meeting: MeetingDetail | None = None

    @model_validator(mode="after")
    def _meeting_detail_matches_type(self) -> ActivityCreate:
        if self.type is ActivityType.MEETING and self.meeting is None:
            msg = "meeting detail is required when type is MEETING."
            raise ValueError(msg)
        if self.type is not ActivityType.MEETING and self.meeting is not None:
            msg = "meeting detail is only valid when type is MEETING."
            raise ValueError(msg)
        return self


class ActivityUpdate(BaseModel):
    """Partial update. ``type`` is immutable once written."""

    subject: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: ActivityStatus | None = None
    due_date: dt.datetime | None = None
    outcome: str | None = None
    owner_id: uuid.UUID | None = None
    related_entity_type: CrmEntityType | None = None
    related_entity_id: uuid.UUID | None = None
    meeting: MeetingDetail | None = None


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    type: ActivityType
    subject: str
    description: str | None
    status: ActivityStatus
    due_date: dt.datetime | None
    completed_at: dt.datetime | None
    outcome: str | None
    owner_id: uuid.UUID | None
    related_entity_type: CrmEntityType | None
    related_entity_id: uuid.UUID | None
    meeting: MeetingDetail | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


__all__ = [
    "ActivityCreate",
    "ActivityResponse",
    "ActivityUpdate",
    "MeetingDetail",
]
