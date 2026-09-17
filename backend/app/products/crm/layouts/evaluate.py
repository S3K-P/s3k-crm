"""Pure evaluation of conditional field rules.

No session, no organization id, no I/O — everything here is a function of a
rule (or a layout's rules) and a record's current field values, which is what
makes it usable from two places that must agree byte-for-byte: the server-side
enforcement in :class:`~app.products.crm.custom_fields.service.CustomFieldValueService`
(authoritative) and, mirrored in ``frontend/features/crm/layouts/evaluate.ts``,
the live preview a form renders while a user is still typing (a convenience —
never trusted on its own, see the module docstring on ``layouts/models.py``).

**Operator semantics**, stated once here because both implementations have to
agree on them:

* ``equals`` / ``not_equals`` — case-insensitive string comparison after both
  sides are stringified. A boolean, number or picklist value is compared as
  text, which is what makes one rule editor work for every field type without
  the condition needing to know the target's declared type.
* ``contains`` / ``not_contains`` — case-insensitive substring test. Applied to
  the stringified value; against a multi-select, tests each selected option.
* ``greater_than`` / ``less_than`` — numeric comparison. A value that cannot
  parse as a number never satisfies either — a text field compared numerically
  is a rule that can never match, not an error, because the rule was likely
  authored for a field that used to be numeric.
* ``is_empty`` / ``is_not_empty`` — ``None``, ``""``, and ``[]`` all count as
  empty; a literal ``0`` or ``False`` does not.
* ``in`` / ``not_in`` — ``value`` is a list; membership test, case-insensitive
  for strings.

A missing field (the condition names a field the record has no value for) is
treated as an empty value flowing into the same rules above — ``equals``
against anything but empty is false, ``is_empty`` is true — rather than raising,
because a condition referencing a field the record simply has not been given a
value for yet is the common case on a new record, not a configuration error.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from typing import Any, Protocol


class RuleLike(Protocol):
    """Structural shape :func:`evaluate_rule` needs — real ORM rows and the
    lightweight doubles in ``tests/unit/test_layout_evaluate.py`` both satisfy
    it. Every member is a read-only property rather than a plain attribute
    deliberately: mypy checks a Protocol's plain attributes invariantly, which
    would reject ``LayoutFieldRule.logic`` (a ``RuleLogic``, a ``str``
    subtype) as not exactly ``str``. A property is checked covariantly, which
    is what "this is a value I only read" actually means here.
    """

    @property
    def target_field_key(self) -> str: ...
    @property
    def logic(self) -> str: ...
    @property
    def conditions(self) -> Sequence[Mapping[str, Any]]: ...
    @property
    def effect_visible(self) -> bool: ...
    @property
    def effect_required(self) -> bool | None: ...
    @property
    def position(self) -> int: ...


#: The operator vocabulary a condition may use. Closed, like
#: ``custom_fields.models.CustomFieldType`` — an operator not in this set is
#: refused at rule-save time rather than silently never matching.
OPERATORS: frozenset[str] = frozenset(
    {
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "greater_than",
        "less_than",
        "is_empty",
        "is_not_empty",
        "in",
        "not_in",
    }
)


@dataclasses.dataclass(frozen=True, slots=True)
class FieldState:
    """The effective state of one field after every matching rule is applied."""

    visible: bool = True
    required: bool | None = None


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _as_text(value: Any) -> str:
    """Stringify for comparison. ``None`` is the empty string, not "none" —
    so an ``equals`` condition against ``""`` matches a field the record has
    no value for, the same thing :func:`_is_empty` already treats as nothing.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip().lower()


def _as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_condition(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    """Whether one condition holds against ``context`` (field_key -> value)."""
    field_key = str(condition.get("field_key", ""))
    operator = str(condition.get("operator", ""))
    expected = condition.get("value")
    actual = context.get(field_key)

    if operator == "is_empty":
        return _is_empty(actual)
    if operator == "is_not_empty":
        return not _is_empty(actual)

    if operator in {"in", "not_in"}:
        options = expected if isinstance(expected, (list, tuple, set)) else [expected]
        member = _as_text(actual) in {_as_text(option) for option in options}
        return member if operator == "in" else not member

    if operator in {"contains", "not_contains"}:
        haystack = actual if isinstance(actual, (list, tuple, set)) else [actual]
        needle = _as_text(expected)
        found = any(needle in _as_text(item) for item in haystack) if needle else False
        return found if operator == "contains" else not found

    if operator in {"greater_than", "less_than"}:
        actual_number, expected_number = _as_number(actual), _as_number(expected)
        if actual_number is None or expected_number is None:
            return False
        return (
            actual_number > expected_number
            if operator == "greater_than"
            else actual_number < expected_number
        )

    matches = _as_text(actual) == _as_text(expected)
    return matches if operator == "equals" else not matches


def evaluate_rule(rule: RuleLike, context: Mapping[str, Any]) -> bool:
    """Whether ``rule`` matches — its conditions combined by its ``logic``.

    A rule with no conditions never matches. An empty condition list reads as
    a configuration mistake (a rule an administrator started and never
    finished), and treating it as "always matches" would mean a half-built
    rule could hide or require a field for every record until someone noticed.
    """
    conditions = rule.conditions
    if not conditions:
        return False
    results = [evaluate_condition(condition, context) for condition in conditions]
    return all(results) if str(rule.logic).upper() == "AND" else any(results)


def effective_custom_field_states(
    rules: Sequence[RuleLike],
    context: Mapping[str, Any],
    *,
    base_visible: Mapping[str, bool] = {},
    base_required: Mapping[str, bool] = {},
) -> dict[str, FieldState]:
    """Resolve every rule-governed custom field's final visible/required state.

    Precedence, applied in this order — each stage may only be *overridden* by
    the next, never the reverse, and this is the one place that order is
    decided:

    1. The field's own definition/layout default (``base_visible``/
       ``base_required`` — typically ``True`` / the custom field definition's
       ``is_required``, but not this module's concern to know that).
    2. Rules targeting the field, applied in ascending ``position`` — a later
       rule overrides an earlier one that also matched, which is what lets an
       administrator add a more specific rule after a general one without
       reordering the general one away.
    3. **Hidden implies not required, unconditionally**, applied last and
       after every rule: a field a matching rule (or the base state) has
       hidden cannot be the reason a write is refused, because nothing in the
       UI a hidden field would render in can be asked to fill it in. This is
       the server's own guarantee, independent of what any client rendered —
       see the module docstring on ``layouts/models.py``.

    Only fields named by at least one rule OR present in ``base_required``
    appear in the result; a field this layout says nothing about is left for
    the caller's own default to decide, unaffected by this function.
    """
    target_keys = {rule.target_field_key for rule in rules} | set(base_required) | set(
        base_visible
    )
    states: dict[str, FieldState] = {
        key: FieldState(
            visible=base_visible.get(key, True), required=base_required.get(key, False)
        )
        for key in target_keys
    }

    for rule in sorted(rules, key=lambda r: r.position):
        if not evaluate_rule(rule, context):
            continue
        current = states.get(rule.target_field_key, FieldState())
        states[rule.target_field_key] = FieldState(
            visible=rule.effect_visible,
            required=(
                rule.effect_required if rule.effect_required is not None else current.required
            ),
        )

    return {
        key: (state if state.visible else FieldState(visible=False, required=False))
        for key, state in states.items()
    }


__all__ = [
    "OPERATORS",
    "FieldState",
    "RuleLike",
    "effective_custom_field_states",
    "evaluate_condition",
    "evaluate_rule",
]
