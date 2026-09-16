"""SQLAlchemy models for workflow automation (Checkpoint 6).

Two tables, the same split :mod:`app.platform.events.models` uses and for the
same reason: **configuration** (a rule — what to watch for, what to check,
what to do) and **history** (a run — what actually happened one time this
rule fired) are different lifecycles. A rule is edited by an administrator and
soft-deleted like every other CRM configuration object. A run is an
append-only fact, written once by the engine and never edited — the same
shape as ``platform.outbox_events``, and for the same reason: an execution
record that could be changed after the fact would not be a record.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TimestampMixin, UUIDPrimaryKeyMixin
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin

#: Upper bound on conditions/actions one rule may hold. Every one is evaluated
#: or run inline, synchronously, inside the outbox handler for one event — a
#: rule with more than this is not a process an administrator can follow
#: either, and it is the same order of magnitude blueprints cap a transition's
#: ``required_fields`` at.
MAX_CONDITIONS = 40
MAX_ACTIONS = 20


class WorkflowEntityType(enum.StrEnum):
    """What a workflow rule watches.

    A superset of :class:`~app.products.crm.common.CrmEntityType`: the five
    members shared with it are exactly the entities that already carry
    tenant-defined fields and already fire the generic create/update hook
    (`shared.service.TenantScopedService`); ``TASK`` is additional because a
    due date arriving is a real automation trigger (`WorkflowTriggerType.TASK_DUE`)
    on a record that has no custom fields and is not part of ``CrmEntityType``.
    Values are kept identical to ``CrmEntityType``'s where they overlap so a
    record's own ``crm_entity_type`` can be used here with no translation.
    """

    ACCOUNT = "ACCOUNT"
    CONTACT = "CONTACT"
    LEAD = "LEAD"
    OPPORTUNITY = "OPPORTUNITY"
    CAMPAIGN = "CAMPAIGN"
    TASK = "TASK"


class WorkflowTriggerType(enum.StrEnum):
    """What has to happen before a rule's conditions are even considered."""

    #: A new record of ``entity_type`` was created.
    RECORD_CREATED = "RECORD_CREATED"
    #: Any field on an existing record changed.
    RECORD_UPDATED = "RECORD_UPDATED"
    #: One named field changed — ``trigger_config``: ``{"field": str,
    #: "to": Any | None, "from": Any | None}``. ``to``/``from`` narrow to a
    #: specific value; omitted, either side matches anything.
    FIELD_CHANGED = "FIELD_CHANGED"
    #: An opportunity moved pipeline stage — ``trigger_config``:
    #: ``{"to_stage_name": str | None, "from_stage_name": str | None}``.
    #: ``entity_type`` must be ``OPPORTUNITY``.
    STAGE_CHANGED = "STAGE_CHANGED"
    #: A lead's status changed — ``trigger_config``: ``{"to": str | None,
    #: "from": str | None}`` (``LeadStatus`` values). ``entity_type`` must be
    #: ``LEAD``.
    STATUS_CHANGED = "STATUS_CHANGED"
    #: ``owner_id`` changed, on any entity that carries one.
    OWNER_CHANGED = "OWNER_CHANGED"
    #: A date field on the record has arrived — ``trigger_config``:
    #: ``{"date_field": str, "offset_minutes": int}``. Fires once ``date_field
    #: + offset_minutes <= now``; a negative offset fires *before* the date
    #: ("3 days before close date" = ``-4320``), zero fires as soon as it
    #: passes. Evaluated by a periodic scan (`.service.scan_scheduled_workflows`),
    #: never by the record-event hook. ``date_field`` is validated against a
    #: fixed allow-list per ``entity_type`` (`.conditions.SCHEDULED_DATE_FIELDS`).
    SCHEDULED = "SCHEDULED"
    #: A task's ``due_date`` has arrived. ``entity_type`` must be ``TASK``;
    #: ``trigger_config``: ``{"offset_minutes": int}``, same semantics as
    #: ``SCHEDULED``. Evaluated by the same periodic scan.
    TASK_DUE = "TASK_DUE"


class WorkflowActionType(enum.StrEnum):
    """What a matched rule does. See :mod:`.actions` for execution."""

    UPDATE_FIELD = "UPDATE_FIELD"
    ASSIGN_OWNER = "ASSIGN_OWNER"
    CREATE_TASK = "CREATE_TASK"
    CREATE_ACTIVITY = "CREATE_ACTIVITY"
    CREATE_NOTE = "CREATE_NOTE"
    SEND_EMAIL = "SEND_EMAIL"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"
    #: Opportunity only. Goes through ``OpportunityService.change_stage`` —
    #: the same blueprint-guarded transition a person's drag-and-drop uses.
    CHANGE_STAGE = "CHANGE_STAGE"
    #: Lead only. Goes through ``LeadService.change_status``, likewise
    #: blueprint-guarded.
    CHANGE_STATUS = "CHANGE_STATUS"


