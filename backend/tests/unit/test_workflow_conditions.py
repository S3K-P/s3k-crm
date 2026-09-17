"""Trigger matching and condition evaluation, without a database.

:mod:`app.products.crm.workflows.conditions` is pure — an event's trigger
reason and its ``changed_fields`` delta in, a yes/no out for
:func:`rule_matches_trigger`; a rule's conditions and a record's context in,
a yes/no out for :func:`matches_conditions` (a thin wrapper over
``layouts.evaluate``, already exhaustively tested there). Every
``WorkflowTriggerType`` is exercised here, including the negative cases: an
``updated`` event must not satisfy a ``STATUS_CHANGED`` rule, a field that
did not change must not satisfy a ``FIELD_CHANGED`` rule naming it.
"""

from __future__ import annotations

from app.products.crm.workflows.conditions import matches_conditions, rule_matches_trigger
from app.products.crm.workflows.models import WorkflowTriggerType

# --- RECORD_CREATED / RECORD_UPDATED ----------------------------------------


def test_record_created_matches_only_a_created_event() -> None:
    assert rule_matches_trigger(
        trigger_type=WorkflowTriggerType.RECORD_CREATED,
        trigger_config={},
        trigger="created",
        changed_fields={},
    )
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.RECORD_CREATED,
        trigger_config={},
        trigger="updated",
        changed_fields={},
    )


def test_record_updated_matches_any_update_shaped_trigger() -> None:
    for trigger in ("updated", "status_changed", "stage_changed"):
        assert rule_matches_trigger(
            trigger_type=WorkflowTriggerType.RECORD_UPDATED,
            trigger_config={},
            trigger=trigger,
            changed_fields={},
        )
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.RECORD_UPDATED,
        trigger_config={},
        trigger="created",
        changed_fields={},
    )


# --- FIELD_CHANGED -----------------------------------------------------------


def test_field_changed_requires_the_named_field_to_have_changed() -> None:
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config={"field": "priority"},
        trigger="updated",
        changed_fields={"industry": {"before": "Retail", "after": "Finance"}},
    ), "a different field changing must not satisfy a rule naming another one"

    assert rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config={"field": "priority"},
        trigger="updated",
        changed_fields={"priority": {"before": "LOW", "after": "HIGH"}},
    )


def test_field_changed_to_narrows_the_destination_value() -> None:
    config = {"field": "priority", "to": "HIGH"}
    assert rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config=config,
        trigger="updated",
        changed_fields={"priority": {"before": "LOW", "after": "HIGH"}},
    )
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config=config,
        trigger="updated",
        changed_fields={"priority": {"before": "LOW", "after": "MEDIUM"}},
    )


def test_field_changed_to_matches_a_number_regardless_of_how_it_is_spelled() -> None:
    """A whole-number ``Decimal`` re-serializes without its trailing zeros —
    ``jsonable_encoder`` turns ``Decimal("75000.00")`` into the JSON number
    ``75000`` — so a rule configured with ``"75000.00"`` must still match.
    Found via manual browser verification: a ``deal_value`` trigger silently
    never fired until this normalization was added.
    """
    config = {"field": "deal_value", "to": "75000.00"}
    assert rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config=config,
        trigger="updated",
        changed_fields={"deal_value": {"before": 50000, "after": 75000}},
    )
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config=config,
        trigger="updated",
        changed_fields={"deal_value": {"before": 50000, "after": 80000}},
    )


def test_field_changed_from_narrows_the_origin_value() -> None:
    config = {"field": "priority", "from": "LOW"}
    assert rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config=config,
        trigger="updated",
        changed_fields={"priority": {"before": "LOW", "after": "HIGH"}},
    )
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config=config,
        trigger="updated",
        changed_fields={"priority": {"before": "MEDIUM", "after": "HIGH"}},
    )


def test_field_changed_with_no_field_configured_never_matches() -> None:
    """A half-configured rule must not silently match everything."""
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.FIELD_CHANGED,
        trigger_config={},
        trigger="updated",
        changed_fields={"priority": {"before": "LOW", "after": "HIGH"}},
    )


# --- STATUS_CHANGED / STAGE_CHANGED / OWNER_CHANGED -------------------------


