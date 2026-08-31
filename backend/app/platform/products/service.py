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
import enum
import uuid
from collections.abc import Collection
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import provisioning_scope
from app.platform.products.models import (
    CRM_PRODUCT_CODE,
    EntitlementStatus,
    Product,
    ProductAvailability,
    ProductEntitlement,
    ProductStatus,
)
from app.platform.products.repository import ProductRepository

logger = structlog.get_logger(__name__)


class AppState(enum.StrEnum):
    """What a client should do with an app, decided once on the server."""

    #: Held, switched on, openable now.
    OPEN = "OPEN"
    #: Licensed, but an administrator has switched it off for the organization.
    DISABLED = "DISABLED"
    #: Shipped, but this organization holds no usable grant.
    NOT_LICENSED = "NOT_LICENSED"
    #: Not built. Never openable, by anyone, in any organization.
    COMING_SOON = "COMING_SOON"


@dataclass(frozen=True, slots=True)
class AppView:
    """One app resolved against one organization.

    Carries the verdict *and* the evidence behind it. The evidence is not
    decoration: an administrator looking at a greyed-out app needs to know
    whether it is unlicensed or merely switched off, and those two have
    different fixes.
    """

    product: Product
    state: AppState
    #: A usable licence exists, whatever the administrator switch says.
    entitled: bool
    #: The administrator switch. ``False`` when no entitlement exists at all.
    enabled: bool
    #: ``None`` unless the app is openable right now.
    route: str | None


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

        # A COMING_SOON product is a catalogue entry with no application behind
        # it. Refusing the grant here rather than in the caller means no path —
        # signup, bootstrap, a future billing webhook — can produce an
        # entitlement that opens onto nothing, and the launcher never has to
        # defend against a licence it cannot route.
        if product.availability is not ProductAvailability.AVAILABLE:
            logger.warning(
                "product_not_available_for_grant",
                code=code,
                availability=product.availability.value,
                organization_id=str(organization_id),
            )
            return None

        # Both the lookup and the write run scoped to the organization being
        # granted. The caller is organization creation, which runs either with
        # no tenant context at all (bootstrap, registration) or with one still
        # naming the *creating* organization; under a role that does not
        # bypass RLS -- every role outside local development -- the policy
        # would otherwise hide the existing row and then refuse the INSERT
        # that follows, turning re-provisioning into a unique-constraint
        # violation rather than the idempotent repair it is meant to be.
        async with provisioning_scope(self._repository.session, organization_id):
            existing = await self._repository.get_entitlement(
                organization_id=organization_id, code=code
            )
            if existing is not None:
                existing.status = EntitlementStatus.ACTIVE
                existing.expires_at = expires_at
                await self._repository.session.flush()
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

    async def describe_apps(self, organization_id: uuid.UUID) -> list[AppView]:
        """Every app S3K offers, resolved against what this organization holds.

        The launcher, the Explore catalogue and the admin Applications screen
        are three views of this one answer, so the verdict is computed here
        rather than three times in the UI. A client that ignores
        :attr:`AppView.state` and reads the evidence fields instead can reach
        the same conclusion, but it cannot reach a *different* one.

        Note the ordering of the branches: availability is tested before the
        licence. An app that has not been built reports ``COMING_SOON`` even in
        the impossible case that a row somehow entitles an organization to it,
        so a bad grant degrades to "not yet" rather than to an open door.
        """
        now = dt.datetime.now(dt.UTC)
        held = {
            product.code: entitlement
            for entitlement, product in await self.entitlements_for(organization_id)
        }

        views: list[AppView] = []
        for product in await self._repository.list_products():
            entitlement = held.get(product.code)

            # "Licensed" deliberately ignores ``enabled``: an administrator who
            # switched the app off still holds the licence, and the admin
            # screen has to be able to say so in order to offer it back.
            licensed = (
                entitlement is not None
                and product.status is ProductStatus.ACTIVE
                and entitlement.status is EntitlementStatus.ACTIVE
                and (entitlement.expires_at is None or entitlement.expires_at > now)
            )
            enabled = entitlement.enabled if entitlement is not None else False

            if product.availability is not ProductAvailability.AVAILABLE:
                state = AppState.COMING_SOON
            elif not licensed:
                state = AppState.NOT_LICENSED
            elif not enabled:
                state = AppState.DISABLED
            else:
                state = AppState.OPEN

            views.append(
                AppView(
                    product=product,
                    state=state,
                    entitled=licensed,
                    enabled=enabled,
                    # Withheld unless the app is actually openable, so a client
                    # that renders a link without checking the state still has
                    # nowhere wrong to send anybody.
                    route=product.route if state is AppState.OPEN else None,
                )
            )
        return views

    async def catalogue(self) -> list[Product]:
        """Every product S3K lists, in display order.

        Global reference data and therefore not tenant-filtered. It carries no
        customer information, which is why it can be served to any
        authenticated caller without leaking anything about other tenants.
        """
        return await self._repository.list_products()

    async def entitlements_for(
        self, organization_id: uuid.UUID
    ) -> list[tuple[ProductEntitlement, Product]]:
        """One organization's grants, paired with their catalogue entries."""
        return await self._repository.list_entitlements(organization_id=organization_id)

    async def set_enabled(
        self, *, organization_id: uuid.UUID, code: str, enabled: bool
    ) -> ProductEntitlement | None:
        """Switch a held product on or off for the whole organization.

        Returns ``None`` when the organization holds no entitlement for
        ``code`` — which is the case that keeps this from being a grant. There
        is no branch here that creates a row, so an administrator calling it
        for a product nobody sold them changes nothing and is told so; the only
        reachable outcome is narrowing, or restoring, a licence that already
        exists. That is the whole reason this is safe to expose as an API when
        :meth:`grant` is not.
        """
        entitlement = await self._repository.get_entitlement(
            organization_id=organization_id, code=code
        )
        if entitlement is None:
            return None

        entitlement.enabled = enabled
        await self._repository.session.flush()
        logger.info(
            "product_enablement_changed",
            code=code,
            enabled=enabled,
            organization_id=str(organization_id),
        )
        return entitlement

    async def grant_self_serve_products(
        self, *, organization_id: uuid.UUID, codes: Collection[str]
    ) -> list[str]:
        """Entitle a newly created organization to the apps it chose at signup.

        ``codes`` arrives from an unauthenticated signup payload, so it is
        treated as a *filter over* what self-service already permits rather
        than as a list of things to grant. Anything not marked ``self_serve``
        in the catalogue is dropped silently — a caller who posts
        ``["s3k-finance"]`` gets no finance entitlement and no error telling
        them the code was real, because neither outcome should depend on what
        the client asked for.

        Returns the codes actually granted, so the caller can report the truth
        rather than echoing the request back.
        """
        eligible = {
            product.code
            for product in await self._repository.list_products()
            if product.self_serve and product.availability is ProductAvailability.AVAILABLE
        }
        granted: list[str] = []
        for code in codes:
            if code not in eligible:
                logger.info(
                    "self_serve_product_rejected",
                    code=code,
                    organization_id=str(organization_id),
                )
                continue
            if await self.grant(organization_id=organization_id, code=code) is not None:
                granted.append(code)
        return granted


def products_for_session(session: AsyncSession) -> ProductService:
    """Build the service from a session, for callers holding only that."""
    return ProductService(ProductRepository(session))


__all__ = ["AppState", "AppView", "ProductService", "products_for_session"]
