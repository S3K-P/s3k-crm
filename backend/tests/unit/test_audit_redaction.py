"""What must never reach ``audit_logs.details``, and what must.

An audit trail is written from the middle of sensitive operations — a password
change, a token rotation, a member edit — so the values in scope at the call
site are exactly the ones that must not be copied into a permanent, immutable,
admin-readable table. :mod:`app.platform.audit.redaction` is the single filter
standing between the two, which makes it worth testing from both directions:

* the negative cases, that a credential cannot survive the trip; and
* the positive cases, that redaction did not just empty the payload — a record
  that says nothing about what changed is not evidence either.

These run with no database: redaction is a pure function over a mapping, and
that is the point of it being one.
"""

from __future__ import annotations

import datetime as dt
import decimal
import enum
import uuid

import pytest

from app.platform.audit.redaction import (
    MAX_DEPTH,
    MAX_ITEMS,
    MAX_STRING_LENGTH,
    REDACTED,
    diff,
    is_pii_key,
    is_secret_key,
    mask_email,
    mask_phone,
    redact,
)

# --- Secrets ----------------------------------------------------------------

#: Every spelling a caller might plausibly hand the audit service. Each must be
#: recognised by *substring*, because the real payloads are things like
#: ``new_password_confirmation`` and ``refresh_token_hash``, not ``password``.
SECRET_KEYS = [
    "password",
    "new_password",
    "current_password",
    "new_password_confirmation",
    "password_hash",
    "PASSWORD",
    "access_token",
    "refresh_token",
    "refresh_token_hash",
    "api_key",
    "apiKey",
    "client_secret",
    "authorization",
    "Cookie",
    "private_key",
    "signature",
    "otp",
    "cvv",
    "card_number",
    "ssn",
]


@pytest.mark.parametrize("key", SECRET_KEYS)
def test_a_key_that_names_a_credential_is_never_stored(key: str) -> None:
    result = redact({key: "Str0ngPassphrase!"})

    assert result == {key: REDACTED}
    assert "Str0ngPassphrase!" not in str(result)


@pytest.mark.parametrize("key", SECRET_KEYS)
def test_the_same_keys_are_recognised_by_the_predicate(key: str) -> None:
    """The predicate and the redaction must agree, or one of them is decoration."""
    assert is_secret_key(key)


def test_a_credential_nested_inside_a_structure_is_still_removed() -> None:
    """The realistic shape: a request body echoed into ``details`` wholesale."""
    result = redact(
        {
            "request": {
                "user": {"email": "admin@acme.example", "password": "hunter2hunter2"},
                "tokens": [{"refresh_token": "rt_live_abcdef"}],
            }
        }
    )

    flattened = str(result)
    assert "hunter2hunter2" not in flattened
    assert "rt_live_abcdef" not in flattened


def test_a_secret_change_records_that_it_happened_and_nothing_else() -> None:
    """A password rotation must be auditable *as an event* without the values."""
    changes = diff({"password_hash": "argon2$old"}, {"password_hash": "argon2$new"})

    assert changes == {"password_hash": {"from": REDACTED, "to": REDACTED}}


def test_raw_bytes_are_never_stored() -> None:
    """A key, a certificate or a file chunk has no business in the trail."""
    assert redact({"payload": b"\x00binary"}) == {"payload": REDACTED}


# --- PII --------------------------------------------------------------------


def test_an_email_is_masked_but_its_domain_survives() -> None:
    """Doc 13 classifies email as PII to be masked in audit logs.

    The domain is kept deliberately: telling a corporate address from a
    personal one, or spotting a supplier domain, is most of what makes a trail
    usable, and it does not identify the person.
    """
    assert mask_email("jordan.blake@acme.example") == "j***@acme.example"


def test_a_phone_number_keeps_only_its_last_four_digits() -> None:
    assert mask_phone("+91 98765 43210") == "***3210"


def test_a_phone_too_short_to_mask_is_dropped_entirely() -> None:
    """Failing closed: if it cannot be masked it is not stored."""
    assert mask_phone("12") == REDACTED


@pytest.mark.parametrize("key", ["email", "work_email", "phone", "mobile"])
def test_contact_fields_are_masked_by_key(key: str) -> None:
    assert is_pii_key(key)
    (value,) = redact({key: "jordan.blake@acme.example"}).values()
    assert value == "j***@acme.example"


