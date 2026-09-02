"""Automation configuration: assignment rules, and the settings that gate scoring.

Two tables, both small and both **data rather than code**, which is the whole
approach the analysis argues for (§5.6): declarative configuration a sales
manager owns, not a workflow designer nobody can reason about.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin


class AssignmentRule(Base, CrmEntityMixin):
    """Who owns a new record, decided by criteria and round-robin.

    Zoho runs assignment on import, web forms and the API but not on manual
    creation; this runs everywhere (see ``assignment.py``). The criteria set is
    deliberately three fields rather than an expression language — those are
    what territory assignment actually keys on, and anything richer becomes a
    rule engine.
    """

    __tablename__ = "assignment_rules"
    __table_args__ = (
        Index(
            "ix_assignment_rules_organization_id_module_active",
            "organization_id",
            "module",
            "sort_order",
            postgresql_where=text("is_active AND deleted_at IS NULL"),
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        CheckConstraint("last_assigned_index >= 0", name="last_assigned_index_non_negative"),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Registry/permission module the rule applies to, e.g. ``leads``.
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    #: Rules are tried in this order; the first match wins.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # --- Criteria (NULL means "any") ---------------------------------------
    match_country: Mapped[str | None] = mapped_column(String(120), nullable=True)
    match_industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    match_lead_source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.lead_sources.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Outcome ------------------------------------------------------------
    #: Candidate owners, cycled round-robin. Plain user ids, not foreign keys:
    #: ``owner_id`` is deliberately not a FK anywhere in CRM (constraint C2),
    #: because ownership has to survive the owner leaving the platform.
    owner_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    #: Where the round-robin got to. Advanced inside the assigning transaction,
    #: so two concurrent creates take different owners rather than both the
    #: first.
    last_assigned_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=-1, server_default="-1"
    )


class AutomationSettings(Base, CrmEntityMixin):
    """Per-organization switches for the automation that runs unattended.

    Scoring and health are **off by default**. A wrong score erodes trust
    faster than a missing one, and a tenant that has not looked at the model
    should not find their accounts silently relabelled AT_RISK overnight
    (analysis §6.5). Turning them on is a deliberate act.

    One row per organization, created on demand.
    """

    __tablename__ = "automation_settings"
    __table_args__ = (
        Index(
            "uq_automation_settings_organization_id_live",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "stale_opportunity_days > 0 AND stale_lead_days > 0",
            name="stale_windows_positive",
        ),
        {"schema": CRM_SCHEMA},
    )

    lead_scoring_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    contact_scoring_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    account_health_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Whether a health score may move an account between ACTIVE and AT_RISK.
    #: Separate from computing the score at all, because seeing the number and
    #: letting it relabel your customer list are different levels of trust.
    account_status_automation_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Nudges are on by default: a reminder about your own stale deal is
    #: helpful and reversible, unlike a score that changes what a record says.
    stale_reminders_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    stale_opportunity_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=14, server_default="14"
    )
    stale_lead_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7, server_default="7"
    )


__all__ = ["AssignmentRule", "AutomationSettings"]
