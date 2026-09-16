"""Conditional layout rule evaluation, without a database.

:mod:`app.products.crm.layouts.evaluate` is pure — a rule (or several) and a
record's field values in, a decision out — so every operator and the
precedence rules (layout override < rule < hidden-implies-not-required) are
exercised here exhaustively, the same way custom-field coercion is tested in
``test_custom_field_validation.py``.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.products.crm.layouts.evaluate import (
    FieldState,
    effective_custom_field_states,
    evaluate_condition,
    evaluate_rule,
)


@dataclasses.dataclass
class _Rule:
    target_field_key: str = "custom:qualification_details"
    logic: str = "AND"
    conditions: list[dict[str, object]] = dataclasses.field(default_factory=list)
    effect_visible: bool = True
    effect_required: bool | None = None
    position: int = 0


# --- Operators ---------------------------------------------------------


@pytest.mark.parametrize(
    ("operator", "actual", "expected", "result"),
    [
        ("equals", "Qualified", "qualified", True),
        ("equals", "Qualified", "New", False),
        ("equals", None, "", True),  # both stringify to empty
        ("not_equals", "Qualified", "New", True),
        ("not_equals", "Qualified", "Qualified", False),
        ("contains", ["EMEA", "APAC"], "emea", True),
        ("contains", "Enterprise Account", "prise", True),
        ("contains", "Enterprise Account", "zzz", False),
        ("not_contains", "Enterprise Account", "zzz", True),
        ("greater_than", 50, 10, True),
        ("greater_than", 5, 10, False),
        ("greater_than", "not-a-number", 10, False),
        ("less_than", 5, 10, True),
        ("less_than", "not-a-number", 10, False),
        ("is_empty", None, None, True),
        ("is_empty", "", None, True),
        ("is_empty", [], None, True),
        ("is_empty", 0, None, False),
        ("is_empty", False, None, False),
        ("is_empty", "x", None, False),
        ("is_not_empty", "x", None, True),
        ("is_not_empty", None, None, False),
        ("in", "EMEA", ["emea", "apac"], True),
        ("in", "LATAM", ["emea", "apac"], False),
        ("not_in", "LATAM", ["emea", "apac"], True),
    ],
)
def test_operator_semantics(
    operator: str, actual: object, expected: object, result: bool
) -> None:
    condition = {"field_key": "status", "operator": operator, "value": expected}
    assert evaluate_condition(condition, {"status": actual}) is result


def test_a_missing_field_reads_as_empty_not_an_error() -> None:
    """A condition on a field the record has no value for yet is common, not broken."""
    assert evaluate_condition({"field_key": "status", "operator": "is_empty"}, {}) is True
    condition = {"field_key": "status", "operator": "equals", "value": "x"}
    assert evaluate_condition(condition, {}) is False


# --- Rule combination ----------------------------------------------------


def test_and_requires_every_condition() -> None:
    rule = _Rule(
        logic="AND",
        conditions=[
            {"field_key": "status", "operator": "equals", "value": "QUALIFIED"},
            {"field_key": "industry", "operator": "equals", "value": "Finance"},
        ],
    )
    assert evaluate_rule(rule, {"status": "QUALIFIED", "industry": "Finance"}) is True
    assert evaluate_rule(rule, {"status": "QUALIFIED", "industry": "Retail"}) is False


def test_or_requires_any_condition() -> None:
    rule = _Rule(
        logic="OR",
        conditions=[
            {"field_key": "status", "operator": "equals", "value": "QUALIFIED"},
            {"field_key": "status", "operator": "equals", "value": "CONTACTED"},
        ],
    )
    assert evaluate_rule(rule, {"status": "CONTACTED"}) is True
    assert evaluate_rule(rule, {"status": "NEW"}) is False


def test_a_rule_with_no_conditions_never_matches() -> None:
    """An unfinished rule must not silently apply to every record."""
    assert evaluate_rule(_Rule(conditions=[]), {"status": "QUALIFIED"}) is False


# --- Precedence: base < rule < hidden-implies-not-required -----------------


def test_no_matching_rule_falls_back_to_the_base_state() -> None:
    rule = _Rule(conditions=[{"field_key": "status", "operator": "equals", "value": "QUALIFIED"}])
    states = effective_custom_field_states(
        [rule],
        {"status": "NEW"},
        base_visible={"custom:qualification_details": False},
        base_required={"custom:qualification_details": True},
    )
    assert states["custom:qualification_details"] == FieldState(visible=False, required=False)


def test_a_matching_rule_overrides_the_base_state() -> None:
    rule = _Rule(
        conditions=[{"field_key": "status", "operator": "equals", "value": "QUALIFIED"}],
        effect_visible=True,
        effect_required=True,
    )
    states = effective_custom_field_states(
        [rule],
        {"status": "QUALIFIED"},
        base_visible={"custom:qualification_details": False},
        base_required={"custom:qualification_details": False},
    )
    assert states["custom:qualification_details"] == FieldState(visible=True, required=True)


def test_hidden_is_never_required_even_if_a_rule_says_so() -> None:
    """The server's own guarantee: a hidden field cannot block a write."""
    rule = _Rule(
        conditions=[{"field_key": "status", "operator": "equals", "value": "QUALIFIED"}],
        effect_visible=False,
        effect_required=True,
    )
    states = effective_custom_field_states([rule], {"status": "QUALIFIED"})
    assert states["custom:qualification_details"] == FieldState(visible=False, required=False)


def test_a_rule_with_no_required_effect_leaves_the_base_requiredness() -> None:
    """``effect_required=None`` changes visibility only."""
    rule = _Rule(
        conditions=[{"field_key": "status", "operator": "equals", "value": "QUALIFIED"}],
        effect_visible=True,
        effect_required=None,
    )
    states = effective_custom_field_states(
        [rule],
        {"status": "QUALIFIED"},
        base_visible={"custom:qualification_details": False},
        base_required={"custom:qualification_details": True},
    )
    assert states["custom:qualification_details"] == FieldState(visible=True, required=True)


def test_later_position_wins_when_two_rules_match_the_same_field() -> None:
    earlier = _Rule(
        conditions=[{"field_key": "status", "operator": "is_not_empty"}],
        effect_visible=True,
        effect_required=False,
        position=0,
    )
    later = _Rule(
        conditions=[{"field_key": "status", "operator": "equals", "value": "QUALIFIED"}],
        effect_visible=True,
        effect_required=True,
        position=1,
    )
    states = effective_custom_field_states(
        [later, earlier],  # deliberately out of order — the function sorts by position
        {"status": "QUALIFIED"},
    )
    assert states["custom:qualification_details"].required is True


def test_a_field_named_by_nothing_is_absent_from_the_result() -> None:
    states = effective_custom_field_states([], {"status": "QUALIFIED"})
    assert states == {}