def test_an_address_is_masked_even_under_a_key_that_does_not_say_email() -> None:
    """Shape-based masking, so a contact detail in a neutrally named field is
    not stored in full just because nobody named the field ``email``."""
    assert redact({"identifier": "jordan.blake@acme.example"}) == {
        "identifier": "j***@acme.example"
    }


# --- What must survive ------------------------------------------------------


def test_ordinary_business_values_are_kept_verbatim() -> None:
    """The counterweight: over-redaction produces a useless trail.

    A record that only ever says "[redacted]" cannot answer what changed, which
    is the question the table exists for.
    """
    result = redact(
        {
            "name": "Northwind Traders",
            "status": "ACTIVE",
            "annual_revenue": 42,
            "is_default": True,
            "owner_id": None,
        }
    )

    assert result == {
        "name": "Northwind Traders",
        "status": "ACTIVE",
        "annual_revenue": 42,
        "is_default": True,
        "owner_id": None,
    }


def test_values_are_coerced_into_shapes_jsonb_accepts() -> None:
    """``details`` is JSONB, and the callers hand it ORM values."""

    class Status(enum.StrEnum):
        ACTIVE = "ACTIVE"

    identifier = uuid.uuid4()
    moment = dt.datetime(2026, 8, 21, 9, 30, tzinfo=dt.UTC)

    result = redact(
        {
            "id": identifier,
            "at": moment,
            "status": Status.ACTIVE,
            "amount": decimal.Decimal("1250.75"),
        }
    )

    assert result == {
        "id": str(identifier),
        "at": moment.isoformat(),
        "status": "ACTIVE",
        # A string, not a float: a monetary amount must not acquire binary
        # rounding error on its way into the record of what it became.
        "amount": "1250.75",
    }


def test_a_diff_records_both_sides_of_a_change() -> None:
    """"Changed to X" is half a story when the question is who changed it from Y."""
    changes = diff({"status": "NEW", "name": "Acme"}, {"status": "QUALIFIED", "name": "Acme"})

    assert changes == {"status": {"from": "NEW", "to": "QUALIFIED"}}


def test_a_diff_of_identical_values_is_empty() -> None:
    """A PATCH that re-sends what was already stored is not an event.

    ``AuditService.record_change`` writes nothing at all in this case, so this
    is what stops a save button producing a row every time it is pressed.
    """
    assert diff({"status": "NEW"}, {"status": "NEW"}) == {}


def test_a_diff_masks_pii_on_both_sides() -> None:
    changes = diff(
        {"email": "old.address@acme.example"}, {"email": "new.address@acme.example"}
    )

    assert changes == {
        "email": {"from": "o***@acme.example", "to": "n***@acme.example"}
    }


# --- Bounds -----------------------------------------------------------------


def test_a_long_string_is_truncated() -> None:
    """One audited action must never become an unbounded write."""
    (value,) = redact({"note": "x" * (MAX_STRING_LENGTH * 3)}).values()

    assert isinstance(value, str)
    assert len(value) == MAX_STRING_LENGTH + 1  # the ellipsis


def test_an_oversized_mapping_is_capped() -> None:
    result = redact({f"field_{index}": index for index in range(MAX_ITEMS * 3)})

    assert len(result) == MAX_ITEMS


def test_an_oversized_list_is_capped() -> None:
    (value,) = redact({"items": list(range(MAX_ITEMS * 3))}).values()

    assert isinstance(value, list)
    assert len(value) == MAX_ITEMS


def test_deep_nesting_stops_rather_than_recursing_without_limit() -> None:
    payload: dict[str, object] = {"leaf": "bottom"}
    for _ in range(MAX_DEPTH * 3):
        payload = {"nested": payload}

    result = redact(payload)

    assert "[truncated]" in str(result)


def test_redaction_never_mutates_what_it_was_given() -> None:
    """The caller keeps working with its own values after auditing."""
    original = {"password": "hunter2hunter2", "name": "Acme"}

    redact(original)

    assert original == {"password": "hunter2hunter2", "name": "Acme"}


def test_none_is_passed_through_rather_than_becoming_an_empty_object() -> None:
    """``details`` is nullable; "no detail" and "empty detail" differ."""
    assert redact(None) is None
