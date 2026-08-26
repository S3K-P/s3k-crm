"""Shared building blocks for CRM tables.

Every CRM entity is tenant-owned, soft-deleted and authored, so the mixin stack
is identical across all of them. Declaring it once here keeps the individual
``models.py`` files focused on the columns that actually differ, and — more
importantly — makes it impossible to create a CRM table that accidentally omits
``organization_id`` and therefore escapes RLS.
"""

from __future__ import annotations

import enum

from sqlalchemy import Computed
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

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


#: The searchable text of an ``email`` column: the whole address, plus its
#: local part and first domain label as separate words.
#:
#: PostgreSQL's text-search parser treats an address as a **single** token, so
#: a vector built from ``email`` alone matches "ravi@zephyr.example" and not
#: "zephyr" — which makes "find everyone at Zephyr", the thing people actually
#: search email for, impossible. Splitting adds the two words worth having.
#:
#: The first domain *label* rather than the whole domain, deliberately: it
#: yields "zephyr" instead of "zephyr.example", and stops short of indexing
#: the TLD, which would make "com" a lexeme matching most of the database.
#: ``split_part`` is IMMUTABLE, so this is legal inside a generated column.
EMAIL_TERMS = (
    "coalesce(email, '') || ' ' || "
    "split_part(coalesce(email, ''), '@', 1) || ' ' || "
    "split_part(split_part(coalesce(email, ''), '@', 2), '.', 1)"
)


def searchable(expression: str) -> Mapped[str | None]:
    """A read-only ``search_vector`` maintained by PostgreSQL (`P3-W20-BE-01`).

    ``Computed(..., persisted=True)`` is what tells SQLAlchemy the column is
    generated, so it is left out of every INSERT and UPDATE the ORM builds.
    Without it, the first write to a searchable table would fail with
    "cannot insert into generated column" — the ORM would try to persist a
    value the database reserves for itself.

    ``expression`` must be IMMUTABLE, which in practice means every
    ``to_tsvector`` call inside it passes ``'english'::regconfig`` explicitly.
    It is stated here *and* in revision ``20260826_0100``: the migration is a
    snapshot of what was built, this is the live definition, and the two are
    allowed to diverge only through a migration that changes both. Changing
    this string alone changes nothing in the database — the column is already
    built — which is exactly why the migration owns its own copy.

    ``deferred`` matters more than it looks. Every list endpoint selects the
    whole entity, and a tsvector over a description field is far larger than
    the row it summarises; without this, adding search would have quietly put
    a few kilobytes of lexemes on the wire for every row of every list page,
    to be discarded unread. Search itself never loads the value into Python —
    it uses the column in ``WHERE`` and ``ORDER BY``, where deferral has no
    effect at all.
    """
    return mapped_column(
        TSVECTOR,
        Computed(expression, persisted=True),
        nullable=True,
        deferred=True,
    )


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
    "searchable",
]
