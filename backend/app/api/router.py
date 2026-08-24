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
    /api/v1/audit-logs/*      the audit trail (read-only, admin permission)
    /api/v1/attachments/*     file metadata + pre-signed object-storage URLs
    /api/v1/crm/*             S3K CRM business resources
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import health
from app.platform.audit import router as audit_router
from app.platform.auth import router as auth_router
from app.platform.authorization import router as authorization_router
from app.platform.documents import router as documents_router
from app.platform.organizations import router as organizations_router
from app.platform.teams import router as teams_router
from app.products.crm.accounts import router as accounts_router
from app.products.crm.activities import router as activities_router
from app.products.crm.campaigns import router as campaigns_router
from app.products.crm.contacts import router as contacts_router
from app.products.crm.dashboard import router as dashboard_router
from app.products.crm.leads import router as leads_router
from app.products.crm.leads import source_router as lead_sources_router
from app.products.crm.notes import router as notes_router
from app.products.crm.opportunities import router as opportunities_router
from app.products.crm.shared.attachments import crm_entity_access
from app.products.crm.tasks import router as tasks_router

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
api_router.include_router(audit_router.router, prefix="/audit-logs", tags=["platform:audit"])
api_router.include_router(teams_router.router, prefix="/teams", tags=["platform:teams"])
api_router.include_router(
    teams_router.department_router, prefix="/departments", tags=["platform:teams"]
)

# Attachments are the one place a Platform module needs a product's answer:
# whether the caller may reach the CRM record a file hangs off depends on
# ``owner_id`` and on record-level visibility, neither of which Platform may
# import (ARCHITECTURE-BOUNDARIES.md rule 1). The documents module inverts it
# behind a Protocol; this file — already the one module permitted to see both
# layers — supplies the CRM implementation.
#
# Registered *before* the router is included, and the registry denies
# everything until it is, so an attachment route can never be served without a
# record-access check behind it.
documents_router.register_entity_access(crm_entity_access)
api_router.include_router(
    documents_router.router, prefix="/attachments", tags=["platform:documents"]
)

# --- S3K CRM routers --------------------------------------------------------
api_router.include_router(
    dashboard_router.router, prefix="/crm/dashboard", tags=["crm:dashboard"]
)
api_router.include_router(accounts_router.router, prefix="/crm/accounts", tags=["crm:accounts"])
api_router.include_router(contacts_router.router, prefix="/crm/contacts", tags=["crm:contacts"])
api_router.include_router(
    lead_sources_router.router, prefix="/crm/lead-sources", tags=["crm:lead-sources"]
)
api_router.include_router(leads_router.router, prefix="/crm/leads", tags=["crm:leads"])
api_router.include_router(
    opportunities_router.router, prefix="/crm/opportunities", tags=["crm:opportunities"]
)
api_router.include_router(campaigns_router.router, prefix="/crm/campaigns", tags=["crm:campaigns"])
api_router.include_router(
    activities_router.router, prefix="/crm/activities", tags=["crm:activities"]
)
api_router.include_router(tasks_router.router, prefix="/crm/tasks", tags=["crm:tasks"])
api_router.include_router(notes_router.router, prefix="/crm/notes", tags=["crm:notes"])

__all__ = ["api_router", "root_router"]
