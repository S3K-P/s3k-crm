"""Filtering and sorting a list screen by a tenant-defined field.

A custom value lives inside a JSONB document, which has no column type, so a
comparison has to be told what the value *means* before it can mean anything.
That answer is on the definition, and this module is the only place it is
turned into SQL.

**Why a cast rather than text comparison.** ``custom_fields->>'deal_size'``
returns text, and text ordering puts "100" before "9". Casting per the
definition's declared type is what makes ``>= 500`` and ``ORDER BY`` answer the
question the user asked. The cast is chosen from the definition — a value the
tenant's administrator set, resolved through the definitions table — never from
anything in the request, so no request can select an arbitrary cast.

**Why a bad value cannot 500 the list.** A NUMBER field can hold text if the
document predates the definition, or if a row was written by a path that is not
the API. ``::numeric`` on that row raises, and one bad row would take down the
whole list screen for everybody. Every numeric and temporal comparison is
therefore guarded by a regex on the text form first; PostgreSQL's ``AND``
does not guarantee evaluation order in general, but a ``CASE`` does, so the
cast happens only where the guard already passed.

**Why the api_name is never interpolated.** It arrives from the query string.
It is resolved against the tenant's own definitions first — an unrecognised
name is a 422, not a filter — and then passed as a **bound parameter** to the
``->>`` operator rather than being formatted into SQL text.
"""

from __future__ import annotations

import enum
import json
from typing import Any
from typing import cast as narrow  # `cast` is SQLAlchemy's SQL CAST, below

from sqlalchemy import Boolean, ColumnElement, Date, DateTime, Numeric, case, cast, func, literal
from sqlalchemy.dialects.postgresql import JSONB

from app.core.exceptions import ValidationFailedError
from app.products.crm.custom_fields.models import (
    FILTERABLE_TYPES,
    SORTABLE_TYPES,
    CustomFieldDefinition,
    CustomFieldType,
)
from app.products.crm.custom_fields.validation import coerce

#: Prefix that marks a query-string parameter as a custom-field filter.
#:
#: Namespaced so a custom field called ``status`` can never shadow the built-in
#: ``?status=`` every list endpoint already has. Without it, adding a field
#: would silently change the meaning of an existing filter.
FILTER_PREFIX = "cf_"

#: Rejects anything ``::numeric`` would raise on. Optional sign, digits, an
#: optional fractional part, and nothing else.
_NUMERIC_GUARD = r"^-?[0-9]+(\.[0-9]+)?$"

#: ``YYYY-MM-DD`` with an optional time part, which is what `validation.py`
#: writes for DATE and DATETIME. Deliberately not a full ISO-8601 grammar: this
#: guards a cast, so being narrower than the cast accepts is safe and being
#: wider is not.
_DATE_GUARD = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"


class FilterOperator(enum.StrEnum):
    """Comparisons a list filter may make.

    Closed, and small on purpose: each member below has one SQL shape and one
    type rule. ``CONTAINS`` is the only text-shaped one and is deliberately a
    substring match rather than full-text — custom fields are not in any
    search vector, and pretending otherwise would give a "search" that quietly
    missed most of what a user typed.
    """

    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    CONTAINS = "contains"
    IN = "in"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


#: Operators legal per field type. A range over a picklist or a ``contains``
#: over a boolean are requests with no meaning, and answering them with an
#: empty page would look like a data problem rather than a bad filter.
_ORDERED = (
    FilterOperator.LT,
    FilterOperator.LTE,
    FilterOperator.GT,
    FilterOperator.GTE,
)
_PRESENCE = (FilterOperator.IS_EMPTY, FilterOperator.IS_NOT_EMPTY)
_EQUALITY = (FilterOperator.EQ, FilterOperator.NE, FilterOperator.IN)

_ALLOWED_OPERATORS: dict[CustomFieldType, tuple[FilterOperator, ...]] = {
    CustomFieldType.TEXT: (*_EQUALITY, FilterOperator.CONTAINS, *_PRESENCE),
    CustomFieldType.TEXTAREA: (FilterOperator.CONTAINS, *_PRESENCE),
    CustomFieldType.NUMBER: (*_EQUALITY, *_ORDERED, *_PRESENCE),
    CustomFieldType.DECIMAL: (*_EQUALITY, *_ORDERED, *_PRESENCE),
    CustomFieldType.DATE: (*_EQUALITY, *_ORDERED, *_PRESENCE),
    CustomFieldType.DATETIME: (*_EQUALITY, *_ORDERED, *_PRESENCE),
    CustomFieldType.BOOLEAN: (FilterOperator.EQ, FilterOperator.NE, *_PRESENCE),
    CustomFieldType.EMAIL: (*_EQUALITY, FilterOperator.CONTAINS, *_PRESENCE),
    CustomFieldType.URL: (*_EQUALITY, FilterOperator.CONTAINS, *_PRESENCE),
    CustomFieldType.PHONE: (*_EQUALITY, FilterOperator.CONTAINS, *_PRESENCE),
    CustomFieldType.PICKLIST: (*_EQUALITY, *_PRESENCE),
    # `eq` on a multi-picklist means "holds this option", not "holds exactly
    # this set" — the question a list filter is ever asked. `in` means "holds
    # any of these".
    CustomFieldType.MULTI_PICKLIST: (
        FilterOperator.EQ,
        FilterOperator.NE,
        FilterOperator.IN,
        *_PRESENCE,
    ),
}


