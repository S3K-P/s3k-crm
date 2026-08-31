"""HTTP routes for the products module.

Three routes, and the split between them is the ADR-011 boundary made concrete.

``GET /entitlements``            what the active organization is licensed for.
``GET /apps``                    the whole S3K catalogue, resolved against
                                 those licences — what the app launcher and
                                 the Explore page are drawn from.
``PUT /apps/{code}/enablement``  an administrator switching a *held* product
                                 on or off for their organization.

There is still deliberately no route that grants or revokes an entitlement.
The one write exposed here takes a boolean and a product code from the path,
resolves that code against a grant the organization already holds, and does
nothing at all when there is none — so it can only narrow or restore an
existing licence, never create one. An administrator still cannot license
their own organization, which is the line ADR-011 draws.

None of these sit behind ``product_gate``: a caller has to be able to find out
which products their organization holds, and gating that on holding one would
make the 403 unexplainable to the person hitting it.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.database import DbSession
from app.core.exceptions import NotFoundError
from app.platform.auth.dependencies import (
    CurrentPrincipal,
    CurrentUser,
    Principal,
    require_permission,
)
from app.platform.authorization.models import PermissionAction
from app.platform.products.models import Product, ProductEntitlement
from app.platform.products.schemas import (
    AppEnablementRequest,
    AppResponse,
    CatalogueEntryResponse,
    EntitlementResponse,
)
from app.platform.products.service import AppView, products_for_session

router = APIRouter()

#: App enablement is an organization-level setting, so it is gated on the
#: existing ``organizations`` module rather than on a permission invented for
#: it. Manager holds only ``organizations.VIEW`` and User holds nothing there,
#: so this resolves to administrators — without adding a second RBAC concept.
ORGANIZATIONS_MODULE = "organizations"


def _entitlement_response(
    entitlement: ProductEntitlement, product: Product, *, active: bool
) -> EntitlementResponse:
    return EntitlementResponse(
        product_code=product.code,
        product_name=product.name,
        status=entitlement.status.value,
        granted_at=entitlement.granted_at,
        expires_at=entitlement.expires_at,
        active=active,
        enabled=entitlement.enabled,
    )


def _app_response(view: AppView) -> AppResponse:
    return AppResponse(
        code=view.product.code,
        name=view.product.name,
        summary=view.product.summary,
        description=view.product.description,
        icon=view.product.icon,
        route=view.route,
        availability=view.product.availability.value,
        sort_order=view.product.sort_order,
        state=view.state.value,
        entitled=view.entitled,
        enabled=view.enabled,
    )


@router.get("/catalogue", response_model=list[CatalogueEntryResponse])
async def list_catalogue(
    _user: CurrentUser, session: DbSession
) -> list[CatalogueEntryResponse]:
    """The S3K product catalogue, with no organization in the picture.

    Exists for the signup wizard, which has to offer a choice of apps *before*
    the tenant that would be entitled to them exists — so it cannot use
    ``/apps``, which resolves against an organization.

    Authenticated but not tenant-scoped. Authentication is not protecting
    anything secret here: the catalogue is the same public list of S3K products
    for everybody and names no customer. It is required only because the only
    caller is already signed in by this point, and leaving an endpoint open
    that nothing needs open is a habit worth not forming.
    """
    products = await products_for_session(session).catalogue()
    return [
        CatalogueEntryResponse(
            code=product.code,
            name=product.name,
            summary=product.summary,
            description=product.description,
            icon=product.icon,
            availability=product.availability.value,
            self_serve=product.self_serve,
            sort_order=product.sort_order,
        )
        for product in products
    ]


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
    now = dt.datetime.now(dt.UTC)
    service = products_for_session(session)
    rows = await service.entitlements_for(principal.organization_id)

    return [
        _entitlement_response(
            entitlement, product, active=entitlement.grants_access(now=now)
        )
        for entitlement, product in rows
    ]


@router.get("/apps", response_model=list[AppResponse])
async def list_apps(principal: CurrentPrincipal, session: DbSession) -> list[AppResponse]:
    """Every S3K app, resolved against the active organization's licences.

    Membership alone, for the same reason as ``/entitlements``: this *is* the
    app launcher, and a user who cannot enumerate the catalogue cannot be told
    which apps they have. It exposes no tenant data beyond the caller's own —
    the catalogue half is global reference data, and the licence half is read
    through the organization already proven to belong to them.
    """
    views = await products_for_session(session).describe_apps(principal.organization_id)
    return [_app_response(view) for view in views]


@router.put("/apps/{code}/enablement", response_model=AppResponse)
async def set_app_enablement(
    code: str,
    payload: AppEnablementRequest,
    principal: Annotated[
        Principal,
        Depends(require_permission(ORGANIZATIONS_MODULE, PermissionAction.EDIT)),
    ],
    session: DbSession,
) -> AppResponse:
    """Switch a held product on or off for the whole organization.

    404 when the organization holds no entitlement for ``code``, which covers
    both a product nobody sold them and a code that is not in the catalogue at
    all. Neither is distinguished, and neither creates anything: the failure
    mode of a tampered code is a 404, never a grant.

    Raises:
        NotFoundError: the active organization holds no such entitlement.
    """
    entitlement = await products_for_session(session).set_enabled(
        organization_id=principal.organization_id, code=code, enabled=payload.enabled
    )
    if entitlement is None:
        raise NotFoundError("This organization has no entitlement for that product.")

    # Re-read through the same resolver the launcher uses, so the response a
    # client stores is the same shape and the same verdict it would get from
    # ``GET /apps`` a moment later.
    views = await products_for_session(session).describe_apps(principal.organization_id)
    for view in views:
        if view.product.code == code:
            return _app_response(view)

    raise NotFoundError("This organization has no entitlement for that product.")


__all__ = ["router"]