class WorkflowRunStatus(enum.StrEnum):
    """The outcome of one rule firing once."""

    SUCCEEDED = "SUCCEEDED"
    #: At least one action failed; at least one other succeeded (or none were
    #: configured to fail together, order-independent — see ``.service``).
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class WorkflowRule(Base, CrmEntityMixin):
    """One tenant-configured ``WHEN -> IF -> THEN`` automation."""

    __tablename__ = "workflow_rules"
    __table_args__ = (
        Index(
            "uq_workflow_rules_organization_id_name_live",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # The engine's own lookup: active rules for one entity type. Trigger
        # narrowing beyond that (which trigger_type, which field) is cheap
        # enough in Python over a small per-tenant set that it is not indexed
        # separately — see the module docstring on ``.service``.
        Index(
            "ix_workflow_rules_organization_id_entity_type_active",
            "organization_id",
            "entity_type",
            "is_active",
        ),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    entity_type: Mapped[WorkflowEntityType] = mapped_column(
        Enum(WorkflowEntityType, name="workflow_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    trigger_type: Mapped[WorkflowTriggerType] = mapped_column(
        Enum(
            WorkflowTriggerType, name="workflow_trigger_type", schema=CRM_SCHEMA, native_enum=True
        ),
        nullable=False,
    )
    #: Shape depends on ``trigger_type`` — see the member docstrings above.
    trigger_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    #: ``"AND"`` or ``"OR"`` over ``conditions``. One level, no nested groups —
    #: the same shape ``app.products.crm.layouts.evaluate`` already gives a
    #: layout rule, and for the same reason: one operator over a flat list
    #: covers the overwhelming majority of real rules and is what the
    #: evaluator (`.conditions.matches_conditions`, a thin wrapper over
    #: ``evaluate_rule``) already understands with no adapter.
    condition_logic: Mapped[str] = mapped_column(String(3), nullable=False, default="AND")
    #: ``[{"field_key": str, "operator": str, "value": Any}, ...]`` — the same
    #: condition shape ``layouts.evaluate.evaluate_condition`` takes.
    conditions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    #: Ordered list of ``{"type": WorkflowActionType, ...}``. Run in order,
    #: each independently (`.service._run_rule`): one action failing does not
    #: stop the rest from being attempted.
    actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )

    #: Created inactive, like a blueprint — see ``BlueprintCreate``'s docstring
    #: for the identical reasoning: activation is the moment a rule starts
    #: acting on real records, and doing that in the same request that
    #: creates an empty one would activate a rule describing nothing.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    #: Execution order when more than one active rule matches the same event.
    #: Not a priority in the sense of "only the first one runs" — every
    #: matched rule runs — just the order they run in, so an administrator
    #: who wants rule B's field update to be the value rule A's email quotes
    #: can arrange it.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One rule firing once. Append-only — see the module docstring."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        # Idempotency (Step 10): the *same* outbox event redelivering must not
        # run the same rule's actions twice. A duplicate insert here raises
        # ``IntegrityError``, which ``.service._run_rule`` catches and treats
        # as "already handled" rather than an error.
        Index(
            "uq_workflow_runs_rule_source_event",
            "workflow_rule_id",
            "source_event_id",
            unique=True,
            postgresql_where=text("source_event_id IS NOT NULL"),
        ),
        # Same guarantee for a scheduled trigger, which has no outbox event to
        # key on — ``dedupe_key`` is minted by the scanner as
        # ``f"{rule_id}:{record_id}:{date}"`` so an hourly tick that finds the
        # same overdue record again does not fire it again the same day.
        Index(
            "uq_workflow_runs_rule_dedupe_key",
            "workflow_rule_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        Index("ix_workflow_runs_organization_id_created_at", "organization_id", "created_at"),
        Index(
            "ix_workflow_runs_organization_id_rule_id_created_at",
            "organization_id",
            "workflow_rule_id",
            "created_at",
        ),
        Index(
            "ix_workflow_runs_organization_id_entity_type_record_id",
            "organization_id",
            "entity_type",
            "record_id",
        ),
        Index("ix_workflow_runs_correlation_id", "correlation_id"),
        {"schema": CRM_SCHEMA},
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workflow_rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.workflow_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[WorkflowEntityType] = mapped_column(
        Enum(WorkflowEntityType, name="workflow_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: ``"created"`` / ``"updated"`` / ``"status_changed"`` / ``"stage_changed"``
    #: / ``"scheduled"`` — the reason this run happened, for the history view.
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)

    #: The outbox event that caused this run, or ``None`` for a scheduled one.
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    #: Set only for a scheduled/date trigger — see the index docstring above.
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)

    #: Ties every run in one causal chain together (Step 13) — shared by every
    #: event a workflow action's own write enqueues.
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    #: Hops from the original, human-initiated write. 0 means this run was
    #: triggered directly by a request, not by another workflow's action.
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[WorkflowRunStatus] = mapped_column(
        Enum(WorkflowRunStatus, name="workflow_run_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    actions_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actions_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: ``[{"type": str, "status": "SUCCEEDED" | "FAILED", "detail": str | None}, ...]``
    #: — one entry per configured action, in the order it ran.
    action_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    #: Set only when the rule itself could not run at all (its record vanished
    #: mid-flight, its condition context could not be built) — distinct from
    #: an individual action's failure, which lives in ``action_results``.
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = [
    "MAX_ACTIONS",
    "MAX_CONDITIONS",
    "WorkflowActionType",
    "WorkflowEntityType",
    "WorkflowRule",
    "WorkflowRun",
    "WorkflowRunStatus",
    "WorkflowTriggerType",
]
