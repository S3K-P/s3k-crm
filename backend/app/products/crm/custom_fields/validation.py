"""Coercion and validation of one custom value against its definition.

Pure functions over plain data — no session, no ORM, no I/O — so the rules can
be unit-tested exhaustively without a database, and so the same code validates
a submitted value, a configured default and an imported CSV cell.

**Coercion, then validation, in that order.** A client sends JSON, a CSV import
sends text, and a default is stored as text; all three have to arrive at the
same canonical shape before a bound or a pattern means anything. So each type
has a coercer that turns "what the caller sent" into "what is stored", and the
bounds are then checked against the coerced value.

**What is stored is JSON-native.** Numbers land as numbers, booleans as
booleans, dates as ISO-8601 strings, multi-picklists as arrays of strings.
Dates are strings rather than a JSON number because JSONB has no date type and
an ISO-8601 string sorts and compares correctly as text — which is what makes
``ORDER BY custom_fields->>'renewal_date'`` a real ordering rather than a
coincidence.

**Empty means absent.** ``None``, ``""`` and ``[]`` all clear the field: they
are what a form sends when a user empties an input, and storing three different
spellings of "nothing" would make every downstream comparison wrong in a
different way. A cleared required field is a 422, which is the same answer as
never having supplied it.
"""

from __future__ import annotations

import datetime as dt
import decimal
import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.core.exceptions import ValidationFailedError
from app.products.crm.custom_fields.models import (
    MAX_VALUE_LENGTH,
    CustomFieldDefinition,
    CustomFieldType,
)

#: Deliberately permissive: this is a CRM field, not an address the product
#: will attempt delivery to, and rejecting a legitimate address a customer
#: actually uses is the worse failure. Structure only — a local part, an ``@``,
#: a dotted domain, no whitespace.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: http/https only. A ``javascript:`` or ``data:`` URL stored in a field the UI
#: renders as a link is a stored-XSS vector, and no CRM field has a legitimate
#: reason to hold one.
_URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)

#: Digits, with the punctuation phone numbers are actually written with.
_PHONE_RE = re.compile(r"^[+()\-.\s\d]{4,32}$")

#: Accepted spellings of a boolean, because a CSV cell says "true" and a JSON
#: body says ``true``.
_TRUE = frozenset({"true", "t", "yes", "y", "1", "on"})
_FALSE = frozenset({"false", "f", "no", "n", "0", "off"})

#: Longest pattern an administrator may configure, and the longest input it is
#: run against. Both bound the work a pathological regex can do: Python's `re`
#: backtracks, so an unbounded pattern over an unbounded string is a CPU
#: denial-of-service that one administrator could inflict on their own tenant.
MAX_PATTERN_LENGTH = 255
MAX_PATTERN_INPUT = 4_096


class CustomFieldValueError(ValidationFailedError):
    """A submitted custom value does not satisfy its definition."""

    code = "custom_field_invalid"

    def __init__(self, api_name: str, reason: str) -> None:
        super().__init__(
            f"{api_name}: {reason}",
            details={"field": api_name, "reason": reason},
        )


