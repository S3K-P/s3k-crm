"""Pydantic contracts for the products module.

Granting is still not an API. Entitlements are provisioned -- by a migration,
by ``app.bootstrap``, by self-service signup, or eventually by a billing
integration -- rather than by an endpoint an administrator could call to
license their own organization. There is therefore no schema here that names a
product to be granted.

The one write that *is* exposed is :class:`AppEnablementRequest`, and it
carries a boolean rather than a product code for exactly that reason: the code
comes from the path, is looked up against an entitlement the organization
already holds, and a request naming a product nobody sold them resolves to
nothing. See :meth:`ProductService.set_enabled`.
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
    #: Whether this grant permits opening the product right now -- status,
    #: expiry and the administrator switch resolved together, so a client never
    #: has to re-derive the rule.
    active: bool
    #: The administrator switch on its own, so an admin screen can show *why*
    #: an otherwise valid licence is not granting access.
    enabled: bool


class AppResponse(BaseModel):
    """One app as the launcher and the Explore catalogue see it.

    Deliberately one shape for both surfaces, carrying every app S3K offers
    rather than only the ones held. A launcher that fetched just the
    entitlements could not draw the "Explore" half without a second contract,
    and the two would drift.
    """

    code: str
    name: str
    summary: str
    description: str
    #: A lucide-react icon name. The frontend resolves it against an explicit
    #: allow-list -- never a dynamic import on a server-supplied string.
    icon: str
    #: Where "Open" lands. ``None`` whenever the app is not openable, so a
    #: client that ignores ``state`` still cannot route into nothing.
    route: str | None
    availability: str
    sort_order: int
    #: The single field a client should branch on. Everything below is the
    #: evidence behind it, exposed so an admin screen can explain the verdict.
    #:
    #: ``OPEN``          held, switched on, and openable now.
    #: ``DISABLED``      licensed, but an administrator has switched it off.
    #: ``NOT_LICENSED``  shipped, but this organization holds no usable grant.
    #: ``COMING_SOON``   not built. Never openable by anyone.
    state: str
    entitled: bool
    enabled: bool


class CatalogueEntryResponse(BaseModel):
    """One product as the *signup wizard* sees it, before any tenant exists.

    Carries no entitlement fields, because there is no organization to resolve
    them against yet — and deliberately so: a shape with an ``entitled`` field
    that is always ``false`` invites a client to read it as a verdict rather
    than as "not asked". ``self_serve`` is the only actionable flag here: it
    says whether choosing this app at signup will do anything.
    """

    code: str
    name: str
    summary: str
    description: str
    icon: str
    availability: str
    #: Whether a brand-new organization may be entitled to this by signing up.
    self_serve: bool
    sort_order: int

    model_config = {"from_attributes": True}


class AppEnablementRequest(BaseModel):
    """Switch a held product on or off for the whole organization."""

    enabled: bool


__all__ = [
    "AppEnablementRequest",
    "AppResponse",
    "CatalogueEntryResponse",
    "EntitlementResponse",
    "ProductResponse",
]
