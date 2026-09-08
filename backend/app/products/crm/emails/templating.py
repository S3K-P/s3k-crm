"""Placeholder substitution for user-written templates, and subject normalization.

``{{placeholder}}``, not ``{placeholder}``, and the difference is not cosmetic.
The platform's three system templates use ``str.format``; that is safe for
strings held in source control and reviewed with the code. A user's template
body is arbitrary prose, and single braces appear in it: a pasted JSON snippet,
a code sample, a range written ``{1,200}``. Under ``str.format`` every one of
those raises at send time and the message never goes out — a failure the sender
can neither predict nor fix. Double braces are rare in prose, and the
substitution below is a regex over a fixed vocabulary rather than an evaluator.

**An unknown placeholder is left alone.** Not blanked, and not an error. A
template written against a field this record does not have should send with
the placeholder visible, so the sender sees what went wrong and fixes it, and
so the *recipient* never receives "Dear ," — which is what blanking produces
and which is worse than any of the alternatives. The render endpoint reports
unresolved names separately so the composer can warn before anything is sent.

Nothing here evaluates anything. The vocabulary is a flat ``dict[str, str]``
built by :mod:`app.products.crm.emails.variables` from one record, and a
placeholder that is not a key in it is not substituted. There is no attribute
traversal, no expression, and therefore no way for a template to reach a field
its author was not offered.
"""

from __future__ import annotations

import re
from typing import Final

#: ``{{ name }}`` with optional inner whitespace. The name charset is
#: deliberately narrow — letters, digits, underscore and a single dot for the
#: ``record.field`` shape — so that a brace pair around arbitrary prose is not
#: mistaken for a placeholder and mangled.
_PLACEHOLDER: Final = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)*)\s*\}\}")

#: Reply and forward prefixes stripped when grouping a subject into a thread.
#: Matched repeatedly from the left, so "Re: Fwd: RE: Quote" normalizes to
#: "quote" — which is what a chain of replies and forwards actually looks like
#: by the time it comes back to us.
_SUBJECT_PREFIX: Final = re.compile(
    r"^\s*(?:re|aw|sv|vs|fw|fwd|wg)\s*(?:\[\d+\])?\s*:\s*", re.IGNORECASE
)

#: Ceiling on prefix stripping. A subject line consisting of nothing but
#: "Re:" repeated is a malformed input, not a conversation, and this stops it
#: costing more than a constant.
_MAX_PREFIX_STRIPS: Final = 10


def render_placeholders(text: str, variables: dict[str, str]) -> str:
    """Substitute ``{{name}}`` from ``variables``, leaving unknowns in place."""

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        value = variables.get(name)
        return match.group(0) if value is None else value

    return _PLACEHOLDER.sub(substitute, text)


def placeholders_in(text: str) -> set[str]:
    """Every placeholder name ``text`` uses."""
    return {match.group(1) for match in _PLACEHOLDER.finditer(text)}


def unresolved_placeholders(text: str, variables: dict[str, str]) -> list[str]:
    """Placeholder names ``text`` uses that ``variables`` cannot fill.

    Sorted, so the composer's warning is stable between renders rather than
    reordering itself on every keystroke.
    """
    return sorted(placeholders_in(text) - set(variables))


def normalize_subject(subject: str) -> str:
    """The grouping key for a subject line.

    Reply and forward prefixes removed, whitespace collapsed, case folded.
    ``casefold`` rather than ``lower``: it is the correct operation for
    case-insensitive comparison outside ASCII, and subjects are not ASCII.

    An empty result — a subject that was nothing but prefixes, or nothing at
    all — is returned as the empty string rather than being special-cased.
    Threads are matched on this *together with* the record, so empty-subject
    messages to one contact group with each other and with nobody else, which
    is the behaviour a mail client has too.
    """
    working = subject.strip()
    for _ in range(_MAX_PREFIX_STRIPS):
        stripped = _SUBJECT_PREFIX.sub("", working, count=1)
        if stripped == working:
            break
        working = stripped
    return " ".join(working.split()).casefold()


__all__ = [
    "normalize_subject",
    "placeholders_in",
    "render_placeholders",
    "unresolved_placeholders",
]
