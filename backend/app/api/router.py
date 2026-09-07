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
    /api/v1/notifications/*   the caller's own in-app notifications
    /api/v1/crm/*             S3K CRM business resources
    /api/v1/crm/reports       the built-in report library, gated per report
    /api/v1/crm/search        cross-entity search, permission-filtered in-query
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import health
from app.platform.ai import router as ai_router
from app.platform.audit import router as audit_router
from app.platform.auth import router as auth_router
from app.platform.authorization import router as authorization_router
from app.platform.documents import router as documents_router
from app.platform.notifications import router as notifications_router
from app.platform.notifications.service import register_reminder_source
from app.platform.organizations import router as organizations_router
from app.platform.organizations.provisioning import register_provisioning_hook
from app.platform.products import router as products_router
from app.platform.products.models import CRM_PRODUCT_CODE
from app.platform.products.policies import product_gate
from app.platform.teams import router as teams_router
from app.products.crm.accounts import router as accounts_router
from app.products.crm.activities import router as activities_router
from app.products.crm.campaigns import router as campaigns_router
from app.products.crm.contacts import router as contacts_router
from app.products.crm.dashboard import router as dashboard_router
from app.products.crm.imports import router as imports_router
from app.products.crm.leads import router as leads_router
from app.products.crm.leads import source_router as lead_sources_router
from app.products.crm.market_insights import router as market_insights_router
from app.products.crm.notes import router as notes_router
from app.products.crm.opportunities import router as opportunities_router
from app.products.crm.reports import router as reports_router
from app.products.crm.search import router as search_router
from app.products.crm.shared.attachments import crm_entity_access
from app.products.crm.shared.provisioning import crm_provisioning_hook
from app.products.crm.shared.reminders import crm_reminder_source
from app.products.crm.tasks import router as tasks_router

root_router = APIRouter()
root_router.include_router(health.router)

api_router = APIRouter()

# --- Shared Platform routers -----------------------------------------------
api_router.include_router(auth_router.router, prefix="/auth", tags=["platform:auth"])
api_router.include_router(
    organizations_router.router, prefix="/organizations", tags=["platform:organizations"]
)
# Redemption sits outside ``/organizations`` because the person accepting is
# not a member yet and has no tenant context to scope the path to.
api_router.include_router(
    organizations_router.invitation_router,
    prefix="/invitations",
    tags=["platform:organizations"],
)
api_router.include_router(
    authorization_router.router, prefix="/roles", tags=["platform:authorization"]
)
api_router.include_router(audit_router.router, prefix="/audit-logs", tags=["platform:audit"])
# The AI gateway (ADR-016). Not behind the CRM product gate: ``/ai/status``
# answers whether AI is connected at all, which the AI section needs in order
# to render its "not connected" state, and prompt configuration is
# organization-level administration rather than a CRM resource.
api_router.include_router(ai_router.router, prefix="/ai", tags=["platform:ai"])
# Deliberately *not* behind the product gate: a caller has to be able to find
# out which products their organization holds, and gating that on holding one
# would make the 403 unexplainable to the person hitting it.
api_router.include_router(products_router.router, prefix="/products", tags=["platform:products"])
api_router.include_router(teams_router.router, prefix="/teams", tags=["platform:teams"])
api_router.include_router(
    teams_router.department_router, prefix="/departments", tags=["platform:teams"]
)

# Notifications are the caller's own mailbox (see policies.py: no permission
# module gates it), so it is mounted here rather than behind the CRM product
# gate below — a user without CRM access could still hold a Platform-level
# notification in future. The CRM is the only source of reminders today
# (register_reminder_source, beside register_provisioning_hook below), but the
# module itself has no CRM dependency.
api_router.include_router(
    notifications_router.router, prefix="/notifications", tags=["platform:notifications"]
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

# The CRM's first-run setup for a newly created organization. Same inversion,
# and for the same reason: ``POST /organizations`` lives in the Platform layer
# and may not import a product, but a tenant with no pipeline cannot create an
# opportunity, so the CRM would be broken on the customer's first visit.
# ``app.bootstrap`` calls ``ensure_default_pipeline`` directly because it holds
# a lint exemption an HTTP route has no business borrowing.
register_provisioning_hook(crm_provisioning_hook)

# Same inversion again: deciding which reminders are due needs CRM data
# (meetings, tasks) that Platform may not import. Registered here rather than
# beside the router include above because nothing that consumes it is an HTTP
# route — see app.platform.notifications.policies and .service.
register_reminder_source(crm_reminder_source)

# --- S3K CRM routers --------------------------------------------------------
#
# Every CRM route hangs off this one router, and the router carries the
# product gate (ADR-011, `P1-W08-BE-02`). Declaring it here once means a new
# CRM module cannot be mounted without it: the dependency is attached to the
# parent, so it applies to every route beneath and travels with them if the
# prefix ever changes. That is the property an ASGI middleware matching on the
# string "/crm/" would not have — see CR18.
#
# It runs before any handler and refuses with 403 `product_not_licensed` when
# the caller's organization holds no usable entitlement, whatever CRM
# permissions their role grants.
crm_router = APIRouter(dependencies=[product_gate(CRM_PRODUCT_CODE)])

crm_router.include_router(
    dashboard_router.router, prefix="/crm/dashboard", tags=["crm:dashboard"]
)
crm_router.include_router(accounts_router.router, prefix="/crm/accounts", tags=["crm:accounts"])
crm_router.include_router(contacts_router.router, prefix="/crm/contacts", tags=["crm:contacts"])
crm_router.include_router(
    lead_sources_router.router, prefix="/crm/lead-sources", tags=["crm:lead-sources"]
)
crm_router.include_router(leads_router.router, prefix="/crm/leads", tags=["crm:leads"])
crm_router.include_router(
    opportunities_router.router, prefix="/crm/opportunities", tags=["crm:opportunities"]
)
crm_router.include_router(campaigns_router.router, prefix="/crm/campaigns", tags=["crm:campaigns"])
crm_router.include_router(
    activities_router.router, prefix="/crm/activities", tags=["crm:activities"]
)
crm_router.include_router(tasks_router.router, prefix="/crm/tasks", tags=["crm:tasks"])
crm_router.include_router(notes_router.router, prefix="/crm/notes", tags=["crm:notes"])
crm_router.include_router(
    market_insights_router.router,
    prefix="/crm/market-insights",
    tags=["crm:market-insights"],
)
# Reports and search share a shape: neither can name its permission when the
# route is declared. Search spans four modules at once; a report names the one
# module it reads, which arrives as a path parameter. Both therefore take the
# permission snapshot and decide inside — see their routers.
crm_router.include_router(reports_router.router, prefix="/crm/reports", tags=["crm:reports"])
crm_router.include_router(search_router.router, prefix="/crm/search", tags=["crm:search"])
# Import chooses its entity from a path parameter, so the permission it needs
# is not known when the route is declared. The route authorizes against the
# named entity's own module inside the handler — see its router.
crm_router.include_router(imports_router.router, prefix="/crm/imports", tags=["crm:imports"])

# Mounted last, so every CRM route above is already behind the gate.
api_router.include_router(crm_router)

__all__ = ["api_router", "root_router"]
