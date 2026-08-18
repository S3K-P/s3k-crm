"""Pydantic contracts for campaigns and their membership."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.products.crm.campaigns.models import (
    CampaignMemberType,
    CampaignStatus,
    CampaignType,
)


class CampaignBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: CampaignType
    status: CampaignStatus = CampaignStatus.PLANNING
    owner_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    expected_revenue: Decimal | None = Field(default=None, ge=0)
    target_audience: str | None = Field(default=None, max_length=255)
    lead_source_id: uuid.UUID | None = None
    products: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _dates_in_order(self) -> CampaignBase:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            msg = "end_date cannot fall before start_date."
            raise ValueError(msg)
        return self


class CampaignCreate(CampaignBase):
    """Everything needed to plan a campaign."""


class CampaignUpdate(BaseModel):
    """Partial update. Cached metrics are never client-writable."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: CampaignType | None = None
    status: CampaignStatus | None = None
    owner_id: uuid.UUID | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    expected_revenue: Decimal | None = Field(default=None, ge=0)
    target_audience: str | None = Field(default=None, max_length=255)
    lead_source_id: uuid.UUID | None = None
    products: str | None = None
    notes: str | None = None


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    type: CampaignType
    status: CampaignStatus
    owner_id: uuid.UUID | None
    start_date: dt.date | None
    end_date: dt.date | None
    budget: Decimal | None
    expected_revenue: Decimal | None
    target_audience: str | None
    lead_source_id: uuid.UUID | None
    products: str | None
    notes: str | None
    leads_generated: int
    opportunities_generated: int
    conversion_rate: Decimal | None
    roi: Decimal | None
    #: Enrolled leads and contacts. Computed per request, not stored.
    member_count: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


class CampaignMemberCreate(BaseModel):
    entity_type: CampaignMemberType
    entity_id: uuid.UUID


class CampaignMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    entity_type: CampaignMemberType
    entity_id: uuid.UUID
    added_at: dt.datetime


__all__ = [
    "CampaignCreate",
    "CampaignMemberCreate",
    "CampaignMemberResponse",
    "CampaignResponse",
    "CampaignUpdate",
]
