"""SQLAlchemy models for the accounts module (doc 05 "Account").

``Account`` is the canonical company record (ADR-008: there is no separate
``Customer`` table). Contacts, opportunities and activities all hang off it.
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Enum,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, searchable


class AccountStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    ONBOARDING = "ONBOARDING"
    AT_RISK = "AT_RISK"
    CHURNED = "CHURNED"


class Account(Base, CrmEntityMixin):
    """A company the organization does business with."""

    __tablename__ = "accounts"
    __table_args__ = (
        # Composite indexes are ordered organization-first because every query
        # filters on the tenant before anything else.
        Index("ix_accounts_organization_id_status", "organization_id", "status"),
        Index("ix_accounts_organization_id_owner_id", "organization_id", "owner_id"),
        Index("ix_accounts_organization_id_deleted_at", "organization_id", "deleted_at"),
        Index("ix_accounts_organization_id_name", "organization_id", "name"),
        CheckConstraint(
            "health_score IS NULL OR (health_score >= 0 AND health_score <= 100)",
            name="health_score_range",
        ),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    annual_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=AccountStatus.ACTIVE,
        server_default=AccountStatus.ACTIVE.value,
    )
    #: Platform user id. Not a foreign key: ownership must survive the owner
    #: leaving the platform, and CRM tables do not depend on platform tables.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    health_score: Mapped[int | None] = mapped_column(nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Address -----------------------------------------------------------
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # --- Integration -------------------------------------------------------
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    integration_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    # --- Search ------------------------------------------------------------
    #: Name first: it is what somebody types when they know which company they
    #: want. ``description`` is included at ``D`` so a distinctive phrase in it
    #: still finds the account, without ever outranking a name match.
    search_vector: Mapped[str | None] = searchable(
        "setweight(to_tsvector('english'::regconfig, coalesce(name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(industry, '')), 'B') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(website, '')), 'B') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(city, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(country, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'D')"
    )


__all__ = ["Account", "AccountStatus"]