def _text_of(model: type[Any], api_name: str) -> ColumnElement[str]:
    """``custom_fields ->> :api_name`` with the key as a bound parameter.

    ``op()`` is untyped in SQLAlchemy's stubs — it has to be, since a custom
    operator's result type is not knowable — so the narrowing happens here,
    once, rather than at each of the dozen places the expression is used.
    """
    return narrow("ColumnElement[str]", model.custom_fields.op("->>")(literal(api_name)))


def _guarded(text: ColumnElement[str], guard: str, target: Any) -> ColumnElement[Any]:
    """Cast ``text`` to ``target`` only on rows whose text form is castable.

    ``CASE`` is what makes this safe: unlike ``AND``, its branches are
    guaranteed not to be evaluated when the condition is false, so a row
    holding "n/a" in a NUMBER field yields NULL here instead of aborting the
    statement. NULL never satisfies a comparison, so such a row is simply not
    in the result — which is the correct answer to "value greater than 500".
    """
    return case((text.op("~")(guard), cast(text, target)), else_=None)


def typed_value(model: type[Any], definition: CustomFieldDefinition) -> ColumnElement[Any]:
    """The stored value of ``definition``, cast to something comparable.

    Used for both filtering and sorting, so a list ordered by a field and
    filtered on it agree about what its values are.
    """
    text = _text_of(model, definition.api_name)
    match definition.field_type:
        case CustomFieldType.NUMBER | CustomFieldType.DECIMAL:
            return _guarded(text, _NUMERIC_GUARD, Numeric(20, 6))
        case CustomFieldType.DATE:
            return _guarded(text, _DATE_GUARD, Date)
        case CustomFieldType.DATETIME:
            return _guarded(text, _DATE_GUARD, DateTime(timezone=True))
        case CustomFieldType.BOOLEAN:
            # `->>` renders a JSON boolean as exactly 'true'/'false', so this
            # needs no guard: there is no other text the API can have stored,
            # and a foreign value simply compares unequal.
            return cast(text, Boolean)
        case _:
            return text


def sort_column(model: type[Any], definition: CustomFieldDefinition) -> ColumnElement[Any]:
    """The ORDER BY expression for a custom field.

    Raises:
        ValidationFailedError: the field's type has no ordering — see
            ``SORTABLE_TYPES``.
    """
    if definition.field_type not in SORTABLE_TYPES:
        raise ValidationFailedError(
            f"'{definition.label}' cannot be sorted on: a "
            f"{definition.field_type.value} field has no order."
        )
    return typed_value(model, definition)


