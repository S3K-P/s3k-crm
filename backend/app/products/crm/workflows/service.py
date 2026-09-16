"""The workflow rule CRUD service, the outbox handler, and the scheduled scan.

Three responsibilities, kept in one module because they share so much of the
same vocabulary (a rule, its trigger, its conditions, its actions) that
splitting them would mean passing the same handful of types back and forth
between files with no independent reason to change on their own:

* :class:`WorkflowRuleService` — configuration. CRUD plus the validation that
  keeps a saved rule *satisfiable*: a real column for a ``FIELD_CHANGED``
  trigger, a real operator for a condition, an action shape that entity type
  actually supports.
* :func:`handle_record_event` — the outbox handler for
  ``crm.record.event_occurred``. Registered by ``app/api/router.py``
  (the composition root) exactly like every other handler.
* :func:`scan_scheduled_workflows` — the periodic check for ``SCHEDULED``/
  ``TASK_DUE`` rules, called from an ARQ cron job in ``app/worker.py``, the
  same shape ``platform.notifications`` uses for reminders.

Both execution paths funnel into :func:`_run_rule`, which is where
idempotency (Step 10), per-action transaction isolation (Step 15) and the
execution history (Step 12) actually live.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import class_mapper

from app.core.database import provisioning_scope
from app.core.exceptions import AppError, NotFoundError, ValidationFailedError
from app.platform.events.service import OutboxEvent, PermanentEventError
from app.platform.organizations.service import organizations_for_session
from app.products.crm.layouts.evaluate import OPERATORS as CONDITION_OPERATORS
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.tasks.models import Task
from app.products.crm.workflows.actions import (
    ALLOWED_UPDATE_FIELDS,
    entity_service_for,
    execute_action,
)
from app.products.crm.workflows.conditions import (
    SCHEDULED_DATE_FIELDS,
    matches_conditions,
    rule_matches_trigger,
)
from app.products.crm.workflows.context import WorkflowExecutionContext, workflow_execution_scope
from app.products.crm.workflows.models import (
    MAX_ACTIONS,
    MAX_CONDITIONS,
    WorkflowActionType,
    WorkflowEntityType,
    WorkflowRule,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowTriggerType,
)
from app.products.crm.workflows.repository import WorkflowRuleRepository, WorkflowRunRepository

logger = structlog.get_logger(__name__)

MODULE = "workflows"

#: Action types with no meaningful target beyond "the triggering record" —
#: refused when that record is not a ``CrmEntityType`` (a ``TASK``-triggered
#: rule), since the polymorphic link they create (``related_entity_type``)
#: has no member for one.
_REQUIRES_CRM_ENTITY: frozenset[WorkflowActionType] = frozenset(
    {
        WorkflowActionType.CREATE_TASK,
        WorkflowActionType.CREATE_ACTIVITY,
        WorkflowActionType.CREATE_NOTE,
    }
)


class DuplicateWorkflowNameError(ValidationFailedError):
    code = "workflow_name_taken"
    message = "A workflow with that name already exists."


class InvalidWorkflowConfigurationError(ValidationFailedError):
    code = "invalid_workflow_configuration"


# =============================================================================
# Configuration: WorkflowRuleService
# =============================================================================


class WorkflowRuleService(TenantScopedService[WorkflowRule]):
    """CRUD over ``crm.workflow_rules``, with configuration-time validation."""

    entity_name = "Workflow"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, WorkflowRule), WorkflowRule)
        self._session = session

    async def list_workflows(
        self, organization_id: uuid.UUID, *, params: PageParams
    ) -> tuple[Sequence[WorkflowRule], int]:
        return await self.list(organization_id, params=params)

    async def create_workflow(
        self, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> WorkflowRule:
        name = str(values.get("name", "")).strip()
        if not name:
            raise InvalidWorkflowConfigurationError("A workflow needs a name.")
        if await WorkflowRuleRepository(self._session).name_taken(organization_id, name):
            raise DuplicateWorkflowNameError

        entity_type = WorkflowEntityType(values["entity_type"])
        trigger_type = WorkflowTriggerType(values["trigger_type"])
        trigger_config = dict(values.get("trigger_config") or {})
        conditions = list(values.get("conditions") or [])
        actions = list(values.get("actions") or [])
        await self._validate(
            entity_type=entity_type,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            condition_logic=str(values.get("condition_logic", "AND")),
            conditions=conditions,
            actions=actions,
        )

        # Always created inactive — see ``WorkflowRule.is_active``'s docstring.
        payload = {**values, "is_active": False}
        return await self.create(organization_id=organization_id, actor_id=actor_id, values=payload)

    async def update_workflow(
        self, rule: WorkflowRule, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> WorkflowRule:
        if "name" in values:
            name = str(values["name"]).strip()
            if not name:
                raise InvalidWorkflowConfigurationError("A workflow needs a name.")
            if await WorkflowRuleRepository(self._session).name_taken(
                rule.organization_id, name, excluding=rule.id
            ):
                raise DuplicateWorkflowNameError

        entity_type = WorkflowEntityType(values.get("entity_type", rule.entity_type))
        trigger_type = WorkflowTriggerType(values.get("trigger_type", rule.trigger_type))
        trigger_config = dict(values.get("trigger_config", rule.trigger_config))
        conditions = list(values.get("conditions", rule.conditions))
        actions = list(values.get("actions", rule.actions))
        await self._validate(
            entity_type=entity_type,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            condition_logic=str(values.get("condition_logic", rule.condition_logic)),
            conditions=conditions,
            actions=actions,
        )
        return await self.update(rule, actor_id=actor_id, values=values)

    async def duplicate_workflow(
        self, rule: WorkflowRule, *, actor_id: uuid.UUID | None
    ) -> WorkflowRule:
        """A deactivated copy, named uniquely (Step 6: "duplicate")."""
        repository = WorkflowRuleRepository(self._session)
        base_name, candidate, suffix = f"{rule.name} (Copy)", f"{rule.name} (Copy)", 1
        while await repository.name_taken(rule.organization_id, candidate):
            suffix += 1
            candidate = f"{base_name} {suffix}"
        return await self.create(
            organization_id=rule.organization_id,
            actor_id=actor_id,
            values={
                "name": candidate,
                "description": rule.description,
                "entity_type": rule.entity_type,
                "trigger_type": rule.trigger_type,
                "trigger_config": dict(rule.trigger_config),
                "condition_logic": rule.condition_logic,
                "conditions": list(rule.conditions),
                "actions": list(rule.actions),
                "position": rule.position,
                "is_active": False,
            },
        )

    # --- Validation ----------------------------------------------------------

    async def _validate(
        self,
        *,
        entity_type: WorkflowEntityType,
        trigger_type: WorkflowTriggerType,
        trigger_config: dict[str, Any],
        condition_logic: str,
        conditions: list[dict[str, Any]],
        actions: list[dict[str, Any]],
    ) -> None:
        if condition_logic.upper() not in ("AND", "OR"):
            raise InvalidWorkflowConfigurationError("condition_logic must be 'AND' or 'OR'.")
        if len(conditions) > MAX_CONDITIONS:
            raise InvalidWorkflowConfigurationError(
                f"A workflow may hold at most {MAX_CONDITIONS} conditions."
            )
        for condition in conditions:
            operator = condition.get("operator")
            if not condition.get("field_key") or operator not in CONDITION_OPERATORS:
                raise InvalidWorkflowConfigurationError(
                    f"'{operator}' is not a supported condition operator."
                )
        if len(actions) > MAX_ACTIONS:
            raise InvalidWorkflowConfigurationError(
                f"A workflow may hold at most {MAX_ACTIONS} actions."
            )

        self._validate_trigger(
            entity_type=entity_type, trigger_type=trigger_type, trigger_config=trigger_config
        )
        for action in actions:
            self._validate_action(entity_type=entity_type, action=action)

    def _validate_trigger(
        self,
        *,
        entity_type: WorkflowEntityType,
        trigger_type: WorkflowTriggerType,
        trigger_config: dict[str, Any],
    ) -> None:
        if (
            trigger_type is WorkflowTriggerType.STAGE_CHANGED
            and entity_type is not WorkflowEntityType.OPPORTUNITY
        ):
            raise InvalidWorkflowConfigurationError("STAGE_CHANGED only applies to opportunities.")
        if (
            trigger_type is WorkflowTriggerType.STATUS_CHANGED
            and entity_type is not WorkflowEntityType.LEAD
        ):
            raise InvalidWorkflowConfigurationError("STATUS_CHANGED only applies to leads.")
        if (
            trigger_type is WorkflowTriggerType.TASK_DUE
            and entity_type is not WorkflowEntityType.TASK
        ):
            raise InvalidWorkflowConfigurationError("TASK_DUE only applies to tasks.")
        if trigger_type is WorkflowTriggerType.SCHEDULED:
            if entity_type is WorkflowEntityType.TASK:
                raise InvalidWorkflowConfigurationError("Use TASK_DUE for tasks, not SCHEDULED.")
            date_field = trigger_config.get("date_field")
            allowed = SCHEDULED_DATE_FIELDS.get(entity_type, frozenset())
            if date_field not in allowed:
                raise InvalidWorkflowConfigurationError(
                    f"'{date_field}' is not a date field this workflow can watch on "
                    f"{entity_type.value}. Available: {sorted(allowed) or 'none'}."
                )
        if trigger_type is WorkflowTriggerType.FIELD_CHANGED:
            field = trigger_config.get("field")
            if not isinstance(field, str) or field not in self._real_columns(entity_type):
                raise InvalidWorkflowConfigurationError(
                    f"'{field}' is not a field on {entity_type.value}."
                )

    def _validate_action(self, *, entity_type: WorkflowEntityType, action: dict[str, Any]) -> None:
        raw_type = str(action.get("type"))
        try:
            action_type = WorkflowActionType(raw_type)
        except ValueError as exc:
            raise InvalidWorkflowConfigurationError(f"'{raw_type}' is not a known action.") from exc

        if (
            action_type is WorkflowActionType.CHANGE_STAGE
            and entity_type is not WorkflowEntityType.OPPORTUNITY
        ):
            raise InvalidWorkflowConfigurationError("CHANGE_STAGE only applies to opportunities.")
        if (
            action_type is WorkflowActionType.CHANGE_STATUS
            and entity_type is not WorkflowEntityType.LEAD
        ):
            raise InvalidWorkflowConfigurationError("CHANGE_STATUS only applies to leads.")
        if action_type in _REQUIRES_CRM_ENTITY and entity_type is WorkflowEntityType.TASK:
            raise InvalidWorkflowConfigurationError(
                f"{action_type.value} cannot link to a task-triggered workflow."
            )
        if action_type is WorkflowActionType.UPDATE_FIELD:
            field = action.get("field")
            if field not in ALLOWED_UPDATE_FIELDS.get(entity_type, frozenset()):
                raise InvalidWorkflowConfigurationError(
                    f"'{field}' is not a field this workflow may update."
                )

    def _real_columns(self, entity_type: WorkflowEntityType) -> frozenset[str]:
        model = entity_service_for(entity_type, self._session).model
        return frozenset(attribute.key for attribute in class_mapper(model).column_attrs)


# =============================================================================
# Execution: shared by the outbox handler and the scheduled scan
# =============================================================================


async def _run_rule(
    session: AsyncSession,
    *,
    rule: WorkflowRule,
    entity_type: WorkflowEntityType,
    record: Any,
    trigger: str,
    source_event_id: uuid.UUID | None,
    dedupe_key: str | None,
    correlation_id: uuid.UUID,
    depth: int,
) -> bool:
    """Evaluate ``rule`` against ``record`` and, if it matches, run its actions.

    Returns whether the rule actually ran its actions this call — ``False``
    for a condition that did not hold or a duplicate delivery, ``True``
    otherwise (whatever the actions' own outcome). The scheduled scanner uses
    this to report how many *records* it genuinely fired for, not how many it
    merely considered; the outbox handler ignores it; a rule that ran but
    whose actions all failed still returns ``True``, since it certainly did
    something the run history now has to say happened.

    Idempotency (Step 10): the ``WorkflowRun`` insert is the claim. It carries
    the same ``(workflow_rule_id, source_event_id)`` — or, for a scheduled
    rule, ``(workflow_rule_id, dedupe_key)`` — unique constraint the migration
    creates; a second attempt at the same event or the same scheduled day
    hits :class:`IntegrityError` inside its own savepoint and is treated as
    "already handled," never as a second run.

    Transaction safety (Step 15): every action runs inside its own savepoint,
    so one action's failure (a rejected email, a blueprint refusal) rolls
    back *only that action's* partial writes — the ``WorkflowRun`` row and
    every action before it stay committed to the outer transaction, and the
    ones after it still run.
    """
    service = entity_service_for(entity_type, session)
    context = service.workflow_context(record)
    matched = matches_conditions(
        logic=rule.condition_logic, conditions=rule.conditions, context=context
    )
    if not matched:
        return False

    now = dt.datetime.now(dt.UTC)
    run = WorkflowRun(
        organization_id=rule.organization_id,
        workflow_rule_id=rule.id,
        entity_type=entity_type,
        record_id=record.id,
        trigger=trigger,
        source_event_id=source_event_id,
        dedupe_key=dedupe_key,
        correlation_id=correlation_id,
        depth=depth,
        status=WorkflowRunStatus.SUCCEEDED,
        started_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError:
        logger.info(
            "workflow_run_duplicate_skipped",
            workflow_rule_id=str(rule.id),
            source_event_id=str(source_event_id) if source_event_id else None,
            dedupe_key=dedupe_key,
        )
        return False

    action_results: list[dict[str, Any]] = []
    succeeded = failed = 0
    next_hop = WorkflowExecutionContext(correlation_id=correlation_id, depth=depth + 1)
    with workflow_execution_scope(next_hop):
        for action in rule.actions:
            action_type = action.get("type")
            try:
                async with session.begin_nested():
                    detail = await execute_action(
                        session,
                        action,
                        organization_id=rule.organization_id,
                        entity_type=entity_type,
                        record=record,
                    )
                action_results.append(
                    {"type": action_type, "status": "SUCCEEDED", "detail": detail}
                )
                succeeded += 1
            except Exception as exc:  # one action must not stop the rest
                logger.warning(
                    "workflow_action_failed",
                    workflow_rule_id=str(rule.id),
                    action_type=action_type,
                    exc_info=True,
                )
                detail = exc.message if isinstance(exc, AppError) else str(exc)
                action_results.append(
                    {"type": action_type, "status": "FAILED", "detail": detail[:500]}
                )
                failed += 1

    run.actions_attempted = len(rule.actions)
    run.actions_succeeded = succeeded
    run.actions_failed = failed
    run.action_results = action_results
    run.status = (
        WorkflowRunStatus.SUCCEEDED
        if failed == 0
        else WorkflowRunStatus.PARTIAL
        if succeeded > 0
        else WorkflowRunStatus.FAILED
    )
    run.finished_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return True


# =============================================================================
# The outbox handler
# =============================================================================


async def handle_record_event(session: AsyncSession, event: OutboxEvent) -> None:
    """Registered for ``crm.record.event_occurred`` by ``app/api/router.py``.

    Re-reads the record fresh through the owning entity's own
    ``get_or_404`` — the payload's ``record_id`` is an identifier, never
    trusted data (the outbox's own rule; see ``platform.events.models``) — so
    a condition never evaluates against a value that went stale between
    enqueue and delivery.
    """
    payload = event.payload
    try:
        entity_type = WorkflowEntityType(payload["entity_type"])
        record_id = uuid.UUID(str(payload["record_id"]))
        trigger = str(payload["trigger"])
        changed_fields = dict(payload.get("changed_fields") or {})
        correlation_id = uuid.UUID(str(payload["correlation_id"]))
        depth = int(payload.get("depth", 0))
    except (KeyError, ValueError, TypeError) as exc:
        raise PermanentEventError(f"Malformed workflow record event payload: {exc}") from exc

    if event.organization_id is None:
        raise PermanentEventError("A record event arrived with no organization.")
    organization_id = event.organization_id

    rules = await WorkflowRuleRepository(session).active_for_entity_type(
        organization_id, entity_type
    )
    matched = [
        rule
        for rule in rules
        if rule_matches_trigger(
            trigger_type=rule.trigger_type,
            trigger_config=rule.trigger_config,
            trigger=trigger,
            changed_fields=changed_fields,
        )
    ]
    if not matched:
        return

    service = entity_service_for(entity_type, session)
    try:
        record = await service.get_or_404(record_id, organization_id)
    except NotFoundError as exc:
        raise PermanentEventError(f"The triggering record no longer exists: {exc}") from exc

    for rule in matched:
        try:
            await _run_rule(
                session,
                rule=rule,
                entity_type=entity_type,
                record=record,
                trigger=trigger,
                source_event_id=event.id,
                dedupe_key=None,
                correlation_id=correlation_id,
                depth=depth,
            )
        except Exception:  # one rule's bug must not sink the whole event
            logger.exception(
                "workflow_rule_processing_failed",
                workflow_rule_id=str(rule.id),
                event_id=str(event.id),
            )


# =============================================================================
# The scheduled scan
# =============================================================================


async def scan_scheduled_workflows(
    session_factory: async_sessionmaker[AsyncSession], *, now: dt.datetime | None = None
) -> int:
    """Fire every due ``SCHEDULED``/``TASK_DUE`` rule, across every organization.

    Same shape as ``platform.notifications.dispatch_due_reminders_for_all_organizations``:
    each organization gets its own transaction, scoped with
    ``provisioning_scope`` since there is no request establishing tenant
    context, and one organization's failure is logged and does not stop the
    rest.
    """
    when = now or dt.datetime.now(dt.UTC)
    total = 0

    async with session_factory() as scan_session:
        organization_ids = await organizations_for_session(
            scan_session
        ).list_active_organization_ids()

    for organization_id in organization_ids:
        try:
            async with (
                session_factory() as session,
                session.begin(),
                provisioning_scope(session, organization_id),
            ):
                rules = await WorkflowRuleRepository(session).all_active_scheduled(organization_id)
                for rule in rules:
                    total += await _scan_rule(
                        session, rule=rule, organization_id=organization_id, now=when
                    )
        except Exception:
            logger.exception(
                "scheduled_workflow_scan_failed_for_organization",
                organization_id=str(organization_id),
            )

    return total


async def _scan_rule(
    session: AsyncSession, *, rule: WorkflowRule, organization_id: uuid.UUID, now: dt.datetime
) -> int:
    offset_minutes = int(rule.trigger_config.get("offset_minutes", 0))
    threshold = now - dt.timedelta(minutes=offset_minutes)

    if rule.trigger_type is WorkflowTriggerType.TASK_DUE:
        candidates: Sequence[Any] = (
            await session.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.deleted_at.is_(None),
                    Task.due_date.is_not(None),
                    Task.due_date <= threshold,
                )
            )
        ).scalars().all()
        entity_type = WorkflowEntityType.TASK
    else:
        entity_type = rule.entity_type
        date_field = rule.trigger_config.get("date_field")
        if date_field not in SCHEDULED_DATE_FIELDS.get(entity_type, frozenset()):
            return 0
        model = entity_service_for(entity_type, session).model
        column = getattr(model, date_field)
        # ``expected_close_date`` (today's only allow-listed field) is a
        # plain ``Date``, not a timestamp — compare on the same terms.
        compare_value: Any = threshold.date() if column.type.python_type is dt.date else threshold
        candidates = (
            await session.execute(
                select(model).where(
                    model.organization_id == organization_id,
                    model.deleted_at.is_(None),
                    column.is_not(None),
                    column <= compare_value,
                )
            )
        ).scalars().all()

    fired = 0
    for record in candidates:
        dedupe_key = f"{rule.id}:{record.id}:{now.date().isoformat()}"
        try:
            ran = await _run_rule(
                session,
                rule=rule,
                entity_type=entity_type,
                record=record,
                trigger="scheduled",
                source_event_id=None,
                dedupe_key=dedupe_key,
                correlation_id=uuid.uuid4(),
                depth=0,
            )
            if ran:
                fired += 1
        except Exception:
            logger.exception(
                "scheduled_workflow_run_failed",
                workflow_rule_id=str(rule.id),
                record_id=str(record.id),
            )
    return fired


# =============================================================================
# History
# =============================================================================


async def list_workflow_runs(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    params: PageParams,
    workflow_rule_id: uuid.UUID | None = None,
) -> tuple[Sequence[WorkflowRun], int]:
    filters = []
    if workflow_rule_id is not None:
        filters.append(WorkflowRun.workflow_rule_id == workflow_rule_id)
    return await WorkflowRunRepository(session).list_for_organization(
        organization_id, params=params, filters=filters
    )


__all__ = [
    "MODULE",
    "DuplicateWorkflowNameError",
    "InvalidWorkflowConfigurationError",
    "WorkflowRuleService",
    "handle_record_event",
    "list_workflow_runs",
    "scan_scheduled_workflows",
]
