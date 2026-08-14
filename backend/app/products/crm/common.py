"""Shared building blocks for CRM tables.

Every CRM entity is tenant-owned, soft-deleted and authored, so the mixin stack
is identical across all of them. Declaring it once here keeps the individual
``models.py`` files focused on the columns that actually differ, and — more
importantly — makes it impossible to create a CRM table that accidentally omits
``organization_id`` and therefore escapes RLS.
"""

from __future__ import annotations

import enum

from app.core.models import (
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

CRM_SCHEMA = "crm"
PLATFORM_SCHEMA = "platform"


class CrmEntityMixin(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
):
    """The standard column set for a tenant-owned CRM record.

    Supplies ``id``, ``created_at``/``updated_at``, ``created_by_id``/
    ``updated_by_id``, ``deleted_at`` and — critically — ``organization_id``.
    """


class Priority(enum.StrEnum):
    """Shared priority scale (doc 05 ``Priority``)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CrmEntityType(enum.StrEnum):
    """Target of a polymorphic association (activities, tasks, notes).

    The relation is validated in the service layer rather than by a foreign
    key, because one column cannot reference five tables. Every write path
    checks that the referenced record exists *within the caller's
    organization* — see ``resolve_related_entity`` in the activities service.
    """

    ACCOUNT = "ACCOUNT"
    CONTACT = "CONTACT"
    LEAD = "LEAD"
    OPPORTUNITY = "OPPORTUNITY"
    CAMPAIGN = "CAMPAIGN"


__all__ = [
    "CRM_SCHEMA",
    "PLATFORM_SCHEMA",
    "CrmEntityMixin",
    "CrmEntityType",
    "Priority",
]
