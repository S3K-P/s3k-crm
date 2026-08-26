"""Make an arbitrary payload safe to store in an audit record (P1-W08-BE-03).

An audit trail is written from wherever a sensitive action happens, and the
values in scope there are whatever the caller was handling — a password change
carries the password, a member update carries an email address, a token
rotation carries the token. Every one of those would otherwise be copied,
verbatim and permanently, into a table an administrator can read on screen.

So nothing reaches ``audit_logs.details`` without passing through
:func:`redact`. Three rules, in order:

1. **Secrets are removed by name.** A key that looks like a credential is
   replaced with a marker; the value never enters the structure at all. Matched
   on a substring of the key, so ``new_password_confirmation`` and
   ``refresh_token_hash`` are caught without enumerating every spelling.
2. **PII is masked by shape.** Doc 13 classifies email and phone as PII to be
   "masked in audit logs". A masked value still supports the question an
   auditor actually asks — *did this field change, and roughly to what* —
   without reproducing the contact details themselves.
3. **Everything else is coerced and bounded.** Values are made JSON-safe,
   long strings are truncated and the structure is depth- and width-limited,
   so no caller can turn one audited action into a megabyte of JSONB.

The redaction is deliberately conservative and one-way. It runs on the write
path, not the read path: a value that was never stored cannot leak later,
whereas a filter applied at display time protects nothing from anyone holding
a database connection.
"""

from __future__ import annotations

import datetime as dt
import decimal
import enum
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Final

#: Written in place of a value whose key names a credential.
REDACTED: Final = "[redacted]"

#: Substrings that mark a key as holding a secret. Compared against the
#: lower-cased key, so any key *containing* one of these is redacted.
#:
#: Erring towards over-redaction is intentional: a field wrongly redacted
#: costs an auditor one question, a field wrongly kept is a credential in a
#: table with a two-year retention policy.
SECRET_KEY_MARKERS: Final[tuple[str, ...]] = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "authorization",
    "auth_header",
    "cookie",
    "session_key",
    "salt",
    "hash",
    "signature",
    "otp",
    "mfa_code",
    "cvv",
    "card_number",
    "ssn",
    "tax_id",
    "aadhaar",
    "pan_number",
)

#: Keys whose values are masked rather than dropped, regardless of shape.
#: Catches a contact field that happens to hold something unparseable.
PII_KEY_MARKERS: Final[tuple[str, ...]] = (
    "email",
    "phone",
    "mobile",
    "contact_number",
)

#: Caps. A single audited action must never become an unbounded write.
MAX_STRING_LENGTH: Final = 500
MAX_ITEMS: Final = 50
MAX_DEPTH: Final = 4

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
#: Loose on purpose — international formats vary and this only decides whether
#: to mask, never whether to accept.
_PHONE = re.compile(r"^[+()\d][\d\s()+.-]{5,}$")


def is_secret_key(key: str) -> bool:
    """Whether a key names something that must never be stored."""
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def is_pii_key(key: str) -> bool:
    """Whether a key names contact detail that must be stored masked."""
    lowered = key.lower()
    return any(marker in lowered for marker in PII_KEY_MARKERS)


def mask_email(value: str) -> str:
    """``jordan.blake@acme.example`` -> ``j***@acme.example``.

    The domain survives because it is what makes a trail usable — telling a
    corporate address from a personal one, spotting a sign-in from a supplier
    domain — while the local part is the identifying half.
    """
    local, _, domain = value.partition("@")
    if not local or not domain:
        return REDACTED
    return f"{local[0]}***@{domain}"


def mask_phone(value: str) -> str:
    """Keep only the last four digits: ``+91 98765 43210`` -> ``***3210``."""
    digits = [character for character in value if character.isdigit()]
    if len(digits) < 4:
        return REDACTED
    return "***" + "".join(digits[-4:])


def mask_value(value: str) -> str:
    """Mask a string that looks like contact detail, else truncate it."""
    stripped = value.strip()
    if _EMAIL.match(stripped):
        return mask_email(stripped)
    if _PHONE.match(stripped):
        return mask_phone(stripped)
    return _truncate(stripped)


def _truncate(value: str) -> str:
    if len(value) <= MAX_STRING_LENGTH:
        return value
    return value[:MAX_STRING_LENGTH] + "…"


def _coerce_scalar(value: Any) -> Any:
    """Render a scalar in a form ``JSONB`` accepts and a human can read."""
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, enum.Enum):
        return _coerce_scalar(value.value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        # str, not float: a monetary amount must not acquire binary rounding
        # error on its way into the record of what it was changed to.
        return str(value)
    if isinstance(value, bytes):
        return REDACTED
    return _truncate(str(value))


def _redact_value(value: Any, *, depth: int, mask: bool) -> Any:
    """Redact one value, recursing into containers up to :data:`MAX_DEPTH`."""
    if depth > MAX_DEPTH:
        return "[truncated]"

    if isinstance(value, Mapping):
        return _redact_mapping(value, depth=depth)

    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        items = list(value)[:MAX_ITEMS]
        return [_redact_value(item, depth=depth + 1, mask=mask) for item in items]

    coerced = _coerce_scalar(value)
    if isinstance(coerced, str):
        # A string is masked when its key said so, and otherwise still checked
        # by shape: an address landing in a field called ``identifier`` is no
        # less an address for it.
        return mask_value(coerced) if mask else _mask_if_contact_shaped(coerced)
    return coerced


def _mask_if_contact_shaped(value: str) -> str:
    stripped = value.strip()
    if _EMAIL.match(stripped):
        return mask_email(stripped)
    return _truncate(value)


def _redact_mapping(payload: Mapping[Any, Any], *, depth: int) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for raw_key, value in list(payload.items())[:MAX_ITEMS]:
        key = _truncate(str(raw_key))
        if is_secret_key(key):
            redacted[key] = REDACTED
            continue
        redacted[key] = _redact_value(value, depth=depth + 1, mask=is_pii_key(key))
    return redacted


def redact(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return ``payload`` made safe and JSON-serialisable, or ``None``.

    Args:
        payload: arbitrary detail a caller wants recorded.

    Returns:
        A new dictionary. The input is never mutated, so a caller cannot be
        surprised by the values it still holds after auditing.
    """
    if payload is None:
        return None
    return _redact_mapping(payload, depth=0)


def diff(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Field-level change set, already redacted.

    Only keys whose value actually changed appear, so an audit row records the
    edit rather than the whole record. Both sides are kept because "changed to
    X" is half a story when the question is who changed it *from* Y.
    """
    changes: dict[str, dict[str, Any]] = {}
    for key in after:
        old = before.get(key)
        new = after[key]
        if old == new:
            continue
        if is_secret_key(str(key)):
            # The fact of the change is the auditable part; the values are not.
            changes[str(key)] = {"from": REDACTED, "to": REDACTED}
            continue
        mask = is_pii_key(str(key))
        changes[str(key)] = {
            "from": _redact_value(old, depth=1, mask=mask),
            "to": _redact_value(new, depth=1, mask=mask),
        }
    return changes


__all__ = [
    "MAX_DEPTH",
    "MAX_ITEMS",
    "MAX_STRING_LENGTH",
    "PII_KEY_MARKERS",
    "REDACTED",
    "SECRET_KEY_MARKERS",
    "diff",
    "is_pii_key",
    "is_secret_key",
    "mask_email",
    "mask_phone",
    "mask_value",
    "redact",
]
