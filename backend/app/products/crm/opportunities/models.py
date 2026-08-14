"""SQLAlchemy models for the opportunities module (doc 05).

Four tables: ``pipelines`` and ``pipeline_stages`` define the sales process,
``opportunities`` are the deals moving through it, and
``opportunity_stage_history`` is the immutable record of every stage change —
which is what makes velocity and conversion reporting possible later.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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


class Pipeline(Base, CrmEntityMixin):
    """A named sales process. One organization may run several."""

    __tablename__ = "pipelines"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_pipelines_organization_id_name"),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class PipelineStage(Base, CrmEntityMixin):
    """One step in a pipeline.

    ``is_won``/``is_lost`` mark the terminal stages. Deriving closure from
    flags rather than from the stage's name keeps the business rule intact when
    a tenant renames "Closed Won".
    """

    __tablename__ = "pipeline_stages"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "name", name="uq_pipeline_stages_pipeline_id_name"),
        Index("ix_pipeline_stages_pipeline_id_sort_order", "pipeline_id", "sort_order"),
        CheckConstraint(
            "default_probability IS NULL OR "
            "(default_probability >= 0 AND default_probability <= 100)",
            name="default_probability_range",
        ),
        CheckConstraint("NOT (is_won AND is_lost)", name="not_both_won_and_lost"),
        {"schema": CRM_SCHEMA},
    )

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.pipelines.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    default_probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_won: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_lost: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    @property
    def is_closed(self) -> bool:
        return self.is_won or self.is_lost


class Opportunity(Base, CrmEntityMixin):
    """A deal in progress against an account."""

    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opportunities_organization_id_stage_id", "organization_id", "stage_id"),
        Index("ix_opportunities_organization_id_account_id", "organization_id", "account_id"),
        Index("ix_opportunities_organization_id_owner_id", "organization_id", "owner_id"),
        Index(
            "ix_opportunities_organization_id_expected_close_date",
            "organization_id",
            "expected_close_date",
        ),
        Index("ix_opportunities_organization_id_deleted_at", "organization_id", "deleted_at"),
        CheckConstraint(
            "win_probability IS NULL OR (win_probability >= 0 AND win_probability <= 100)",
            name="win_probability_range",
        ),
        CheckConstraint("deal_value IS NULL OR deal_value >= 0", name="deal_value_non_negative"),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    primary_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    stage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.pipeline_stages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    deal_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )
    win_probability: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_close_date: Mapped[dt.date | None] = mapped_column(nullable=True)
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forecast_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    competitor: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lead_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.lead_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    products: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Closure -----------------------------------------------------------
    won_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    loss_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    win_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    @property
    def is_closed(self) -> bool:
        return self.won_at is not None or self.lost_at is not None


class OpportunityStageHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """Append-only audit of stage movement.

    No soft delete and no ``updated_by``: history is written once and never
    edited. It is still tenant-scoped so RLS applies.
    """

    __tablename__ = "opportunity_stage_history"
    __table_args__ = (
        Index(
            "ix_opportunity_stage_history_opportunity_id_changed_at",
            "opportunity_id",
            "changed_at",
        ),
        {"schema": CRM_SCHEMA},
    )

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    to_stage_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    changed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)


__all__ = [
    "Opportunity",
    "OpportunityStageHistory",
    "Pipeline",
    "PipelineStage",
]
