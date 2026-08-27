"""Data access for products and entitlements."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.products.models import Product, ProductEntitlement


class ProductRepository:
    """Reads the catalogue and one organization's grants."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def get_product_by_code(self, code: str) -> Product | None:
        result = await self._session.execute(
            select(Product).where(Product.code == code)
        )
        return result.scalar_one_or_none()

    async def get_entitlement(
        self, *, organization_id: uuid.UUID, code: str
    ) -> ProductEntitlement | None:
        """One organization's grant for one product code, or ``None``.

        Joined on ``products`` rather than taking a product id, because every
        caller knows the code and none of them should have to resolve it
        first -- a two-step lookup is a second place to get the tenant filter
        wrong.
        """
        result = await self._session.execute(
            select(ProductEntitlement)
            .join(Product, Product.id == ProductEntitlement.product_id)
            .where(
                ProductEntitlement.organization_id == organization_id,
                Product.code == code,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, instance: Product | ProductEntitlement) -> None:
        self._session.add(instance)
        await self._session.flush()


__all__ = ["ProductRepository"]
