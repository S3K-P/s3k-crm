"""Pydantic contracts for accounts.

``AccountResponse`` is the only shape the API emits. ``organization_id`` is
deliberately absent from every request model: tenancy comes from the
authenticated principal, so accepting it would invite a client to try setting
it (see ``TenantScopedService.create``).
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.products.crm.accounts.models import AccountStatus
from app.products.crm.common import Rating
from app.products.crm.shared.schemas import CustomFieldValues


class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    account_type: str | None = Field(default=None, max_length=64)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=512)
    phone: str | None = Field(default=None, max_length=32)
    fax: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    rating: Rating | None = None
    company_size: str | None = Field(default=None, max_length=64)
    annual_revenue: Decimal | None = Field(default=None, ge=0)
    parent_account_id: uuid.UUID | None = None
    status: AccountStatus = AccountStatus.ACTIVE
    owner_id: uuid.UUID | None = None
    primary_contact_id: uuid.UUID | None = None
    health_score: int | None = Field(default=None, ge=0, le=100)
    source: str | None = Field(default=None, max_length=120)
    description: str | None = None
    address_line1: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=120)
    shipping_address_line1: str | None = Field(default=None, max_length=255)
    shipping_city: str | None = Field(default=None, max_length=120)
    shipping_state: str | None = Field(default=None, max_length=120)
    shipping_postal_code: str | None = Field(default=None, max_length=32)
    shipping_country: str | None = Field(default=None, max_length=120)


class AccountCreate(AccountBase):
    """Everything needed to open an account."""

    #: Tenant-defined values, validated against this organization's own field
    #: definitions. Absent means "apply the configured defaults"; a supplied
    #: object is merged over them.
    custom_fields: CustomFieldValues | None = None


class AccountUpdate(BaseModel):
    """Partial update. Only supplied fields are written."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    account_type: str | None = Field(default=None, max_length=64)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=512)
    phone: str | None = Field(default=None, max_length=32)
    fax: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    rating: Rating | None = None
    company_size: str | None = Field(default=None, max_length=64)
    annual_revenue: Decimal | None = Field(default=None, ge=0)
    parent_account_id: uuid.UUID | None = None
    status: AccountStatus | None = None
    owner_id: uuid.UUID | None = None
    primary_contact_id: uuid.UUID | None = None
    health_score: int | None = Field(default=None, ge=0, le=100)
    source: str | None = Field(default=None, max_length=120)
    description: str | None = None
    address_line1: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=120)
    shipping_address_line1: str | None = Field(default=None, max_length=255)
    shipping_city: str | None = Field(default=None, max_length=120)
    shipping_state: str | None = Field(default=None, max_length=120)
    shipping_postal_code: str | None = Field(default=None, max_length=32)
    shipping_country: str | None = Field(default=None, max_length=120)
    #: Tenant-defined values. Absent leaves the whole document untouched — an
    #: empty object is what clears it — so patching one built-in column cannot
    #: wipe a record's custom fields.
    custom_fields: CustomFieldValues | None = None


class AccountBulkUpdate(BaseModel):
    """Patch the same fields on many accounts at once (Checkpoint 4)."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    values: AccountUpdate


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    account_type: str | None
    industry: str | None
    website: str | None
    phone: str | None
    fax: str | None
    email: str | None
    rating: Rating | None
    company_size: str | None
    annual_revenue: Decimal | None
    parent_account_id: uuid.UUID | None
    status: AccountStatus
    owner_id: uuid.UUID | None
    primary_contact_id: uuid.UUID | None
    health_score: int | None
    source: str | None
    description: str | None
    address_line1: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    country: str | None
    shipping_address_line1: str | None
    shipping_city: str | None
    shipping_state: str | None
    shipping_postal_code: str | None
    shipping_country: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None
    #: Never absent: the column is NOT NULL DEFAULT '{}'.
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class AccountOverviewResponse(BaseModel):
    """The Account 360 summary header: real aggregates, never sample data.

    Every count and sum is scoped to what the caller may see — see
    ``AccountService.overview`` — so this can never claim more pipeline or
    more contacts than the caller's own list views would show them.
    """

    contacts_count: int
    open_deals_count: int
    open_pipeline_value: Decimal
    #: Set only when every open deal shares one currency; ``None`` when they
    #: differ, because a sum across currencies has no single symbol to show.
    open_pipeline_currency: str | None
    won_deals_count: int
    won_revenue: Decimal
    won_revenue_currency: str | None
    open_tasks_count: int
    last_activity_at: dt.datetime | None
    next_meeting_id: uuid.UUID | None
    next_meeting_title: str | None
    next_meeting_at: dt.datetime | None
    owner_name: str | None
    primary_contact_name: str | None
    primary_contact_title: str | None


class AccountTimelineEntryResponse(BaseModel):
    """One event in the account's unified timeline.

    ``kind`` is a small fixed vocabulary (``activity``, ``deal_created``,
    ``stage_changed``, ``contact_created``) so the frontend can choose an icon
    without parsing ``title``.
    """

    kind: str
    occurred_at: dt.datetime
    title: str
    detail: str | None
    entity_type: str
    entity_id: uuid.UUID


__all__ = [
    "AccountBulkUpdate",
    "AccountCreate",
    "AccountOverviewResponse",
    "AccountResponse",
    "AccountTimelineEntryResponse",
    "AccountUpdate",
]
