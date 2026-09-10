"""Coercion and bounds for one custom value, without a database.

These are the rules a record write is subject to, and they are pure functions
over a definition and a value — so they are exercised here exhaustively, per
type, rather than through an HTTP round trip per case.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.exceptions import ValidationFailedError
from app.products.crm.common import CrmEntityType
from app.products.crm.custom_fields.models import CustomFieldDefinition, CustomFieldType
from app.products.crm.custom_fields.validation import (
    MAX_PATTERN_LENGTH,
    CustomFieldValueError,
    coerce,
    compile_pattern,
    is_empty,
)
from app.products.crm.shared.schemas import MAX_CUSTOM_FIELD_VALUES


def definition(field_type: CustomFieldType, **overrides: object) -> CustomFieldDefinition:
    """An unsaved definition. Nothing here touches a session."""
    values: dict[str, object] = {
        "organization_id": uuid.uuid4(),
        "entity_type": CrmEntityType.LEAD,
        "api_name": "field",
        "label": "Field",
        "field_type": field_type,
        "is_required": False,
        "is_active": True,
        "position": 0,
        "default_value": None,
        "picklist_id": uuid.uuid4() if "PICKLIST" in field_type.value else None,
        "min_value": None,
        "max_value": None,
        "min_length": None,
        "max_length": None,
        "pattern": None,
    }
    values.update(overrides)
    return CustomFieldDefinition(**values)  # type: ignore[arg-type]


# --- Emptiness -------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   ", [], (), set()])
def test_every_spelling_of_nothing_is_empty(value: object) -> None:
    """A form sends several shapes for "the user cleared this"; all mean one thing."""
    assert is_empty(value)


@pytest.mark.parametrize("value", [0, False, "0", ["a"], "x"])
def test_falsey_but_present_values_are_not_empty(value: object) -> None:
    """``0`` and ``False`` are answers, not the absence of one.

    The bug this guards against is a truthiness check: it would silently
    discard every zero and every "no" a user ever entered.
    """
    assert not is_empty(value)


def test_an_empty_value_clears_the_field() -> None:
    assert coerce(definition(CustomFieldType.TEXT), "") is None


# --- Per-type coercion -----------------------------------------------------


@pytest.mark.parametrize(
    ("field_type", "given", "expected"),
    [
        (CustomFieldType.TEXT, "  Acme  ", "Acme"),
        (CustomFieldType.TEXTAREA, "line\nline", "line\nline"),
        (CustomFieldType.NUMBER, "42", 42),
        (CustomFieldType.NUMBER, 42, 42),
        (CustomFieldType.NUMBER, "-7", -7),
        (CustomFieldType.DECIMAL, "3.5", 3.5),
        (CustomFieldType.DECIMAL, 3, 3.0),
        (CustomFieldType.BOOLEAN, "yes", True),
        (CustomFieldType.BOOLEAN, "FALSE", False),
        (CustomFieldType.BOOLEAN, True, True),
        (CustomFieldType.DATE, "2026-03-04", "2026-03-04"),
        (CustomFieldType.DATE, dt.date(2026, 3, 4), "2026-03-04"),
        (CustomFieldType.EMAIL, "  Ravi@Zephyr.Example ", "ravi@zephyr.example"),
        (CustomFieldType.URL, "https://example.com/x", "https://example.com/x"),
        (CustomFieldType.PHONE, "+44 (0)20 7946 0000", "+44 (0)20 7946 0000"),
    ],
)
def test_a_value_is_coerced_to_its_stored_shape(
    field_type: CustomFieldType, given: object, expected: object
) -> None:
    assert coerce(definition(field_type), given) == expected


@pytest.mark.parametrize(
    ("field_type", "given"),
    [
        (CustomFieldType.NUMBER, "4.5"),
        (CustomFieldType.NUMBER, "abc"),
        (CustomFieldType.NUMBER, True),
        (CustomFieldType.DECIMAL, "NaN"),
        (CustomFieldType.DECIMAL, "Infinity"),
        (CustomFieldType.BOOLEAN, "perhaps"),
        (CustomFieldType.DATE, "04/03/2026"),
        (CustomFieldType.DATETIME, "not a time"),
        (CustomFieldType.EMAIL, "ravi@zephyr"),
        (CustomFieldType.EMAIL, "no-at-sign.example"),
        (CustomFieldType.URL, "javascript:alert(1)"),
        (CustomFieldType.URL, "ftp://example.com"),
        (CustomFieldType.PHONE, "call me maybe"),
    ],
)
def test_a_value_of_the_wrong_shape_is_refused(
    field_type: CustomFieldType, given: object
) -> None:
    with pytest.raises(CustomFieldValueError):
        coerce(definition(field_type), given)


def test_a_javascript_url_is_refused() -> None:
    """A URL field's value is rendered as a link; ``javascript:`` is stored XSS."""
    with pytest.raises(CustomFieldValueError):
        coerce(definition(CustomFieldType.URL), "javascript:fetch('//evil')")


