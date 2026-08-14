"""Top-level API router composition.

Two routers are exposed:

``root_router``  — unversioned operational endpoints (health probes) mounted at
                   ``/`` so orchestrators have a stable path.
``api_router``   — the versioned business API mounted under ``settings.api_prefix``.

This module is the composition root for HTTP: it is the one place allowed to
import both Platform and product routers (see the lint exemption in
``pyproject.toml``). Nothing else in the Platform layer may reference a product.

Path layout follows doc 11:

    /api/v1/auth/*            authentication
    /api/v1/organizations/*   tenants and membership
    /api/v1/roles/*           RBAC
    /api/v1/crm/*             S3K CRM business resources
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import health
from app.platform.auth import router as auth_router
from app.platform.authorization import router as authorization_router
from app.platform.organizations import router as organizations_router
from app.products.crm.accounts import router as accounts_router
from app.products.crm.dashboard import router as dashboard_router
from app.products.crm.leads import router as leads_router
from app.products.crm.opportunities import router as opportunities_router

root_router = APIRouter()
root_router.include_router(health.router)

api_router = APIRouter()

# --- Shared Platform routers -----------------------------------------------
api_router.include_router(auth_router.router, prefix="/auth", tags=["platform:auth"])
api_router.include_router(
    organizations_router.router, prefix="/organizations", tags=["platform:organizations"]
)
api_router.include_router(
    authorization_router.router, prefix="/roles", tags=["platform:authorization"]
)

# --- S3K CRM routers --------------------------------------------------------
api_router.include_router(
    dashboard_router.router, prefix="/crm/dashboard", tags=["crm:dashboard"]
)
api_router.include_router(accounts_router.router, prefix="/crm/accounts", tags=["crm:accounts"])
api_router.include_router(leads_router.router, prefix="/crm/leads", tags=["crm:leads"])
api_router.include_router(
    opportunities_router.router, prefix="/crm/opportunities", tags=["crm:opportunities"]
)

__all__ = ["api_router", "root_router"]
