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

from pydantic import BaseModel, ConfigDict, Field

from app.products.crm.accounts.models import AccountStatus
from app.products.crm.shared.schemas import CustomFieldValues


class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=512)
    company_size: str | None = Field(default=None, max_length=64)
    annual_revenue: Decimal | None = Field(default=None, ge=0)
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


class AccountCreate(AccountBase):
    """Everything needed to open an account."""

    #: Tenant-defined values, validated against this organization's own field
    #: definitions. Absent means "apply the configured defaults"; a supplied
    #: object is merged over them.
    custom_fields: CustomFieldValues | None = None


class AccountUpdate(BaseModel):
    """Partial update. Only supplied fields are written."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=512)
    company_size: str | None = Field(default=None, max_length=64)
    annual_revenue: Decimal | None = Field(default=None, ge=0)
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
    #: Tenant-defined values. Absent leaves the whole document untouched — an
    #: empty object is what clears it — so patching one built-in column cannot
    #: wipe a record's custom fields.
    custom_fields: CustomFieldValues | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    industry: str | None
    website: str | None
    company_size: str | None
    annual_revenue: Decimal | None
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
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None
    updated_by_id: uuid.UUID | None
    #: Never absent: the column is NOT NULL DEFAULT '{}'.
    custom_fields: dict[str, Any] = Field(default_factory=dict)


__all__ = ["AccountCreate", "AccountResponse", "AccountUpdate"]
