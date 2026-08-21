"""Pydantic contracts for leads and lead sources."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.products.crm.common import Priority
from app.products.crm.leads.models import LeadSourceStatus, LeadStatus


class LeadCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    company: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    lead_source_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    priority: Priority | None = None
    expected_deal_size: Decimal | None = Field(default=None, ge=0)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=512)
    company_size: str | None = Field(default=None, max_length=64)
    product_interest: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    campaign_id: uuid.UUID | None = None


class LeadUpdate(BaseModel):
    """Partial update. ``status`` is excluded — use the transition endpoint."""

    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    company: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    lead_source_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    priority: Priority | None = None
    expected_deal_size: Decimal | None = Field(default=None, ge=0)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=512)
    company_size: str | None = Field(default=None, max_length=64)
    product_interest: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    ai_score: int | None = Field(default=None, ge=0, le=100)


class LeadStatusChange(BaseModel):
    """Move a lead along the pipeline."""

    status: LeadStatus
    lost_reason: str | None = Field(default=None, max_length=255)


class LeadOwnerChange(BaseModel):
    owner_id: uuid.UUID | None = None


class LeadConvertRequest(BaseModel):
    """Convert a qualified lead.

    Supply ``account_id`` / ``contact_id`` to link existing records instead of
    creating duplicates. When omitted, the service auto-links an exact name /
    email match when one exists; otherwise it creates new records from the
    lead. Create a deal by default so the lifecycle reaches Opportunity.
    """

    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    create_opportunity: bool = True
    opportunity_name: str | None = Field(default=None, max_length=255)
    opportunity_value: Decimal | None = Field(default=None, ge=0)
    stage_id: uuid.UUID | None = None
    expected_close_date: dt.date | None = None


class ConversionMatchAccount(BaseModel):
    id: uuid.UUID
    name: str


class ConversionMatchContact(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    account_id: uuid.UUID | None


class LeadConversionSuggestions(BaseModel):
    """Existing records the convert UI should offer to link instead of recreate."""

    matching_accounts: list[ConversionMatchAccount]
    matching_contacts: list[ConversionMatchContact]
    suggested_account_name: str
    suggested_contact_name: str
    suggested_opportunity_name: str
    suggested_deal_value: Decimal | None


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    first_name: str
    last_name: str
    company: str | None
    email: str | None
    phone: str | None
    lead_source_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    status: LeadStatus
    ai_score: int | None
    priority: Priority | None
    expected_deal_size: Decimal | None
    industry: str | None
    website: str | None
    company_size: str | None
    product_interest: str | None
    notes: str | None
    lost_reason: str | None
    converted_at: dt.datetime | None
    converted_account_id: uuid.UUID | None
    converted_contact_id: uuid.UUID | None
    converted_opportunity_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None


class LeadConversionResponse(BaseModel):
    """What conversion produced, so the client can navigate straight there."""

    lead_id: uuid.UUID
    account_id: uuid.UUID
    contact_id: uuid.UUID
    opportunity_id: uuid.UUID | None


class LeadStatusCounts(BaseModel):
    """Per-column totals for the kanban board."""

    counts: dict[str, int]


# --- Lead sources -----------------------------------------------------------


class LeadSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=120)
    description: str | None = None
    status: LeadSourceStatus = LeadSourceStatus.ACTIVE


class LeadSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=120)
    description: str | None = None
    status: LeadSourceStatus | None = None


class LeadSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    category: str | None
    description: str | None
    status: LeadSourceStatus
    #: Live leads attributed to this source. Derived per request, never stored,
    #: so it cannot drift from the leads table.
    lead_count: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None = None
    updated_by_id: uuid.UUID | None = None


__all__ = [
    "ConversionMatchAccount",
    "ConversionMatchContact",
    "LeadConversionResponse",
    "LeadConversionSuggestions",
    "LeadConvertRequest",
    "LeadCreate",
    "LeadOwnerChange",
    "LeadResponse",
    "LeadSourceCreate",
    "LeadSourceResponse",
    "LeadSourceUpdate",
    "LeadStatusChange",
    "LeadStatusCounts",
    "LeadUpdate",
]
