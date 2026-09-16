"""The condition tree a custom report's (or an advanced list filter's) WHERE
clause is built from, and the one function that turns it into SQL.

**Why a closed operator vocabulary rather than accepting an expression.** The
custom-report engine and the advanced-filter query parameter both let a
caller describe a comparison. The only way that can stay safe is if
"describe" means "pick a member of a fixed enum and supply a value" rather
than "supply anything a query planner could evaluate" — the same shape
:mod:`app.products.crm.custom_fields.filters` already established for
tenant-defined fields, extended here to the small set of extra operators a
report additionally wants (``starts_with``, ``ends_with``, ``between``) and
to built-in, natively-typed columns rather than a JSONB document.

**Relative dates reuse the saved-report library's own period vocabulary.**
A date condition's value may be a literal ISO date/datetime, or
``{"relative": "THIS_QUARTER"}`` naming a
:class:`~app.products.crm.reports.models.ReportPeriod` member — resolved
through the *exact* function (:func:`~app.products.crm.reports.library.resolve_period`)
a saved report's own stored period already goes through, so "this quarter"
means the same calendar window whether it comes from a saved report's period
picker or a condition inside a filter group. No second definition of what
"this quarter" means exists anywhere in the codebase after this module.

**Grouping is one level: one logic operator (AND or OR) over a flat list of
conditions.** Not a recursive tree of nested groups. That is deliberately the
same shape :mod:`app.products.crm.layouts.evaluate` gives a layout rule
(``logic`` + ``conditions``), which shipped, was tested, and has not needed
more. A report wanting "(A or B) and C" is two separate, real limitations —
document them rather than build a general boolean-expression parser to avoid
writing that sentence.
"""

from __future__ import annotations

import datetime as dt
import enum
from typing import Any, Literal
from typing import cast as narrow  # `cast` is SQLAlchemy's SQL CAST, below

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, and_, func, or_
from sqlalchemy import Date as SaDate
from sqlalchemy import cast as sa_cast

from app.core.exceptions import ValidationFailedError
from app.products.crm.custom_fields.filters import (
    FilterOperator as CustomFieldFilterOperator,
)
from app.products.crm.custom_fields.filters import (
    custom_field_filter,
)
from app.products.crm.custom_fields.models import CustomFieldDefinition
from app.products.crm.reports.catalog import ColumnType
from app.products.crm.reports.fields import ReportField
from app.products.crm.reports.models import ReportPeriod


class ReportFilterOperator(enum.StrEnum):
    """Comparisons a report or advanced-filter condition may make."""

    EQ = "eq"
    NE = "ne"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    IN = "in"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"


_TEXT_ONLY = (
    ReportFilterOperator.CONTAINS,
    ReportFilterOperator.STARTS_WITH,
    ReportFilterOperator.ENDS_WITH,
)
_ORDERED = (
    ReportFilterOperator.GT,
    ReportFilterOperator.GTE,
    ReportFilterOperator.LT,
    ReportFilterOperator.LTE,
    ReportFilterOperator.BETWEEN,
)
_PRESENCE = (ReportFilterOperator.IS_EMPTY, ReportFilterOperator.IS_NOT_EMPTY)
_EQUALITY = (ReportFilterOperator.EQ, ReportFilterOperator.NE, ReportFilterOperator.IN)

#: Operators legal per output column type. A ``between`` on a status column or
#: a ``contains`` on a currency figure is a request with no meaning.
ALLOWED_OPERATORS: dict[ColumnType, frozenset[ReportFilterOperator]] = {
    ColumnType.TEXT: frozenset({*_EQUALITY, *_TEXT_ONLY, *_PRESENCE}),
    ColumnType.STATUS: frozenset({*_EQUALITY, *_PRESENCE}),
    ColumnType.PERSON: frozenset({*_EQUALITY, *_PRESENCE}),
    ColumnType.NUMBER: frozenset({*_EQUALITY, *_ORDERED, *_PRESENCE}),
    ColumnType.CURRENCY: frozenset({*_EQUALITY, *_ORDERED, *_PRESENCE}),
    ColumnType.PERCENT: frozenset({*_EQUALITY, *_ORDERED, *_PRESENCE}),
    ColumnType.DATE: frozenset({*_EQUALITY, *_ORDERED, *_PRESENCE}),
}

