"""SQLAlchemy models for the campaigns module (doc 05 "Campaign")."""

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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin


class CampaignType(enum.StrEnum):
    EMAIL = "EMAIL"
    WEBINAR = "WEBINAR"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    EVENT = "EVENT"
    ADVERTISEMENT = "ADVERTISEMENT"


class CampaignStatus(enum.StrEnum):
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class CampaignMemberType(enum.StrEnum):
    LEAD = "LEAD"
    CONTACT = "CONTACT"


class Campaign(Base, CrmEntityMixin):
    """A marketing campaign that generates leads."""

    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_organization_id_status", "organization_id", "status"),
        Index("ix_campaigns_organization_id_deleted_at", "organization_id", "deleted_at"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="end_date_after_start_date",
        ),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[CampaignType] = mapped_column(
        Enum(CampaignType, name="campaign_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=CampaignStatus.PLANNING,
        server_default=CampaignStatus.PLANNING.value,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    start_date: Mapped[dt.date | None] = mapped_column(nullable=True)
    end_date: Mapped[dt.date | None] = mapped_column(nullable=True)
    budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    expected_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lead_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.lead_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    products: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Cached metrics ----------------------------------------------------
    # Maintained by background aggregation, never by request handlers.
    leads_generated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    opportunities_generated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    conversion_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    roi: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)


class CampaignMember(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """A lead or contact enrolled in a campaign.

    Tenant-scoped in its own right so RLS covers it directly rather than
    relying on a join to the parent campaign.
    """

    __tablename__ = "campaign_members"
    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "entity_type",
            "entity_id",
            name="uq_campaign_members_campaign_id_entity_type_entity_id",
        ),
        Index("ix_campaign_members_organization_id_campaign_id", "organization_id", "campaign_id"),
        {"schema": CRM_SCHEMA},
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[CampaignMemberType] = mapped_column(
        Enum(
            CampaignMemberType,
            name="campaign_member_type",
            schema=CRM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    added_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "Campaign",
    "CampaignMember",
    "CampaignMemberType",
    "CampaignStatus",
    "CampaignType",
]
