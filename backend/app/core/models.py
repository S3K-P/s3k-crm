"""Shared declarative mixins for every Platform and CRM table.

Composed rather than inherited from one god-base, so a table takes exactly the
columns it needs:

    class Account(Base, UUIDPrimaryKeyMixin, TimestampMixin,
                  AuthorshipMixin, SoftDeleteMixin, TenantMixin):
        __tablename__ = "accounts"
        __table_args__ = {"schema": "crm"}

``TenantMixin`` is the one that matters for isolation: it supplies the
``organization_id`` column that every RLS policy filters on (ADR-007). A table
holding tenant data without it is a data leak waiting to happen — see
``enable_rls`` in :mod:`app.core.rls`.

Column naming is snake_case at the database level. The Prisma schema documents
in ``docs/architecture`` use camelCase as a logical model; this is the physical
mapping of it, not a second source of truth.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, MetaData, Uuid, func, text
from sqlalchemy.orm import Mapped, declarative_mixin, mapped_column

from app.core.ids import uuid7

# Deterministic constraint names keep Alembic autogenerate diffs stable and
# make migrations reversible without hand-written DROP CONSTRAINT names.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: Shared metadata for every Platform and CRM table — one database, one
#: migration history (ADR-001, ADR-007). ``Base`` in :mod:`app.core.database`
#: adopts this so the naming convention applies everywhere.
METADATA = MetaData(naming_convention=NAMING_CONVENTION)

#: The PostgreSQL setting the tenant context writes and RLS policies read.
TENANT_SETTING = "app.current_org_id"


@declarative_mixin
class UUIDPrimaryKeyMixin:
    """Time-ordered UUID v7 primary key (decision D02).

    The server default uses PostgreSQL 18's native ``uuidv7()`` so rows created
    by migrations or raw SQL are consistent with ORM inserts, while the Python
    default lets application code know the id before flushing.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid7,
        server_default=text("uuidv7()"),
    )


@declarative_mixin
class TimestampMixin:
    """Creation and last-modification timestamps, maintained by the database."""

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


@declarative_mixin
class AuthorshipMixin:
    """Who created and last modified the row.

    Deliberately **not** a foreign key to the users table: audit history must
    survive user deletion, and Platform must not force a hard dependency on
    identity into every product table.
    """

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


@declarative_mixin
class SoftDeleteMixin:
    """Soft deletion via a nullable timestamp.

    ``deleted_at IS NULL`` means live. Repositories are responsible for
    filtering; this mixin only supplies the column and its partial index.
    """

    deleted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@declarative_mixin
class TenantMixin:
    """Tenant discriminator — the column every RLS policy filters on (ADR-007).

    Any table carrying customer data must include this mixin **and** have RLS
    enabled in its migration. The index is not optional: every tenant-scoped
    query filters on this column.
    """

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
