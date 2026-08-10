"""Top-level API router composition.

Two routers are exposed:

``root_router``  — unversioned operational endpoints (health probes) mounted at
                   ``/`` so orchestrators have a stable path.
``api_router``   — the versioned business API mounted under ``settings.api_prefix``.

Product routers are registered on ``api_router`` as modules are implemented.
Platform routers are registered first; a product module must never be imported
by the Platform layer (see ARCHITECTURE-BOUNDARIES.md).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import health

root_router = APIRouter()
root_router.include_router(health.router)

api_router = APIRouter()

# --- Shared Platform routers (Phase 1) -------------------------------------
# api_router.include_router(auth.router, prefix="/auth", tags=["platform:auth"])
# api_router.include_router(organizations.router, prefix="/organizations", ...)

# --- Product routers (Phase 2+) --------------------------------------------
# api_router.include_router(accounts.router, prefix="/accounts", tags=["crm:accounts"])

__all__ = ["api_router", "root_router"]