_CUSTOM_FIELD_OPERATOR_MAP: dict[ReportFilterOperator, CustomFieldFilterOperator] = {
    ReportFilterOperator.EQ: CustomFieldFilterOperator.EQ,
    ReportFilterOperator.NE: CustomFieldFilterOperator.NE,
    ReportFilterOperator.CONTAINS: CustomFieldFilterOperator.CONTAINS,
    ReportFilterOperator.GT: CustomFieldFilterOperator.GT,
    ReportFilterOperator.GTE: CustomFieldFilterOperator.GTE,
    ReportFilterOperator.LT: CustomFieldFilterOperator.LT,
    ReportFilterOperator.LTE: CustomFieldFilterOperator.LTE,
    ReportFilterOperator.IN: CustomFieldFilterOperator.IN,
    ReportFilterOperator.IS_EMPTY: CustomFieldFilterOperator.IS_EMPTY,
    ReportFilterOperator.IS_NOT_EMPTY: CustomFieldFilterOperator.IS_NOT_EMPTY,
}


class ReportCondition(BaseModel):
    """One comparison. ``field`` is a registry key, or ``custom:<api_name>``."""

    field: str = Field(min_length=1, max_length=80)
    operator: ReportFilterOperator
    #: A scalar, a two-item list (``between``), a list (``in``), or
    #: ``{"relative": "<ReportPeriod member>"}`` for a date field.
    value: Any = None


class ReportFilterGroup(BaseModel):
    logic: Literal["AND", "OR"] = "AND"
    conditions: list[ReportCondition] = Field(default_factory=list, max_length=20)


def _relative_bounds(
    token: str, *, today: dt.date
) -> tuple[dt.date | None, dt.date | None]:
    try:
        period = ReportPeriod(token)
    except ValueError as exc:
        msg = f"'{token}' is not a recognised relative period."
        raise ValidationFailedError(msg) from exc
    # Imported here rather than at module scope: `library.py` imports
    # `catalog`, and `conditions.py` is imported by `custom.py`, which
    # `library.py` will import — a module-level import back into `library`
    # would be a cycle. `resolve_period` is a pure function with no service
    # dependency of its own, so a local import costs nothing but the cycle.
    from app.products.crm.reports.library import resolve_period

    return resolve_period(period, date_from=None, date_to=None, today=today)


def _as_date(value: Any) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        msg = f"'{value}' is not a date."
        raise ValidationFailedError(msg) from exc


