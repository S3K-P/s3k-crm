"""Product entitlements — the module's public interface (ADR-011).

One question matters here: **may this organization open this product?**
:meth:`ProductService.is_entitled` answers it, and
:func:`app.platform.products.policies.require_product` is what makes every
route under a product's prefix ask.

Granting is the other half, and it is deliberately not an API. Entitlements
are provisioned — by the migration that seeds them, by ``app.bootstrap`` when
it creates an organization, or eventually by a billing integration. An
endpoint that granted them would let an administrator license their own
organization to a product nobody sold them, which is exactly the boundary
ADR-011 exists to draw.
"""

from __future__ import annotations

import datetime as dt
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.products.models import (
    CRM_PRODUCT_CODE,
    EntitlementStatus,
    ProductEntitlement,
    ProductStatus,
)
from app.platform.products.repository import ProductRepository

logger = structlog.get_logger(__name__)


class ProductService:
    """The entitlement check, and the provisioning that feeds it."""

    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    async def is_entitled(self, *, organization_id: uuid.UUID, code: str) -> bool:
        """Whether ``organization_id`` may currently open ``code``.

        Three things must hold, and all three are checked here rather than
        spread between a query and a caller:

        * a grant exists for this organization and product;
        * that grant is ACTIVE and unexpired (:meth:`ProductEntitlement.grants_access`);
        * the product itself is still ACTIVE — a RETIRED product is closed to
          everyone, and reading the entitlement alone would keep letting the
          last tenants in after it was withdrawn.

        Fails closed: anything missing is ``False``.
        """
        entitlement = await self._repository.get_entitlement(
            organization_id=organization_id, code=code
        )
        if entitlement is None:
            return False

        product = await self._repository.get_product_by_code(code)
        if product is None or product.status is not ProductStatus.ACTIVE:
            return False

        return entitlement.grants_access(now=dt.datetime.now(dt.UTC))

    async def grant(
        self,
        *,
        organization_id: uuid.UUID,
        code: str,
        expires_at: dt.datetime | None = None,
    ) -> ProductEntitlement | None:
        """Give an organization access to a product. Idempotent.

        Returns ``None`` when the product code is not in the catalogue, rather
        than raising: the only caller today is organization creation, and a
        catalogue that has not been seeded yet must not stop a tenant from
        being created. The access check fails closed regardless, so the worst
        case is a visible 403 rather than a silent grant.

        An existing grant is reactivated rather than duplicated, so re-running
        provisioning repairs a suspended entitlement instead of colliding with
        the unique constraint.
        """
        product = await self._repository.get_product_by_code(code)
        if product is None:
            logger.warning(
                "product_not_in_catalogue",
                code=code,
                organization_id=str(organization_id),
            )
            return None

        existing = await self._repository.get_entitlement(
            organization_id=organization_id, code=code
        )
        if existing is not None:
            existing.status = EntitlementStatus.ACTIVE
            existing.expires_at = expires_at
            return existing

        entitlement = ProductEntitlement(
            organization_id=organization_id,
            product_id=product.id,
            status=EntitlementStatus.ACTIVE,
            expires_at=expires_at,
        )
        await self._repository.add(entitlement)
        logger.info(
            "product_entitlement_granted",
            code=code,
            organization_id=str(organization_id),
        )
        return entitlement

    async def grant_default_products(self, organization_id: uuid.UUID) -> None:
        """Entitle a new organization to everything it is created with.

        Today that is the CRM alone. It lives here rather than inline in the
        organizations service so that adding a second default product is one
        edit in the module that owns the concept — and so the organizations
        module does not need to know a product code.
        """
        await self.grant(organization_id=organization_id, code=CRM_PRODUCT_CODE)


def products_for_session(session: AsyncSession) -> ProductService:
    """Build the service from a session, for callers holding only that."""
    return ProductService(ProductRepository(session))


__all__ = ["ProductService", "products_for_session"]
