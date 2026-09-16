"""Email providers, behind one interface.

Three implementations, and which one runs is a configuration decision rather
than a code path anybody chooses at a call site:

* :class:`~app.platform.email.graph.GraphEmailService` — the real one, and the
  **only** transport that delivers mail. Microsoft Graph with app-only
  (client-credentials) authentication. There is deliberately no SMTP,
  SendGrid, Resend or SES implementation beside it to fall back to.
* :class:`ConsoleProvider` — development. Writes the message to the log
  instead of sending it. **Reports success**, because the send genuinely
  happened as far as the system is concerned; a developer reads the link out
  of the log. ``Settings`` refuses it in staging and production.
* :class:`NullProvider` — no email configured. **Reports failure**, loudly and
  permanently.

That last distinction is the important one. Before this module the product
created invitations nobody was ever sent, and the invitation screen implied
otherwise. An unconfigured deployment must not quietly repeat that: it fails,
the delivery log says why, and the administrator can see that email was never
set up rather than discovering it from a customer.

**Failure classes.** A provider raises one of three things, and the delivery
handlers treat them differently:

* :class:`EmailNotConfiguredError` and :class:`EmailRejectedError` are
  permanent — no retry configures a mailbox or fixes an address the transport
  refused — so the event dead-letters at once and the delivery log says why.
* :class:`EmailTransientError` (throttling, an outage, a network failure) and
  anything unexpected are retried by the outbox with backoff.

None of their messages may carry a credential or an access token: they are
written to the delivery log, which administrators read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)


class EmailNotConfiguredError(Exception):
    """No provider is configured, so nothing can be sent."""


class EmailDeliveryError(Exception):
    """The transport was reached and the message did not go out."""


class EmailRejectedError(EmailDeliveryError):
    """The transport refused the message or our credentials. Permanent.

    Retrying an invalid client secret, a missing ``Mail.Send`` grant or a
    malformed recipient produces the same answer every time, so the handler
    dead-letters instead of spending the retry budget rediscovering it.
    """


class EmailTransientError(EmailDeliveryError):
    """The transport was throttled, unavailable or unreachable. Retried."""


#: The failures no retry can fix. The delivery handlers dead-letter on these.
PERMANENT_EMAIL_FAILURES: tuple[type[Exception], ...] = (
    EmailNotConfiguredError,
    EmailRejectedError,
)


@dataclass(frozen=True, slots=True)
class EmailAttachment:
    """One file to hang off a message.

    The bytes, in memory. That is a deliberate ceiling rather than an
    oversight: the transport receives each file in at most a few requests, so
    the message has to be assembled in memory whatever this type looks like,
    and streaming here would only move the ceiling somewhere less visible. The
    caller enforces a total size before it gets this far.
    """

    filename: str
    mime_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class OutboundEmail:
    """A message ready to hand over.

    ``to_address`` is the primary recipient and stays required and singular:
    every system message has exactly one, and widening it would have meant
    touching all of them to gain nothing. Everything below it is optional and
    defaulted, so the invitation, verification, password-reset and
    notification paths construct this type without naming fields they do not
    use.
    """

    to_address: str
    subject: str
    text_body: str
    html_body: str | None = None

    #: Further recipients. ``to_address`` is *not* repeated here.
    to_addresses: tuple[str, ...] = ()
    cc_addresses: tuple[str, ...] = ()
    #: Blind copies. Delivered to, and never shown to the other recipients —
    #: the transport carries them separately from the visible recipient list.
    bcc_addresses: tuple[str, ...] = ()
    reply_to: str | None = None
    #: Display name for the From address, e.g. "Ravi Menon".
    from_name: str | None = None

    #: Our identifier for the message, stored before the send so the delivery
    #: log and the CRM message can be traced into the transport's records.
    #: ``None`` for callers that do not need one, in which case the provider
    #: mints one.
    message_id: str | None = None
    #: The identifier of the message this replies to, when there is one.
    in_reply_to: str | None = None

    attachments: tuple[EmailAttachment, ...] = ()

    def envelope_recipients(self) -> tuple[str, ...]:
        """Every address the transport must deliver to, de-duplicated in order.

        Blind copies are in here and in no visible header — the whole
        distinction BCC rests on.
        """
        seen: dict[str, None] = {}
        for address in (
            self.to_address,
            *self.to_addresses,
            *self.cc_addresses,
            *self.bcc_addresses,
        ):
            if address:
                seen.setdefault(address, None)
        return tuple(seen)


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """What the provider said. ``message_id`` is the handle for tracing it."""

    message_id: str
    provider: str


class EmailProvider(Protocol):
    """What the delivery handler needs from a provider."""

    name: str

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        """Hand one message over, or raise.

        Raise :class:`EmailTransientError` (or anything unexpected) for a
        failure worth retrying, and :class:`EmailRejectedError` or
        :class:`EmailNotConfiguredError` for one that is not.
        """
        ...


class NullProvider:
    """No email configured. Every send fails, on purpose."""

    name = "null"

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        raise EmailNotConfiguredError(
            "No email provider is configured. Set EMAIL_PROVIDER=graph with the "
            "MICROSOFT_* settings, or EMAIL_PROVIDER=console for development."
        )


class ConsoleProvider:
    """Writes the message to the log and calls it sent.

    For development, where there is no mailbox and a real send would be
    undeliverable anyway. The body is logged in full — including any link —
    which is the point: it is how a developer completes an invitation flow
    locally. That is also why this provider must never be selected outside
    development, which ``Settings`` enforces.
    """

    name = "console"

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        logger.info(
            "email_console_delivery",
            to=message.to_address,
            # Counts, not addresses, for the copies. The body is logged in
            # full because a developer needs the link out of it; a blind-copy
            # list is not needed to complete any flow locally, and a
            # development log is a file that gets pasted into issues.
            cc_count=len(message.cc_addresses),
            bcc_count=len(message.bcc_addresses),
            attachments=len(message.attachments),
            subject=message.subject,
            body=message.text_body,
        )
        return DeliveryReceipt(
            message_id=message.message_id or f"console-{uuid.uuid4()}",
            provider=self.name,
        )


def build_provider(settings: Settings) -> EmailProvider:
    """Choose a provider from configuration.

    Built once per process and reused, like the object storage client — every
    construction reparses settings, and the Graph provider caches its access
    token between sends.
    """
    choice = settings.email_provider
    if choice == "graph":
        # Imported here: `graph` imports this module for the shared types.
        from app.platform.email.graph import GraphEmailService

        return GraphEmailService(settings)
    if choice == "console":
        return ConsoleProvider()
    return NullProvider()


__all__ = [
    "PERMANENT_EMAIL_FAILURES",
    "ConsoleProvider",
    "DeliveryReceipt",
    "EmailAttachment",
    "EmailDeliveryError",
    "EmailNotConfiguredError",
    "EmailProvider",
    "EmailRejectedError",
    "EmailTransientError",
    "NullProvider",
    "OutboundEmail",
    "build_provider",
]
