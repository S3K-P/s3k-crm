"""The seam between a record write and the custom-field rules.

:class:`~app.products.crm.shared.service.TenantScopedService` is the funnel
every CRM entity write passes through, and it is where custom values have to be
validated — anywhere else and a module added next year would need somebody to
remember to wire it up. But ``shared`` is infrastructure below the modules: it
may not import ``custom_fields``, which subclasses it, and the import would be
circular even if the boundary allowed it.

So the dependency is inverted, exactly as attachments' record access, the CRM's
first-run provisioning and the reminder source already are: this module holds a
registry, ``app.api.router`` — the one module permitted to see every layer —
registers the real implementation at import time, and the shared service calls
through it without knowing what is on the other side.

**Unregistered means refused, not permitted.** With no resolver installed a
write carrying ``custom_fields`` raises rather than silently storing whatever
the client sent. That is the same fail-closed default
``documents_router.register_entity_access`` uses, and for the same reason: a
misassembled application must not be one that quietly skips a validation step.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.common import CrmEntityType


class CustomFieldResolver(Protocol):
    """Validates and merges a record's submitted custom values.

    Implemented by
    :meth:`app.products.crm.custom_fields.service.CustomFieldValueService.resolve`.
    """

    def __call__(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
        submitted: Mapping[str, Any] | None,
        existing: Mapping[str, Any] | None,
        creating: bool,
    ) -> Awaitable[dict[str, Any]]: ...


class CustomFieldDefaults(Protocol):
    """Supplies the document a newly created record starts from."""

    def __call__(
        self,
        session: AsyncSession,
        *,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
    ) -> Awaitable[dict[str, Any]]: ...


class CustomFieldsNotWiredError(RuntimeError):
    """A record write carried custom values but no resolver is registered.

    Always a wiring bug — ``app.api.router`` registers one at import — and
    never something a request can cause. Raised rather than defaulting to
    "store it unvalidated", which would be the one way a custom value could
    reach the database without passing its definition's rules.
    """


_resolver: CustomFieldResolver | None = None
_defaults: CustomFieldDefaults | None = None


def register_custom_field_resolver(
    resolver: CustomFieldResolver, defaults: CustomFieldDefaults
) -> None:
    """Install the implementation. Called once, from the composition root."""
    global _resolver, _defaults
    _resolver = resolver
    _defaults = defaults


async def resolve_custom_fields(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType,
    submitted: Mapping[str, Any] | None,
    existing: Mapping[str, Any] | None = None,
    creating: bool = False,
) -> dict[str, Any]:
    """Validate ``submitted`` against the tenant's definitions and merge it."""
    if _resolver is None:
        raise CustomFieldsNotWiredError(
            "No custom-field resolver is registered; "
            "app.api.router.register_custom_fields() was not called."
        )
    return await _resolver(
        session,
        organization_id=organization_id,
        entity_type=entity_type,
        submitted=submitted,
        existing=existing,
        creating=creating,
    )


async def custom_field_defaults(
    session: AsyncSession, *, organization_id: uuid.UUID, entity_type: CrmEntityType
) -> dict[str, Any]:
    """The configured defaults for a new record of ``entity_type``."""
    if _defaults is None:
        raise CustomFieldsNotWiredError(
            "No custom-field resolver is registered; "
            "app.api.router.register_custom_fields() was not called."
        )
    return await _defaults(session, organization_id=organization_id, entity_type=entity_type)


def _reset_for_tests() -> Callable[[], None]:
    """Restore the registry afterwards. Used by the wiring tests only."""
    previous_resolver, previous_defaults = _resolver, _defaults

    def restore() -> None:
        global _resolver, _defaults
        _resolver, _defaults = previous_resolver, previous_defaults

    return restore


__all__ = [
    "CustomFieldDefaults",
    "CustomFieldResolver",
    "CustomFieldsNotWiredError",
    "custom_field_defaults",
    "register_custom_field_resolver",
    "resolve_custom_fields",
]
