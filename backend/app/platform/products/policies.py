"""The product-access gate (ADR-011, `P1-W08-BE-02`, risk R10).

**What this refuses, and why it is not RBAC.** Permissions answer *what may
this member do inside a product*. This answers the question before it: *may
this organization open the product at all*. A rep with every CRM permission in
the catalogue still gets 403 here if their organization is not licensed for
the CRM, and no permission grant can change that — which is the point, because
otherwise an administrator could license their own tenant.

**Where it runs.** `P1-W08-BE-02` calls for "middleware ... before any
``/crm/*`` handler runs". It is implemented as a router-level dependency
declared once at the composition root instead (CR18). Same guarantee — FastAPI
resolves dependencies before the handler, and a dependency on the parent
router applies to every route mounted beneath it, so a new CRM route cannot be
added without the gate. The reason to prefer it is the failure mode: ASGI
middleware matches on a path prefix it holds as a string, so mounting the CRM
under a different prefix would silently stop protecting it. A parent-router
dependency is attached to the routes themselves and moves with them.

**Why it depends on ``CurrentPrincipal`` rather than reading tenant context
directly.** Ordering, and it is not cosmetic. A router-level dependency
resolves *before* the route's own, so the first version — which called
``require_tenant_context()`` — ran ahead of authentication and turned every
unauthenticated request into ``403 product_not_licensed`` instead of ``401``.
That conflates "we do not know who you are" with "your organization has not
bought this", which is exactly the distinction
``test_an_unauthenticated_request_is_401_not_403`` exists to protect: a caller
who is merely logged out would be told to contact sales.

Depending on ``CurrentPrincipal`` puts the auth chain *inside* this
dependency, so a missing or bad token raises 401 before the entitlement is
ever queried. It also means the organization has already been proven to belong
to the caller by the time the check runs, rather than being read from raw
context.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from fastapi import Depends, params, status

from app.core.database import DbSession
from app.core.exceptions import AppError
from app.platform.auth.dependencies import CurrentPrincipal
from app.platform.products.service import products_for_session

logger = structlog.get_logger(__name__)


class ProductNotLicensedError(AppError):
    """The organization has no usable entitlement for this product.

    403 rather than 404: the caller is authenticated and their organization is
    real, so hiding the product's existence buys nothing — every tenant knows
    the CRM exists. What they need to be told is that *their* organization
    cannot open it, because the fix is commercial rather than technical and a
    404 would send them to support with the wrong question.
    """

    status_code = status.HTTP_403_FORBIDDEN
    code = "product_not_licensed"
    message = "This organization is not licensed for that product."


def require_product(code: str) -> Callable[..., Awaitable[None]]:
    """Build a dependency refusing callers whose organization lacks ``code``.

    Mounted once on the parent router, as::

        crm_router = APIRouter(dependencies=[Depends(require_product("s3k-crm"))])

    Returns ``None`` — nothing downstream needs the entitlement, only the
    refusal. Keeping it valueless means no handler can start depending on it
    and quietly turn a gate into a data source.
    """

    async def dependency(principal: CurrentPrincipal, session: DbSession) -> None:
        entitled = await products_for_session(session).is_entitled(
            organization_id=principal.organization_id, code=code
        )
        if not entitled:
            logger.info(
                "product_not_licensed",
                product=code,
                organization_id=str(principal.organization_id),
            )
            raise ProductNotLicensedError

    return dependency


def product_gate(code: str) -> params.Depends:
    """``require_product`` wrapped for a router's ``dependencies=`` list.

    Annotated as ``params.Depends`` — the class — rather than ``Depends``,
    which is a *function* and therefore not a type. mypy strict rejects the
    latter, and the distinction is easy to miss because the two read
    identically at the call site.
    """
    # ``Depends`` is untyped in FastAPI's stubs, so strict mode sees Any here.
    gate: params.Depends = Depends(require_product(code))
    return gate


__all__ = ["ProductNotLicensedError", "product_gate", "require_product"]
