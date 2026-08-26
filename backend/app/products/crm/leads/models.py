"""SQLAlchemy models for the leads module (doc 05 "Lead", "LeadSource").

``LeadSource`` lives here rather than in its own module because it exists only
to classify leads and is owned by the same bounded context.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, EMAIL_TERMS, CrmEntityMixin, Priority, searchable


class LeadStatus(enum.StrEnum):
    """Lead lifecycle (doc 05).

    Legal transitions are enforced by ``LEAD_TRANSITIONS`` in the service
    layer, not by the database, so the rule is testable and reportable.
    """

    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    PROPOSAL_SENT = "PROPOSAL_SENT"
    NEGOTIATION = "NEGOTIATION"
    UNQUALIFIED = "UNQUALIFIED"
    CONVERTED = "CONVERTED"
    LOST = "LOST"


class LeadSourceStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class LeadSource(Base, CrmEntityMixin):
    """Where leads come from, e.g. "Website", "Referral"."""

    __tablename__ = "lead_sources"
    __table_args__ = (
        # Partial, so uniqueness applies to *live* rows only. An unconditional
        # constraint counted archived sources too, which meant archiving a name
        # burned it forever — and because the service's own duplicate check
        # already excluded archived rows, the INSERT sailed past it and failed
        # in the database as a 500 instead of a 409.
        Index(
            "uq_lead_sources_organization_id_name_live",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_lead_sources_organization_id_status", "organization_id", "status"),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeadSourceStatus] = mapped_column(
        Enum(LeadSourceStatus, name="lead_source_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=LeadSourceStatus.ACTIVE,
        server_default=LeadSourceStatus.ACTIVE.value,
    )


class Lead(Base, CrmEntityMixin):
    """A prospective customer, before conversion into an account + contact."""

    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_organization_id_status", "organization_id", "status"),
        Index("ix_leads_organization_id_owner_id", "organization_id", "owner_id"),
        Index("ix_leads_organization_id_email", "organization_id", "email"),
        Index("ix_leads_organization_id_created_at", "organization_id", "created_at"),
        Index("ix_leads_organization_id_deleted_at", "organization_id", "deleted_at"),
        CheckConstraint(
            "ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 100)",
            name="ai_score_range",
        ),
        {"schema": CRM_SCHEMA},
    )

    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Free-text company name; becomes an ``Account`` on conversion.
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lead_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.lead_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="lead_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=LeadStatus.NEW,
        server_default=LeadStatus.NEW.value,
    )
    #: Persisted only; nothing computes it yet (resolves A01).
    ai_score: Mapped[int | None] = mapped_column(nullable=True)
    priority: Mapped[Priority | None] = mapped_column(
        Enum(Priority, name="crm_priority", schema=CRM_SCHEMA, native_enum=True),
        nullable=True,
    )
    expected_deal_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Product or service the prospect asked about — carried into the deal.
    product_interest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Conversion outcome ------------------------------------------------
    converted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    converted_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    converted_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    converted_opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.opportunities.id", ondelete="SET NULL"),
        nullable=True,
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.campaigns.id", ondelete="SET NULL"),
        nullable=True,
    )
    lost_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Search ------------------------------------------------------------
    #: ``company`` sits at ``B`` alongside email rather than at ``A`` with the
    #: person's name: a lead is a person, and searching "Acme" should surface
    #: the *account* called Acme above the four leads who work there.
    search_vector: Mapped[str | None] = searchable(
        "setweight(to_tsvector('english'::regconfig, coalesce(first_name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(last_name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(company, '')), 'B') || "
        f"setweight(to_tsvector('english'::regconfig, {EMAIL_TERMS}), 'B') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(industry, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(product_interest, '')), 'C')"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_converted(self) -> bool:
        return self.status is LeadStatus.CONVERTED


__all__ = ["Lead", "LeadSource", "LeadSourceStatus", "LeadStatus"]
