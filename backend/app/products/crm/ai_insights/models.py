"""SQLAlchemy models for ai_insights (Checkpoint 7).

One table, ``crm.ai_generations``: the stored result of one AI feature call —
a summary, an intelligence report, a next-best-action, an email draft, a
meeting extraction, a natural-language query translation, or a rule-based
priority's AI-narrated explanation.

**Append-only**, like ``market_insight_sessions``: "Refresh" writes a new row
rather than overwriting the last one, so a record's AI history is real
history (§16 of the checkpoint brief), not a single mutable cell that loses
what the AI said yesterday. The *latest* row per
``(entity_type, entity_id, feature)`` is what a record's AI panel shows; the
repository's ``latest_for`` is the one place that query is written.

**Not owner-scoped.** Unlike ``market_insight_sessions`` — one person's
working notes on an external company — a generation concerns a shared CRM
record (an account, a deal, a lead) and is authorized through that record's
own module permission and record-level visibility, resolved by the caller
before this row is ever reached (``AccountService.get_or_404(..., visibility=...)``
and friends). Anyone who can see the account can see its AI summary, exactly
as anyone who can see the account can see its Notes tab.

**Feedback is columns on the same row, not a second table.** One person's
thumbs up/down on one generation is the whole of §14's feedback requirement;
a many-to-one table would exist to answer a question ("who rated what more
than once") the product has no UI for asking.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import Boolean, DateTime, Enum, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin


class AiFeature(enum.StrEnum):
    """Which Checkpoint 7 feature produced this row."""

    ACCOUNT_SUMMARY = "ACCOUNT_SUMMARY"
    ACCOUNT_INTELLIGENCE = "ACCOUNT_INTELLIGENCE"
    OPPORTUNITY_SUMMARY = "OPPORTUNITY_SUMMARY"
    LEAD_SUMMARY = "LEAD_SUMMARY"
    NEXT_BEST_ACTION = "NEXT_BEST_ACTION"
    EMAIL_DRAFT = "EMAIL_DRAFT"
    MEETING_EXTRACTION = "MEETING_EXTRACTION"
    NL_QUERY = "NL_QUERY"
    PRIORITIZATION_EXPLANATION = "PRIORITIZATION_EXPLANATION"
    #: A Next Best Action Copilot draft (email, message, agenda, call script,
    #: proposal) prepared for a rep to review before anything is executed.
    NBA_COPILOT = "NBA_COPILOT"


class AiGenerationStatus(enum.StrEnum):
    """Outcome of one feature call. No in-flight state — same reasoning as
    ``market_insights.ResearchStatus``: a row is written only once a turn
    has finished, so it is either usable or it failed.
    """

    READY = "READY"
    FAILED = "FAILED"


class AiFeedbackRating(enum.StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class AiGeneration(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One AI feature call's stored result."""

    __tablename__ = "ai_generations"
    __table_args__ = (
        Index(
            "ix_ai_generations_org_entity_feature_created",
            "organization_id",
            "entity_type",
            "entity_id",
            "feature",
            "created_at",
        ),
        Index(
            "ix_ai_generations_org_feature_created",
            "organization_id",
            "feature",
            "created_at",
        ),
        {"schema": CRM_SCHEMA},
    )

    feature: Mapped[AiFeature] = mapped_column(
        Enum(AiFeature, name="ai_feature", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    #: A ``CrmEntityType`` value (``ACCOUNT``, ``OPPORTUNITY``, ``LEAD``, ...)
    #: as plain text rather than a hard FK to that enum type: some features
    #: (``NL_QUERY``, a portfolio-wide ``EMAIL_DRAFT`` with no linked record)
    #: legitimately have no entity at all, and this table must not gain a
    #: dependency on which five entity kinds another module currently lists.
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[AiGenerationStatus] = mapped_column(
        Enum(AiGenerationStatus, name="ai_generation_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=AiGenerationStatus.READY,
        server_default=AiGenerationStatus.READY.value,
    )
    #: The model that produced this row, recorded the same way
    #: ``market_insight_sessions.model`` is — part of how the result should be
    #: read later, never used to authorize anything.
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Set only when ``status`` is ``FAILED`` — a stable code, never a raw
    #: provider message (see ``AiConnectionState``/``ConnectionCheck``).
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The validated structured output (see ``structured.py``), shaped
    #: differently per ``feature`` — the Pydantic model for that feature is
    #: the schema, not this column. Never raw, unvalidated model text.
    content: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: Whether permission-filtered CRM context was available and used, so the
    #: UI can label a generation honestly (§3 of the context-pipeline rules)
    #: instead of assuming context was sent whenever an entity is linked.
    used_crm_context: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    # --- Feedback (§14) ------------------------------------------------
    feedback_rating: Mapped[AiFeedbackRating | None] = mapped_column(
        Enum(AiFeedbackRating, name="ai_feedback_rating", schema=CRM_SCHEMA, native_enum=True),
        nullable=True,
    )
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    feedback_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NbaRule(Base, CrmEntityMixin):
    """A tenant's Next Best Action rule: its own rule, or a tuned built-in.

    Two kinds of row share the table. With ``builtin_key`` set, the row
    overrides a built-in (``nba_rules.BUILTIN_RULES``) — its active flag,
    priority, cooldown and, when ``conditions`` is non-empty, its thresholds —
    while the built-in keeps its action. With ``builtin_key`` null it is a rule
    the tenant wrote, evaluated by the same engine. Configuration, so it is
    soft-deleted and audited like every other CRM configuration object.
    """

    __tablename__ = "nba_rules"
    __table_args__ = (
        Index(
            "uq_nba_rules_organization_id_builtin_key_live",
            "organization_id",
            "builtin_key",
            unique=True,
            postgresql_where=text("builtin_key IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index(
            "uq_nba_rules_organization_id_name_live",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("builtin_key IS NULL AND deleted_at IS NULL"),
        ),
        {"schema": CRM_SCHEMA},
    )

    builtin_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    #: ``OPPORTUNITY`` | ``LEAD`` | ``BOTH``.
    applies_to: Mapped[str] = mapped_column(String(16), nullable=False, default="BOTH")
    condition_logic: Mapped[str] = mapped_column(String(3), nullable=False, default="AND")
    #: ``[{"field_key", "operator", "value"}]`` over signal keys — the shape
    #: ``layouts.evaluate.evaluate_condition`` takes.
    conditions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="MEDIUM")
    #: ``str.format`` template over signal keys.
    reason: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    timing: Mapped[str | None] = mapped_column(String(80), nullable=True)
    due_in_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cooldown_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class NbaActionOutcome(enum.StrEnum):
    EXECUTED = "EXECUTED"
    DISMISSED = "DISMISSED"


class NbaActionLog(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """A rep executed or dismissed a recommended action on a record.

    Append-only, like ``ai_generations``. It is what keeps a recommendation
    from coming straight back after the rep acted on it: the engine suppresses
    an action logged for the same record within the rule's cooldown.
    """

    __tablename__ = "nba_action_logs"
    __table_args__ = (
        Index(
            "ix_nba_action_logs_org_entity_action_created",
            "organization_id",
            "entity_type",
            "entity_id",
            "action_code",
            "created_at",
        ),
        {"schema": CRM_SCHEMA},
    )

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action_code: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[NbaActionOutcome] = mapped_column(
        Enum(NbaActionOutcome, name="nba_action_outcome", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    rule_keys: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    generation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


__all__ = [
    "AiFeature",
    "AiFeedbackRating",
    "AiGeneration",
    "AiGenerationStatus",
    "NbaActionLog",
    "NbaActionOutcome",
    "NbaRule",
]