def custom_field_filter(
    model: type[Any],
    definition: CustomFieldDefinition,
    operator: FilterOperator,
    raw: Any,
) -> ColumnElement[bool]:
    """Build one predicate over ``definition``'s stored value.

    Args:
        model: the record model being listed. Must carry ``custom_fields``.
        definition: the field, which supplies both the key and the type.
        operator: how to compare.
        raw: the comparison value, as it arrived from the query string.
            Coerced through exactly the path a *written* value takes, so
            ``?cf_renewal=2026-1-5`` filters on the same normalized form the
            record stored.

    Raises:
        ValidationFailedError: the operator does not apply to this field type,
            or the comparison value is not a value the field could hold.
    """
    if definition.field_type not in FILTERABLE_TYPES:
        raise ValidationFailedError(f"'{definition.label}' cannot be filtered on.")
    allowed = _ALLOWED_OPERATORS[definition.field_type]
    if operator not in allowed:
        raise ValidationFailedError(
            f"'{operator.value}' does not apply to '{definition.label}'. "
            f"Available: {', '.join(candidate.value for candidate in allowed)}."
        )

    document = model.custom_fields

    if operator is FilterOperator.IS_EMPTY:
        # A key that is absent and a key holding JSON null are both "empty" to
        # a user. `->>` returns SQL NULL for each, so one test covers both.
        return _text_of(model, definition.api_name).is_(None)
    if operator is FilterOperator.IS_NOT_EMPTY:
        return _text_of(model, definition.api_name).is_not(None)

    if definition.field_type is CustomFieldType.MULTI_PICKLIST:
        return _multi_picklist_filter(document, definition, operator, raw)

    if operator is FilterOperator.CONTAINS:
        needle = str(raw).strip()
        if not needle:
            raise ValidationFailedError("A 'contains' filter needs something to look for.")
        # `func.concat` rather than `%` string-building: the pattern is a bound
        # parameter, so a value containing `%` matches literally where the user
        # expects it to and cannot alter the shape of the LIKE.
        return func.lower(_text_of(model, definition.api_name)).like(
            func.concat("%", func.lower(needle), "%")
        )

    column = typed_value(model, definition)

    if operator is FilterOperator.IN:
        values = [_comparable(definition, item) for item in _as_list(raw)]
        if not values:
            raise ValidationFailedError("An 'in' filter needs at least one value.")
        return column.in_(values)

    value = _comparable(definition, raw)
    # `column` is `ColumnElement[Any]` — its type came from a runtime `cast()`
    # chosen by the definition — so every comparison below is `Any` to the type
    # checker. Narrowed once here rather than per branch.
    comparison: Any
    match operator:
        case FilterOperator.EQ:
            comparison = column == value
        case FilterOperator.NE:
            # `IS DISTINCT FROM`, not `!=`: a record with no value for the
            # field compares NULL under `!=` and would be excluded, so "not
            # EMEA" would silently drop every record nobody has filled in yet.
            comparison = column.is_distinct_from(value)
        case FilterOperator.LT:
            comparison = column < value
        case FilterOperator.LTE:
            comparison = column <= value
        case FilterOperator.GT:
            comparison = column > value
        case _:
            comparison = column >= value
    return narrow("ColumnElement[bool]", comparison)


def _multi_picklist_filter(
    document: Any,
    definition: CustomFieldDefinition,
    operator: FilterOperator,
    raw: Any,
) -> ColumnElement[bool]:
    """Containment over a stored array of option values.

    ``@>`` against a one-element array is an index-usable containment test —
    the GIN index on the column serves it directly — where an ``EXISTS`` over
    ``jsonb_array_elements`` could not be.
    """
    wanted = [str(item).strip() for item in _as_list(raw) if str(item).strip()]
    if not wanted:
        raise ValidationFailedError("This filter needs at least one option.")

    def holds(option: str) -> ColumnElement[bool]:
        # Serialized to JSON text and cast, rather than passing a Python dict
        # to ``literal``: SQLAlchemy has no type for a bare dict here and would
        # bind it as a string of its ``repr`` — single quotes, ``None`` for
        # null — which PostgreSQL rejects as malformed JSON. The dict is built
        # from the definition's own api_name and a validated option, and it is
        # still a bound parameter, so nothing from the request is interpolated.
        operand = json.dumps({definition.api_name: [option]})
        return narrow(
            "ColumnElement[bool]", document.op("@>")(cast(literal(operand), JSONB))
        )

    if operator is FilterOperator.NE:
        return ~holds(wanted[0])
    if len(wanted) == 1:
        return holds(wanted[0])
    from sqlalchemy import or_

    return or_(*(holds(option) for option in wanted))


def _as_list(raw: Any) -> list[Any]:
    if isinstance(raw, list | tuple | set):
        return list(raw)
    # A query string carries a repeated parameter as one comma-joined value as
    # often as it carries it repeated, and both spellings mean the same thing.
    return [part for part in str(raw).split(",") if part.strip()]


def _comparable(definition: CustomFieldDefinition, raw: Any) -> Any:
    """Normalize a filter value the way a stored value is normalized.

    Picklist membership is deliberately **not** checked: filtering for an
    option that was retired last week is a legitimate question about the
    records that still hold it, and refusing it would make those records
    unreachable from the list screen. So the option-set argument is empty and
    the value passes through as text.
    """
    if definition.field_type in {CustomFieldType.PICKLIST}:
        return str(raw).strip()
    try:
        value = coerce(definition, raw, allowed_options=())
    except ValidationFailedError as exc:
        raise ValidationFailedError(
            f"'{raw}' is not a valid value to filter '{definition.label}' by."
        ) from exc
    if value is None:
        raise ValidationFailedError(
            f"This filter on '{definition.label}' needs a value. "
            "Use is_empty to look for records without one."
        )
    return value


__all__ = [
    "FILTER_PREFIX",
    "FilterOperator",
    "custom_field_filter",
    "sort_column",
    "typed_value",
]
