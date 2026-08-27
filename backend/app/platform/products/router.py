"""HTTP routes for the products module.

One read-only route: what the active organization is licensed for. It exists
so the frontend can hide a product's navigation rather than let someone click
into a 403, and so support can answer "why can't I open the CRM?" without a
database session.

There is deliberately no route that grants or revokes. Entitlements are
provisioned (migration, `app.bootstrap`, a future billing integration); an
endpoint for it would let an administrator license their own organization,
which is the boundary ADR-011 draws.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.core.database import DbSession
from app.platform.auth.dependencies import CurrentPrincipal
from app.platform.products.models import Product, ProductEntitlement
from app.platform.products.schemas import EntitlementResponse

router = APIRouter()


@router.get("/entitlements", response_model=list[EntitlementResponse])
async def list_entitlements(
    principal: CurrentPrincipal, session: DbSession
) -> list[EntitlementResponse]:
    """Products the caller's active organization holds a grant for.

    Membership alone, not a permission: every member needs to know which
    products their organization can open, and gating that on an admin
    permission would mean an ordinary user could not be told why a page is
    missing.
    """
    import datetime as dt

    now = dt.datetime.now(dt.UTC)
    rows = await session.execute(
        select(ProductEntitlement, Product)
        .join(Product, Product.id == ProductEntitlement.product_id)
        .where(ProductEntitlement.organization_id == principal.organization_id)
        .order_by(Product.code)
    )

    return [
        EntitlementResponse(
            product_code=product.code,
            product_name=product.name,
            status=entitlement.status.value,
            granted_at=entitlement.granted_at,
            expires_at=entitlement.expires_at,
            active=entitlement.grants_access(now=now),
        )
        for entitlement, product in rows.all()
    ]


__all__ = ["router"]
