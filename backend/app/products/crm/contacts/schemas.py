"""Pydantic contracts for contacts.

``organization_id`` is absent from every request model on purpose: tenancy is
taken from the authenticated principal, never from the body.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.products.crm.contacts.models import ContactStatus
from app.products.crm.shared.schemas import CustomFieldValues


class ContactBase(BaseModel):
    salutation: str | None = Field(default=None, max_length=20)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    account_id: uuid.UUID | None = None
    email: EmailStr | None = None
    secondary_email: EmailStr | None = None
    email_opt_out: bool = False
    phone: str | None = Field(default=None, max_length=32)
    mobile: str | None = Field(default=None, max_length=32)
    job_title: str | None = Field(default=None, max_length=160)
    department: str | None = Field(default=None, max_length=120)
    owner_id: uuid.UUID | None = None
    status: ContactStatus = ContactStatus.ACTIVE
    preferred_communication: str | None = Field(default=None, max_length=64)
    linkedin_url: str | None = Field(default=None, max_length=512)
    notes: str | None = None
    address_line1: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=120)


class ContactCreate(ContactBase):
    """Everything needed to add a contact."""

    #: Promote this contact to primary on its account, demoting the incumbent.
    is_primary: bool = False
    #: Tenant-defined values, validated against this organization's own field
    #: definitions. Absent means "apply the configured defaults"; a supplied
    #: object is merged over them.
    custom_fields: CustomFieldValues | None = None


class ContactUpdate(BaseModel):
    """Partial update. Only supplied fields are written."""

    salutation: str | None = Field(default=None, max_length=20)
    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, min_length=1, max_length=120)
    account_id: uuid.UUID | None = None
    email: EmailStr | None = None
    secondary_email: EmailStr | None = None
    email_opt_out: bool | None = None
    phone: str | None = Field(default=None, max_length=32)
    mobile: str | None = Field(default=None, max_length=32)
    job_title: str | None = Field(default=None, max_length=160)
    department: str | None = Field(default=None, max_length=120)
    owner_id: uuid.UUID | None = None
    status: ContactStatus | None = None
    preferred_communication: str | None = Field(default=None, max_length=64)
    linkedin_url: str | None = Field(default=None, max_length=512)
    notes: str | None = None
    address_line1: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    postal_code: str | None = Field(default=None, max_length=32)
    country: str | None = Field(default=None, max_length=120)
    is_primary: bool | None = None
    #: Tenant-defined values. Absent leaves the whole document untouched — an
    #: empty object is what clears it — so patching one built-in column cannot
    #: wipe a record's custom fields.
    custom_fields: CustomFieldValues | None = None


class ContactBulkUpdate(BaseModel):
    """Patch the same fields on many contacts at once (Checkpoint 4)."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    values: ContactUpdate


class ContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    account_id: uuid.UUID | None
    salutation: str | None
    first_name: str
    last_name: str
    full_name: str
    email: str | None
    secondary_email: str | None
    email_opt_out: bool
    phone: str | None
    mobile: str | None
    job_title: str | None
    department: str | None
    owner_id: uuid.UUID | None
    status: ContactStatus
    ai_score: int | None
    preferred_communication: str | None
    linkedin_url: str | None
    notes: str | None
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


__all__ = ["ContactBulkUpdate", "ContactCreate", "ContactResponse", "ContactUpdate"]
