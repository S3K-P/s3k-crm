"""Pydantic contracts for the products module.

Read-only, and deliberately small. Entitlements are granted by provisioning --
a migration, `app.bootstrap`, or a billing integration that does not exist yet
-- rather than by an API an administrator could call to license their own
organization. There is therefore no create/update schema here on purpose.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel


class ProductResponse(BaseModel):
    """One product in the catalogue."""

    id: uuid.UUID
    code: str
    name: str
    status: str

    model_config = {"from_attributes": True}


class EntitlementResponse(BaseModel):
    """The active organization's licence for one product."""

    product_code: str
    product_name: str
    status: str
    granted_at: dt.datetime
    expires_at: dt.datetime | None
    #: Whether this grant permits opening the product right now -- status and
    #: expiry resolved together, so a client never has to re-derive the rule.
    active: bool


__all__ = ["EntitlementResponse", "ProductResponse"]
