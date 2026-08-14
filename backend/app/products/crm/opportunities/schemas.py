"""Pydantic contracts for opportunities and pipeline stages."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OpportunityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    account_id: uuid.UUID
    stage_id: uuid.UUID
    primary_contact_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    deal_value: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    win_probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: dt.date | None = None
    forecast_category: str | None = Field(default=None, max_length=64)
    competitor: str | None = Field(default=None, max_length=160)
    lead_source_id: uuid.UUID | None = None
    products: str | None = None
    notes: str | None = None


class OpportunityUpdate(BaseModel):
    """Partial update. ``stage_id`` is excluded — use the stage endpoint."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    primary_contact_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    deal_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    win_probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: dt.date | None = None
    health_score: int | None = Field(default=None, ge=0, le=100)
    forecast_category: str | None = Field(default=None, max_length=64)
    competitor: str | None = Field(default=None, max_length=160)
    products: str | None = None
    notes: str | None = None


class OpportunityStageChange(BaseModel):
    """Move a deal to another stage.

    ``loss_reason`` becomes mandatory when the target stage is terminal-lost;
    the service enforces that rather than the schema, because whether a stage
    is "lost" is data, not shape.
    """

    stage_id: uuid.UUID
    note: str | None = Field(default=None, max_length=512)
    loss_reason: str | None = Field(default=None, max_length=255)
    win_reason: str | None = Field(default=None, max_length=255)


class OpportunityReopen(BaseModel):
    stage_id: uuid.UUID


class OpportunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    account_id: uuid.UUID
    primary_contact_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    stage_id: uuid.UUID
    deal_value: Decimal | None
    currency: str
    win_probability: int | None
    expected_close_date: dt.date | None
    health_score: int | None
    forecast_category: str | None
    competitor: str | None
    lead_source_id: uuid.UUID | None
    products: str | None
    notes: str | None
    won_at: dt.datetime | None
    lost_at: dt.datetime | None
    loss_reason: str | None
    win_reason: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


class PipelineStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pipeline_id: uuid.UUID
    name: str
    sort_order: int
    default_probability: int | None
    is_won: bool
    is_lost: bool


class StageHistoryEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_stage_id: uuid.UUID | None
    to_stage_id: uuid.UUID
    changed_by_id: uuid.UUID | None
    changed_at: dt.datetime
    note: str | None


__all__ = [
    "OpportunityCreate",
    "OpportunityReopen",
    "OpportunityResponse",
    "OpportunityStageChange",
    "OpportunityUpdate",
    "PipelineStageResponse",
    "StageHistoryEntry",
]