def is_empty(value: Any) -> bool:
    """Whether ``value`` means "no value", in any of its spellings."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return isinstance(value, list | tuple | set) and not value


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Compile an administrator-supplied pattern, or raise.

    Called at *definition* time so an uncompilable pattern is a 422 on the
    admin screen rather than a 500 on every subsequent record write.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ValidationFailedError(
            f"A validation pattern may be at most {MAX_PATTERN_LENGTH} characters."
        )
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValidationFailedError(f"Not a valid regular expression: {exc}") from exc


def coerce(
    definition: CustomFieldDefinition,
    value: Any,
    *,
    allowed_options: Sequence[str] | None = None,
) -> Any:
    """Return the storable form of ``value``, or raise :class:`CustomFieldValueError`.

    Args:
        definition: the field the value is being written to.
        value: whatever the caller supplied — JSON scalar, list, or text.
        allowed_options: for a picklist type, the option values a *new* value
            may be chosen from. ``None`` for every other type. The caller
            resolves it because it needs a session and this module has none;
            passing it explicitly is also what lets the "already stored"
            exemption be decided by the caller rather than guessed here.

    Returns:
        A JSON-native value, or ``None`` meaning "the field is cleared".
    """
    api_name = definition.api_name
    if is_empty(value):
        return None

    field_type = definition.field_type
    coerced = _COERCERS[field_type](api_name, value, allowed_options or ())
    _check_bounds(definition, coerced)
    return coerced


# ---------------------------------------------------------------------------
# Per-type coercion
# ---------------------------------------------------------------------------


def _as_text(api_name: str, value: Any, _options: Sequence[str]) -> str:
    if isinstance(value, bool) or not isinstance(value, str | int | float | decimal.Decimal):
        raise CustomFieldValueError(api_name, "expected text.")
    text = str(value).strip()
    if len(text) > MAX_VALUE_LENGTH:
        raise CustomFieldValueError(
            api_name, f"is longer than the {MAX_VALUE_LENGTH:,} character limit."
        )
    return text


def _as_integer(api_name: str, value: Any, _options: Sequence[str]) -> int:
    if isinstance(value, bool):
        raise CustomFieldValueError(api_name, "expected a whole number.")
    if isinstance(value, int):
        return value
    try:
        number = decimal.Decimal(str(value).strip())
    except (decimal.InvalidOperation, ValueError) as exc:
        raise CustomFieldValueError(api_name, "expected a whole number.") from exc
    if number != number.to_integral_value():
        raise CustomFieldValueError(api_name, "expected a whole number, not a decimal.")
    return int(number)


def _as_decimal(api_name: str, value: Any, _options: Sequence[str]) -> float:
    if isinstance(value, bool):
        raise CustomFieldValueError(api_name, "expected a number.")
    try:
        number = decimal.Decimal(str(value).strip())
    except (decimal.InvalidOperation, ValueError) as exc:
        raise CustomFieldValueError(api_name, "expected a number.") from exc
    if not number.is_finite():
        raise CustomFieldValueError(api_name, "expected a finite number.")
    # Stored as a JSON number so it compares numerically after the cast in
    # `filters.py`. `float` is what JSONB would hold in any case — JSON has one
    # numeric type — so converting here rather than at serialization keeps the
    # stored value and the validated value identical.
    return float(number)


def _as_boolean(api_name: str, value: Any, _options: Sequence[str]) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise CustomFieldValueError(api_name, "expected true or false.")


def _as_date(api_name: str, value: Any, _options: Sequence[str]) -> str:
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value).strip()
    try:
        # `fromisoformat` accepts a full timestamp too, which is what a date
        # picker sends when it is configured for a datetime elsewhere on the
        # same form. Taking the date part is friendlier than refusing it, and
        # unambiguous: the caller told us the field is a DATE.
        return dt.date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise CustomFieldValueError(api_name, "expected a date as YYYY-MM-DD.") from exc


def _as_datetime(api_name: str, value: Any, _options: Sequence[str]) -> str:
    if isinstance(value, dt.datetime):
        moment = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            moment = dt.datetime.fromisoformat(text)
        except ValueError as exc:
            raise CustomFieldValueError(
                api_name, "expected a date and time in ISO-8601 format."
            ) from exc
    # Normalized to UTC before storage, so two records written from two
    # timezones compare and sort against each other correctly. A naive value is
    # read as UTC rather than as the server's zone: the server's zone is an
    # accident of deployment and would make the same request mean different
    # instants on different hosts.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return moment.astimezone(dt.UTC).isoformat()


def _as_email(api_name: str, value: Any, options: Sequence[str]) -> str:
    text = _as_text(api_name, value, options)
    if not _EMAIL_RE.match(text):
        raise CustomFieldValueError(api_name, "is not a valid email address.")
    return text.lower()


def _as_url(api_name: str, value: Any, options: Sequence[str]) -> str:
    text = _as_text(api_name, value, options)
    if not _URL_RE.match(text):
        raise CustomFieldValueError(api_name, "must be an http:// or https:// URL.")
    return text


def _as_phone(api_name: str, value: Any, options: Sequence[str]) -> str:
    text = _as_text(api_name, value, options)
    if not _PHONE_RE.match(text):
        raise CustomFieldValueError(api_name, "is not a valid phone number.")
    return text


def _as_option(api_name: str, value: Any, options: Sequence[str]) -> str:
    text = _as_text(api_name, value, options)
    if text not in options:
        raise CustomFieldValueError(api_name, "is not one of the available options.")
    return text


def _as_options(api_name: str, value: Any, options: Sequence[str]) -> list[str]:
    raw = value if isinstance(value, list | tuple | set) else [value]
    chosen: list[str] = []
    for item in raw:
        if is_empty(item):
            continue
        text = _as_option(api_name, item, options)
        # De-duplicated, order preserved. A repeated option is a UI artefact,
        # not a statement that the record holds it twice.
        if text not in chosen:
            chosen.append(text)
    # Sorted so two records holding the same set compare equal as JSONB and a
    # containment filter has one shape to match. The user's click order carries
    # no meaning the product ever reads back.
    return sorted(chosen)


_COERCERS: Mapping[CustomFieldType, Any] = {
    CustomFieldType.TEXT: _as_text,
    CustomFieldType.TEXTAREA: _as_text,
    CustomFieldType.NUMBER: _as_integer,
    CustomFieldType.DECIMAL: _as_decimal,
    CustomFieldType.DATE: _as_date,
    CustomFieldType.DATETIME: _as_datetime,
    CustomFieldType.BOOLEAN: _as_boolean,
    CustomFieldType.EMAIL: _as_email,
    CustomFieldType.URL: _as_url,
    CustomFieldType.PHONE: _as_phone,
    CustomFieldType.PICKLIST: _as_option,
    CustomFieldType.MULTI_PICKLIST: _as_options,
}


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


def _check_bounds(definition: CustomFieldDefinition, value: Any) -> None:
    """Apply the definition's configured length, range and pattern rules."""
    api_name = definition.api_name

    if isinstance(value, int | float) and not isinstance(value, bool):
        if definition.min_value is not None and decimal.Decimal(str(value)) < decimal.Decimal(
            str(definition.min_value)
        ):
            raise CustomFieldValueError(api_name, f"must be at least {definition.min_value}.")
        if definition.max_value is not None and decimal.Decimal(str(value)) > decimal.Decimal(
            str(definition.max_value)
        ):
            raise CustomFieldValueError(api_name, f"must be at most {definition.max_value}.")

    if isinstance(value, str):
        if definition.min_length is not None and len(value) < definition.min_length:
            raise CustomFieldValueError(
                api_name, f"must be at least {definition.min_length} characters."
            )
        if definition.max_length is not None and len(value) > definition.max_length:
            raise CustomFieldValueError(
                api_name, f"must be at most {definition.max_length} characters."
            )
        if definition.pattern:
            if len(value) > MAX_PATTERN_INPUT:
                raise CustomFieldValueError(
                    api_name,
                    f"is too long to check against this field's format "
                    f"(limit {MAX_PATTERN_INPUT:,} characters).",
                )
            # `fullmatch`, not `match`: an administrator writing `\d{4}` means
            # "four digits", and a `match` would accept "1234abc".
            if not compile_pattern(definition.pattern).fullmatch(value):
                raise CustomFieldValueError(api_name, "does not match the required format.")


__all__ = [
    "MAX_PATTERN_INPUT",
    "MAX_PATTERN_LENGTH",
    "CustomFieldValueError",
    "coerce",
    "compile_pattern",
    "is_empty",
]