def test_a_datetime_is_normalized_to_utc() -> None:
    """Two timezones must produce comparable stored values, or sorting is a lie."""
    stored = coerce(definition(CustomFieldType.DATETIME), "2026-03-04T12:00:00+05:30")
    assert stored is not None
    assert dt.datetime.fromisoformat(str(stored)) == dt.datetime(
        2026, 3, 4, 6, 30, tzinfo=dt.UTC
    )


def test_a_naive_datetime_is_read_as_utc_not_as_the_servers_zone() -> None:
    """The server's zone is an accident of deployment and must not change meaning."""
    stored = coerce(definition(CustomFieldType.DATETIME), "2026-03-04T12:00:00")
    assert stored is not None
    assert dt.datetime.fromisoformat(str(stored)).tzinfo == dt.UTC
    assert str(stored).startswith("2026-03-04T12:00:00")


# --- Picklists -------------------------------------------------------------


def test_a_picklist_accepts_only_an_offered_option() -> None:
    field = definition(CustomFieldType.PICKLIST)
    assert coerce(field, "EMEA", allowed_options=["EMEA", "APAC"]) == "EMEA"
    with pytest.raises(CustomFieldValueError):
        coerce(field, "LATAM", allowed_options=["EMEA", "APAC"])


def test_a_multi_picklist_stores_a_sorted_deduplicated_set() -> None:
    """Order carries no meaning the product reads back, and duplicates are UI noise."""
    field = definition(CustomFieldType.MULTI_PICKLIST)
    assert coerce(
        field, ["APAC", "EMEA", "APAC"], allowed_options=["EMEA", "APAC"]
    ) == ["APAC", "EMEA"]


def test_a_multi_picklist_accepts_a_single_value() -> None:
    field = definition(CustomFieldType.MULTI_PICKLIST)
    assert coerce(field, "EMEA", allowed_options=["EMEA"]) == ["EMEA"]


def test_a_multi_picklist_of_only_blanks_clears_the_field() -> None:
    field = definition(CustomFieldType.MULTI_PICKLIST)
    assert coerce(field, ["", "  "], allowed_options=["EMEA"]) == []


# --- Bounds ----------------------------------------------------------------


def test_a_number_below_its_minimum_is_refused() -> None:
    field = definition(CustomFieldType.NUMBER, min_value=10, max_value=20)
    assert coerce(field, 15) == 15
    with pytest.raises(CustomFieldValueError):
        coerce(field, 9)
    with pytest.raises(CustomFieldValueError):
        coerce(field, 21)


def test_text_length_bounds_apply() -> None:
    field = definition(CustomFieldType.TEXT, min_length=3, max_length=5)
    assert coerce(field, "abcd") == "abcd"
    with pytest.raises(CustomFieldValueError):
        coerce(field, "ab")
    with pytest.raises(CustomFieldValueError):
        coerce(field, "abcdef")


def test_a_pattern_must_match_the_whole_value() -> None:
    """``fullmatch``: ``\\d{4}`` means four digits, not "starts with four digits"."""
    field = definition(CustomFieldType.TEXT, pattern=r"[A-Z]{2}\d{4}")
    assert coerce(field, "AB1234") == "AB1234"
    with pytest.raises(CustomFieldValueError):
        coerce(field, "AB1234-extra")


def test_an_uncompilable_pattern_is_refused_at_definition_time() -> None:
    """So it is a 422 on the admin screen, not a 500 on every later record write."""
    with pytest.raises(ValidationFailedError):
        compile_pattern("[unterminated")


def test_an_over_long_pattern_is_refused() -> None:
    with pytest.raises(ValidationFailedError):
        compile_pattern("a" * (MAX_PATTERN_LENGTH + 1))


# --- Cross-module agreement ------------------------------------------------


def test_the_request_cap_matches_the_per_entity_field_limit() -> None:
    """``shared.schemas`` restates the limit to avoid a boundary-crossing import.

    Restating it is only safe if the two cannot drift, which is what this
    asserts. If the field limit moves, this fails and names the other constant.
    """
    from app.products.crm.custom_fields.models import MAX_FIELDS_PER_ENTITY

    assert MAX_CUSTOM_FIELD_VALUES == MAX_FIELDS_PER_ENTITY
