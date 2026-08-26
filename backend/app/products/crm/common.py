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

#: CRM tables that legitimately carry no ``organization_id``, and why.
#:
#: The RLS schema audit discovers tenant-scoped tables from the database rather
#: than from a list (see :mod:`app.core.schema_audit`), so anything *without*
#: the tenant column is a finding unless it is named here. That inversion is
#: the point: a new CRM table is unclassified — and therefore a failure — until
#: someone either gives it ``organization_id`` or writes down why it needs none.
#: Adding an entry is a deliberate, reviewable act.
#:
#: Keep this list short. An exemption is a hole in tenant isolation that
#: something *else* has to close, and the reason has to say what that is.
RLS_EXEMPT_TABLES: dict[str, str] = {
    "meetings": (
        "strict 1:1 extension of crm.activities through a NOT NULL, UNIQUE "
        "activity_id FK with ON DELETE CASCADE. It holds scheduling detail and "
        "no tenant discriminator of its own; every read path resolves the parent "
        "activity first, and that lookup is policy-filtered. Adding "
        "organization_id here would create a second copy of the tenant that "
        "could drift from the parent's."
    ),
}


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
    "RLS_EXEMPT_TABLES",
    "CrmEntityMixin",
    "CrmEntityType",
    "Priority",
]