def test_status_changed_only_matches_a_status_changed_event() -> None:
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.STATUS_CHANGED,
        trigger_config={},
        trigger="updated",
        changed_fields={"status": {"before": "NEW", "after": "QUALIFIED"}},
    ), "a plain field update must not satisfy STATUS_CHANGED even if status happened to move"

    assert rule_matches_trigger(
        trigger_type=WorkflowTriggerType.STATUS_CHANGED,
        trigger_config={"to": "QUALIFIED"},
        trigger="status_changed",
        changed_fields={"status": {"before": "NEW", "after": "QUALIFIED"}},
    )
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.STATUS_CHANGED,
        trigger_config={"to": "QUALIFIED"},
        trigger="status_changed",
        changed_fields={"status": {"before": "NEW", "after": "CONTACTED"}},
    )


def test_stage_changed_matches_by_stage_name_not_id() -> None:
    assert rule_matches_trigger(
        trigger_type=WorkflowTriggerType.STAGE_CHANGED,
        trigger_config={"to_stage_name": "Closed Won"},
        trigger="stage_changed",
        changed_fields={
            "stage_id": {"before": "s1", "after": "s2"},
            "stage_name": {"before": "Negotiation", "after": "Closed Won"},
        },
    )
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.STAGE_CHANGED,
        trigger_config={"to_stage_name": "Closed Won"},
        trigger="stage_changed",
        changed_fields={
            "stage_id": {"before": "s1", "after": "s3"},
            "stage_name": {"before": "Negotiation", "after": "Proposal"},
        },
    )


def test_owner_changed_matches_any_owner_id_update() -> None:
    assert rule_matches_trigger(
        trigger_type=WorkflowTriggerType.OWNER_CHANGED,
        trigger_config={},
        trigger="updated",
        changed_fields={"owner_id": {"before": "u1", "after": "u2"}},
    )
    assert not rule_matches_trigger(
        trigger_type=WorkflowTriggerType.OWNER_CHANGED,
        trigger_config={},
        trigger="updated",
        changed_fields={"priority": {"before": "LOW", "after": "HIGH"}},
    )


# --- SCHEDULED / TASK_DUE never match a record event ------------------------


def test_scheduled_and_task_due_are_never_matched_by_a_record_event() -> None:
    """These fire only from the periodic scan (`.service.scan_scheduled_workflows`)."""
    for trigger_type in (WorkflowTriggerType.SCHEDULED, WorkflowTriggerType.TASK_DUE):
        assert not rule_matches_trigger(
            trigger_type=trigger_type,
            trigger_config={},
            trigger="updated",
            changed_fields={},
        )


# --- matches_conditions ------------------------------------------------------


def test_no_conditions_always_matches() -> None:
    """Unlike a layout rule, an empty condition list is a deliberate,
    common configuration — "whenever created, always act" — not a mistake."""
    assert matches_conditions(logic="AND", conditions=[], context={})


def test_and_requires_every_condition() -> None:
    conditions = [
        {"field_key": "industry", "operator": "equals", "value": "Finance"},
        {"field_key": "priority", "operator": "equals", "value": "HIGH"},
    ]
    assert matches_conditions(
        logic="AND", conditions=conditions, context={"industry": "Finance", "priority": "HIGH"}
    )
    assert not matches_conditions(
        logic="AND", conditions=conditions, context={"industry": "Finance", "priority": "LOW"}
    )


def test_or_requires_any_condition() -> None:
    conditions = [
        {"field_key": "industry", "operator": "equals", "value": "Finance"},
        {"field_key": "priority", "operator": "equals", "value": "HIGH"},
    ]
    assert matches_conditions(
        logic="OR", conditions=conditions, context={"industry": "Retail", "priority": "HIGH"}
    )
    assert not matches_conditions(
        logic="OR", conditions=conditions, context={"industry": "Retail", "priority": "LOW"}
    )


def test_logic_is_case_insensitive() -> None:
    conditions = [{"field_key": "industry", "operator": "equals", "value": "Finance"}]
    assert matches_conditions(logic="and", conditions=conditions, context={"industry": "Finance"})
