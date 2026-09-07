"""The messages the product sends.

Plain Python format strings, not a template engine. There are three messages,
they are short, and none of them loops or branches; a Jinja environment would
be a dependency, a search path and an autoescaping decision in exchange for
nothing these need.

**Every template is plain text.** Not a stylistic choice: an HTML mail is a
place to put a link whose visible text differs from its target, and these
messages exist to carry links that people are asked to trust. Plain text shows
the URL it is sending you to.

**A template declares the context it requires**, and rendering fails loudly
when a field is missing. Silently interpolating an empty string would produce
"Hi , click  to continue" — sent, logged as delivered, and useless.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    subject: str
    text_body: str


@dataclass(frozen=True, slots=True)
class EmailTemplate:
    """One message, and the fields it cannot be rendered without."""

    name: str
    subject: str
    body: str
    required: tuple[str, ...]


INVITATION = "invitation"
PASSWORD_RESET = "password_reset"  # noqa: S105 - a template name, not a secret
MEETING_REMINDER = "meeting_reminder"


_TEMPLATES: Final[tuple[EmailTemplate, ...]] = (
    EmailTemplate(
        name=INVITATION,
        subject="{inviter_name} invited you to {organization_name} on S3K",
        body=(
            "Hello,\n\n"
            "{inviter_name} has invited you to join {organization_name} on S3K.\n\n"
            "Accept the invitation:\n{accept_url}\n\n"
            "This link expires on {expires_on}. If you were not expecting it, "
            "you can ignore this message — nothing happens until you accept.\n\n"
            "— S3K\n"
        ),
        required=(
            "inviter_name",
            "organization_name",
            "accept_url",
            "expires_on",
        ),
    ),
    EmailTemplate(
        name=PASSWORD_RESET,
        subject="Reset your S3K password",
        body=(
            "Hello,\n\n"
            "Somebody asked to reset the password for this address. If it was "
            "you, choose a new one here:\n{reset_url}\n\n"
            "This link expires on {expires_on} and can be used once.\n\n"
            "If it was not you, ignore this message. Your password has not "
            "changed and nobody has been given access to your account.\n\n"
            "— S3K\n"
        ),
        required=("reset_url", "expires_on"),
    ),
    EmailTemplate(
        name=MEETING_REMINDER,
        subject="Reminder: {subject}",
        body=(
            "Hello {recipient_name},\n\n"
            "{subject} starts at {starts_at}.\n\n"
            "Open it in S3K:\n{record_url}\n\n"
            "— S3K\n"
        ),
        required=("recipient_name", "subject", "starts_at", "record_url"),
    ),
)

TEMPLATES: Final[dict[str, EmailTemplate]] = {
    template.name: template for template in _TEMPLATES
}


def render(name: str, context: dict[str, Any]) -> RenderedEmail:
    """Render ``name`` with ``context``.

    Raises:
        KeyError: the template does not exist, or the context is missing a
            field it declares. Both are permanent failures — the caller turns
            them into a dead-lettered event rather than retrying.
    """
    template = TEMPLATES.get(name)
    if template is None:
        msg = f"Unknown email template '{name}'."
        raise KeyError(msg)

    missing = [field for field in template.required if not context.get(field)]
    if missing:
        msg = f"Template '{name}' is missing: {', '.join(sorted(missing))}."
        raise KeyError(msg)

    # `format_map` over a plain dict: a template referencing a field that is
    # neither required nor supplied raises rather than rendering "{field}"
    # into the message a customer reads.
    return RenderedEmail(
        subject=template.subject.format_map(context),
        text_body=template.body.format_map(context),
    )


__all__ = [
    "INVITATION",
    "MEETING_REMINDER",
    "PASSWORD_RESET",
    "TEMPLATES",
    "EmailTemplate",
    "RenderedEmail",
    "render",
]
