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

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    false,
    func,
    true,
)
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


class ProductAvailability(enum.StrEnum):
    """Whether the product has been *built*, as opposed to whether it is sold.

    :class:`ProductStatus` answers the commercial question and cannot answer
    this one. Keeping them apart is what lets the catalogue advertise an app
    S3K has not shipped yet without marking it sellable — and what lets
    :meth:`ProductService.grant` refuse to entitle anything there is no
    application behind.
    """

    #: Shipped. Has a real ``route`` and may be entitled.
    AVAILABLE = "AVAILABLE"
    #: Catalogue entry only. Never entitled, never routable.
    COMING_SOON = "COMING_SOON"


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One sellable product in the platform catalogue.

    No ``organization_id``: the catalogue is the same for everyone, which is
    why this table is RLS-exempt and why the exemption is safe. It is also why
    ``code`` is globally unique rather than unique per tenant.

    Beyond identity it carries the presentation fields the app launcher and the
    "Explore S3K Apps" catalogue draw a card from. They live here rather than
    in a frontend constant so that adding an app is a data change and the two
    lists cannot drift apart.
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
    availability: Mapped[ProductAvailability] = mapped_column(
        Enum(
            ProductAvailability,
            name="product_availability",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=ProductAvailability.COMING_SOON,
        server_default=ProductAvailability.COMING_SOON.value,
    )
    #: One line under the app name on a launcher card.
    summary: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    #: The longer blurb on the Explore page.
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    #: A lucide-react icon name, resolved against an explicit allow-list on the
    #: frontend — never interpolated into a dynamic import.
    icon: Mapped[str] = mapped_column(String(40), nullable=False, server_default="Boxes")
    #: Where "Open" lands. ``None`` for anything not AVAILABLE, which is why
    #: the launcher has to treat a missing route as "not openable" rather than
    #: defaulting to the workspace.
    route: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Whether signing up may entitle an organization to this product.
    self_serve: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
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
    #: The organization administrator switch, and the only field on this row a
    #: tenant may write. It **narrows** the licence and can never widen it:
    #: turning it off closes a product the organization holds, turning it back
    #: on restores exactly that and nothing more. ``status`` above stays the
    #: commercial fact, writable only by provisioning — which is the split
    #: ADR-011 requires, since otherwise an administrator toggling a switch
    #: would be licensing their own tenant.
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    def grants_access(self, *, now: dt.datetime) -> bool:
        """Whether this row currently permits opening the product.

        All three tests live here rather than in the query, so the rule has one
        home: a status that is not ACTIVE, an expiry that has passed, or an
        administrator who has switched the product off is refused. ``now`` is
        injected rather than read from the clock so the expiry branch is
        testable without waiting.
        """
        if not self.enabled:
            return False
        if self.status is not EntitlementStatus.ACTIVE:
            return False
        return self.expires_at is None or self.expires_at > now


__all__ = [
    "CRM_PRODUCT_CODE",
    "EntitlementStatus",
    "Product",
    "ProductAvailability",
    "ProductEntitlement",
    "ProductStatus",
]
