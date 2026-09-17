"""Pure functions: does this event match this rule's trigger, do its conditions hold.

No session, no I/O — same discipline as
:mod:`app.products.crm.layouts.evaluate`, which this module wraps rather than
reimplements for the "do the conditions hold" half. The "does the trigger
match" half is new here: a layout rule has no concept of *why* a record's
values are what they are, but a workflow rule does — "the status changed" and
"the status is currently Qualified" are different questions, and only the
first is what ``trigger_type`` names.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.products.crm.layouts.evaluate import evaluate_condition
from app.products.crm.workflows.models import WorkflowEntityType, WorkflowTriggerType

#: Date fields a ``SCHEDULED`` rule may watch, per entity. Closed and short —
#: like ``BlueprintField``, a free-text column name would let an
#: administrator configure a scan over a field with no reliable date
#: semantics (or one RLS would refuse to let the scanner read cheaply).
SCHEDULED_DATE_FIELDS: dict[WorkflowEntityType, frozenset[str]] = {
    WorkflowEntityType.OPPORTUNITY: frozenset({"expected_close_date"}),
}


def _as_text(value: Any) -> str:
    """Stringify one side of a ``to``/``from`` comparison.

    Numeric first: a JSON-round-tripped ``Decimal`` and the string an
    administrator typed into the trigger config are rarely spelled alike —
    ``75000`` (a whole-number ``deal_value`` re-serializes without its
    trailing zeros) against a configured ``"75000.00"`` — and both name the
    identical value. Comparing them as text would make a numeric trigger
    fail to match its own worked example. Anything that does not parse as a
    number (a status, a stage name) falls back to case-insensitive text,
    the same rule ``layouts.evaluate`` states for the same reason: one
    condition editor has to work for every field type without knowing which
    one it is pointed at.
    """
    if value is None:
        return ""
    try:
        return repr(float(value))
    except (TypeError, ValueError):
        return str(value).strip().lower()


def _field_delta_matches(config: Mapping[str, Any], delta: Mapping[str, Any] | None) -> bool:
    """Whether a ``{"before":..., "after":...}`` delta satisfies an optional
    ``to``/``from`` narrowing in ``trigger_config``. No delta means the field
    named by the rule did not change at all, which never matches."""
    if delta is None:
        return False
    if "to" in config and _as_text(delta.get("after")) != _as_text(config["to"]):
        return False
    return not ("from" in config and _as_text(delta.get("before")) != _as_text(config["from"]))


def rule_matches_trigger(
    *,
    trigger_type: WorkflowTriggerType,
    trigger_config: Mapping[str, Any],
    trigger: str,
    changed_fields: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Whether an event with this ``trigger`` reason fires a rule of this shape.

    ``trigger`` is the event's own reason string (``"created"``, ``"updated"``,
    ``"status_changed"``, ``"stage_changed"``) — see
    ``shared.service._enqueue_record_event``. ``changed_fields`` maps a field
    name to its ``{"before", "after"}`` delta, present only for fields that
    actually changed value.

    ``SCHEDULED`` and ``TASK_DUE`` rules are never matched here: they have no
    triggering event at all and are evaluated only by
    ``.service.scan_scheduled_workflows``. A rule of either shape is refused a
    match unconditionally rather than raising, so a mixed batch of rules for
    one entity can be checked in one loop without a caller filtering first.
    """
    if trigger_type is WorkflowTriggerType.RECORD_CREATED:
        return trigger == "created"

    if trigger_type is WorkflowTriggerType.RECORD_UPDATED:
        return trigger in ("updated", "status_changed", "stage_changed")

    if trigger_type is WorkflowTriggerType.FIELD_CHANGED:
        field = trigger_config.get("field")
        if not isinstance(field, str) or not field:
            return False
        return _field_delta_matches(trigger_config, changed_fields.get(field))

    if trigger_type is WorkflowTriggerType.STATUS_CHANGED:
        if trigger != "status_changed":
            return False
        config = {
            k: v
            for k, v in (
                ("to", trigger_config.get("to")),
                ("from", trigger_config.get("from")),
            )
            if v is not None
        }
        return _field_delta_matches(config, changed_fields.get("status"))

    if trigger_type is WorkflowTriggerType.STAGE_CHANGED:
        if trigger != "stage_changed":
            return False
        config = {
            k: v
            for k, v in (
                ("to", trigger_config.get("to_stage_name")),
                ("from", trigger_config.get("from_stage_name")),
            )
            if v is not None
        }
        return _field_delta_matches(config, changed_fields.get("stage_name"))

    if trigger_type is WorkflowTriggerType.OWNER_CHANGED:
        return trigger == "updated" and "owner_id" in changed_fields

    # SCHEDULED, TASK_DUE: no event triggers these.
    return False


def matches_conditions(
    *, logic: str, conditions: Sequence[Mapping[str, Any]], context: Mapping[str, Any]
) -> bool:
    """Whether every (``AND``) or any (``OR``) condition holds against ``context``.

    A rule with no conditions always matches — unlike
    ``layouts.evaluate_rule``, where an empty condition list is a half-built
    rule that must never fire. Here it is a deliberate, common configuration:
    "whenever a lead is created, assign it and notify the team," with nothing
    further to check. The two modules disagree on purpose; each states why in
    its own docstring.
    """
    if not conditions:
        return True
    results = [evaluate_condition(condition, context) for condition in conditions]
    return all(results) if logic.upper() == "AND" else any(results)


__all__ = ["SCHEDULED_DATE_FIELDS", "matches_conditions", "rule_matches_trigger"]
