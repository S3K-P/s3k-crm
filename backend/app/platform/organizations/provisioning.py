"""Product provisioning hooks for a newly created organization.

**The problem this solves.** A brand-new tenant needs more than a row in
``platform.organizations`` before its products are usable — the CRM, for one,
cannot create an opportunity until a default pipeline and its stages exist.
That setup belongs to the CRM, but the code that creates organizations is
Platform, and ARCHITECTURE-BOUNDARIES.md rule 1 forbids Platform from importing
a product. ``app.bootstrap`` gets to call ``OpportunityService`` directly only
because it is an operator entrypoint with an explicit lint exemption; an HTTP
route in ``app/platform/`` has no such licence, and giving it one would put a
CRM import inside the Platform layer for every future reader to copy.

**The inversion.** Products register a callable here; the composition root
(``app.api.router``) is the one module allowed to see both layers and does the
registering. It is the same shape the documents module uses for attachment
access checks, deliberately, so there is one pattern to learn rather than two.

**Failure policy.** A hook that raises aborts the whole signup transaction.
That is the intended behaviour: a half-provisioned tenant — entitled to the
CRM but with no pipeline — is a state somebody has to notice and repair by
hand, and it would present to the customer as a broken product on their first
visit. Better to fail the signup and leave nothing behind.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

#: Called once per newly created organization, inside its transaction.
#: ``actor_id`` is the user who created it, for authorship columns.
ProvisioningHook = Callable[[AsyncSession, uuid.UUID, uuid.UUID | None], Awaitable[None]]

_hooks: list[ProvisioningHook] = []


def register_provisioning_hook(hook: ProvisioningHook) -> None:
    """Register a product's first-run setup. Idempotent per callable.

    Guarding against double registration matters because the composition root
    is imported once per process but test suites build the application many
    times; without it the CRM's pipeline setup would run once per application
    instance ever constructed.
    """
    if hook in _hooks:
        return
    _hooks.append(hook)


async def run_provisioning_hooks(
    session: AsyncSession, organization_id: uuid.UUID, actor_id: uuid.UUID | None = None
) -> None:
    """Run every registered hook for a newly created organization.

    Deliberately **not** exception-swallowing — see the module docstring on why
    a partially provisioned tenant is worse than a failed signup.
    """
    for hook in _hooks:
        await hook(session, organization_id, actor_id)
    logger.info(
        "organization_provisioned",
        organization_id=str(organization_id),
        hooks=len(_hooks),
    )


def registered_hook_count() -> int:
    """How many hooks are registered. For tests and diagnostics."""
    return len(_hooks)


__all__ = [
    "ProvisioningHook",
    "register_provisioning_hook",
    "registered_hook_count",
    "run_provisioning_hooks",
]
