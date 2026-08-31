"""The CRM's first-run setup for a newly created organization.

Registered with ``app.platform.organizations.provisioning`` by the composition
root. It lives on this side of the boundary because the work is CRM work — the
Platform layer must not know that a pipeline is a thing (ADR-004,
ARCHITECTURE-BOUNDARIES.md rule 3).

What it guarantees: a tenant that has just been created can immediately create
an opportunity. Without a default pipeline and its stages the CRM opens onto a
dashboard that cannot be populated and a Deals screen that refuses every save,
which is how a brand-new customer would meet the product.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.opportunities.service import OpportunityService


async def crm_provisioning_hook(
    session: AsyncSession, organization_id: uuid.UUID, actor_id: uuid.UUID | None = None
) -> None:
    """Create the organization's default pipeline and stages.

    Idempotent — :meth:`OpportunityService.ensure_default_pipeline` returns an
    existing pipeline unchanged, so re-provisioning repairs rather than
    duplicates. It also handles its own ``provisioning_scope``, which this
    needs: the call happens in the transaction that created the organization,
    before that organization can have a request context, and both pipeline
    tables are RLS-FORCEd.
    """
    await OpportunityService(session).ensure_default_pipeline(
        organization_id, actor_id=actor_id
    )


__all__ = ["crm_provisioning_hook"]
