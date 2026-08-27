"""SQLAlchemy models for product entitlements (doc 04, ADR-011).

Two tables, and the split between them is the whole point.

``products``              the catalogue. Global reference data: "s3k-crm"
                          means the same thing to every tenant, so this table
                          carries no ``organization_id`` and holds no customer
                          data.
``product_entitlements``  which organization may use which product. Tenant
                          data, and therefore tenant-scoped and RLS-protected
                          like everything else that names a customer.

**Why this exists.** ADR-011: "CRM access is not Books access." Until now the
platform had one product and the distinction was free — every authenticated
member of an organization could reach ``/crm/*``. That is the control R10
names as missing and the one GATE 1 criterion still unmet (`P1-W08-BE-01`).
Adding it while CRM is the only product is cheap; adding it after a second
product ships means auditing every route that already assumed access.

An entitlement is deliberately **not** a permission. Permissions answer *what
may this member do inside a product they already have*; an entitlement answers
*may this organization open the product at all*. Conflating them would put
licensing into the RBAC matrix, where an administrator could grant their own
organization a product it has not been sold.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

PLATFORM_SCHEMA = "platform"

#: The CRM's code in the catalogue. The one product that exists today.
CRM_PRODUCT_CODE = "s3k-crm"


class ProductStatus(enum.StrEnum):
    """Whether a product is offered at all (doc 04 ``ProductStatus``)."""

    ACTIVE = "ACTIVE"
    #: Still sold, but new entitlements are not being granted.
    DEPRECATED = "DEPRECATED"
    #: Withdrawn. Existing entitlements stop granting access.
    RETIRED = "RETIRED"


class EntitlementStatus(enum.StrEnum):
    """Whether one organization's grant is currently good (doc 04)."""

    ACTIVE = "ACTIVE"
    #: Withheld without being revoked — non-payment, say. Reversible.
    SUSPENDED = "SUSPENDED"
    #: Ended deliberately. Kept as a row so the history survives.
    REVOKED = "REVOKED"


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One sellable product in the platform catalogue.

    No ``organization_id``: the catalogue is the same for everyone, which is
    why this table is RLS-exempt and why the exemption is safe. It is also why
    ``code`` is globally unique rather than unique per tenant.
    """

    __tablename__ = "products"
    __table_args__ = (
        Index("uq_products_code", "code", unique=True),
        {"schema": PLATFORM_SCHEMA},
    )

    #: Stable machine identifier — "s3k-crm", "s3k-books". Referenced by the
    #: access check, so it is the field that must never be renamed casually.
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="product_status", schema=PLATFORM_SCHEMA, native_enum=True),
        nullable=False,
        default=ProductStatus.ACTIVE,
        server_default=ProductStatus.ACTIVE.value,
    )


class ProductEntitlement(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One organization's licence to use one product.

    ``expires_at`` is nullable and means "no expiry". A grant that has expired
    is not deleted: the row is the record that access once existed, and the
    check reads the clock rather than trusting a status somebody has to
    remember to update.
    """

    __tablename__ = "product_entitlements"
    __table_args__ = (
        Index(
            "uq_product_entitlements_organization_id_product_id",
            "organization_id",
            "product_id",
            unique=True,
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{PLATFORM_SCHEMA}.products.id",
            ondelete="RESTRICT",
            name="fk_product_entitlements_product_id_products",
        ),
        nullable=False,
    )
    status: Mapped[EntitlementStatus] = mapped_column(
        Enum(
            EntitlementStatus,
            name="entitlement_status",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=EntitlementStatus.ACTIVE,
        server_default=EntitlementStatus.ACTIVE.value,
    )
    granted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: ``None`` means the grant does not expire.
    expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def grants_access(self, *, now: dt.datetime) -> bool:
        """Whether this row currently permits opening the product.

        Both halves are checked here rather than in the query, so the rule has
        one home: a status that is not ACTIVE, or an expiry that has passed,
        is refused. ``now`` is injected rather than read from the clock so the
        expiry branch is testable without waiting.
        """
        if self.status is not EntitlementStatus.ACTIVE:
            return False
        return self.expires_at is None or self.expires_at > now


__all__ = [
    "CRM_PRODUCT_CODE",
    "EntitlementStatus",
    "Product",
    "ProductEntitlement",
    "ProductStatus",
]