def _as_number(value: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        msg = f"'{value}' is not a number."
        raise ValidationFailedError(msg) from exc


def _typed(field: ReportField, value: Any) -> Any:
    if field.type in (ColumnType.NUMBER, ColumnType.CURRENCY, ColumnType.PERCENT):
        return _as_number(value)
    if field.type is ColumnType.DATE:
        return _as_date(value)
    return value


def _build_builtin_condition(
    field: ReportField, condition: ReportCondition, *, today: dt.date
) -> ColumnElement[bool]:
    allowed = ALLOWED_OPERATORS.get(field.type, frozenset())
    if condition.operator not in allowed:
        msg = (
            f"'{condition.operator.value}' does not apply to '{field.label}'. "
            f"Available: {', '.join(op.value for op in sorted(allowed, key=str))}."
        )
        raise ValidationFailedError(msg)

    column = field.column

    if condition.operator is ReportFilterOperator.IS_EMPTY:
        return column.is_(None)
    if condition.operator is ReportFilterOperator.IS_NOT_EMPTY:
        return column.is_not(None)

    # A relative-date value replaces the single condition with a bounds
    # check, whatever comparison operator named it — see the module
    # docstring. Only meaningful for date-typed fields.
    if (
        field.type is ColumnType.DATE
        and isinstance(condition.value, dict)
        and "relative" in condition.value
    ):
        start, end = _relative_bounds(str(condition.value["relative"]), today=today)
        clauses: list[ColumnElement[bool]] = []
        if condition.operator in (ReportFilterOperator.EQ, ReportFilterOperator.BETWEEN):
            if start is not None:
                clauses.append(sa_cast(column, SaDate) >= start)
            if end is not None:
                clauses.append(sa_cast(column, SaDate) <= end)
        elif condition.operator in (ReportFilterOperator.GTE, ReportFilterOperator.GT):
            if start is not None:
                clauses.append(sa_cast(column, SaDate) >= start)
        elif condition.operator in (ReportFilterOperator.LTE, ReportFilterOperator.LT):
            if end is not None:
                clauses.append(sa_cast(column, SaDate) <= end)
        else:
            msg = f"'{condition.operator.value}' does not accept a relative period."
            raise ValidationFailedError(msg)
        return and_(*clauses) if clauses else column.is_not(None)

    if condition.operator is ReportFilterOperator.CONTAINS:
        needle = str(condition.value).strip()
        if not needle:
            raise ValidationFailedError("A 'contains' filter needs something to look for.")
        return func.lower(column).like(func.concat("%", func.lower(needle), "%"))
    if condition.operator is ReportFilterOperator.STARTS_WITH:
        needle = str(condition.value).strip()
        if not needle:
            raise ValidationFailedError("A 'starts with' filter needs something to look for.")
        return func.lower(column).like(func.concat(func.lower(needle), "%"))
    if condition.operator is ReportFilterOperator.ENDS_WITH:
        needle = str(condition.value).strip()
        if not needle:
            raise ValidationFailedError("An 'ends with' filter needs something to look for.")
        return func.lower(column).like(func.concat("%", func.lower(needle)))

    if condition.operator is ReportFilterOperator.IN:
        values = condition.value if isinstance(condition.value, list) else [condition.value]
        if not values:
            raise ValidationFailedError("An 'in' filter needs at least one value.")
        return column.in_([_typed(field, item) for item in values])

    if condition.operator is ReportFilterOperator.BETWEEN:
        if not isinstance(condition.value, list) or len(condition.value) != 2:
            raise ValidationFailedError("A 'between' filter needs exactly two values.")
        low, high = (_typed(field, item) for item in condition.value)
        return column.between(low, high)

    value = _typed(field, condition.value)
    # `column` is `ColumnElement[Any]` — its concrete type came from a
    # runtime-resolved `ReportField`, so every comparison below is `Any` to
    # the type checker, the same narrowing `custom_fields/filters.py` needs
    # for the identical reason. Narrowed once here rather than per branch.
    comparison: Any
    match condition.operator:
        case ReportFilterOperator.EQ:
            comparison = column == value
        case ReportFilterOperator.NE:
            comparison = column.is_distinct_from(value)
        case ReportFilterOperator.GT:
            comparison = column > value
        case ReportFilterOperator.GTE:
            comparison = column >= value
        case ReportFilterOperator.LT:
            comparison = column < value
        case _:
            comparison = column <= value
    return narrow("ColumnElement[bool]", comparison)


def build_condition(
    field: ReportField | None,
    condition: ReportCondition,
    *,
    today: dt.date,
    custom_definition: CustomFieldDefinition | None = None,
    custom_model: type[Any] | None = None,
) -> ColumnElement[bool]:
    """One condition's predicate, over a built-in or a custom field.

    ``field`` is required unless ``custom_definition``/``custom_model`` are
    given instead — see :mod:`.custom` for how the caller resolves a
    ``custom:`` key to a definition before reaching here.
    """
    if custom_definition is not None:
        if custom_model is None:  # pragma: no cover - programming error guard
            msg = "custom_model is required alongside custom_definition."
            raise ValueError(msg)
        mapped = _CUSTOM_FIELD_OPERATOR_MAP.get(condition.operator)
        if mapped is None:
            msg = f"'{condition.operator.value}' does not apply to a custom field."
            raise ValidationFailedError(msg)
        return custom_field_filter(custom_model, custom_definition, mapped, condition.value)
    if field is None:  # pragma: no cover - programming error guard
        msg = "field is required unless custom_definition is given."
        raise ValueError(msg)
    return _build_builtin_condition(field, condition, today=today)


def combine(
    predicates: list[ColumnElement[bool]], *, logic: Literal["AND", "OR"]
) -> ColumnElement[bool] | None:
    if not predicates:
        return None
    return and_(*predicates) if logic == "AND" else or_(*predicates)


__all__ = [
    "ALLOWED_OPERATORS",
    "ReportCondition",
    "ReportFilterGroup",
    "ReportFilterOperator",
    "build_condition",
    "combine",
]
