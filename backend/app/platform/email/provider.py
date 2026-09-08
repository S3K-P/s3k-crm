"""Email providers, behind one interface.

Three implementations, and which one runs is a configuration decision rather
than a code path anybody chooses at a call site:

* :class:`SmtpProvider` — the real one. SMTP because it is what every
  transactional provider speaks: SES, Postmark, Resend and a corporate relay
  are all reachable through it, so choosing a vendor is a hostname rather than
  a dependency.
* :class:`ConsoleProvider` — development. Writes the message to the log
  instead of sending it. **Reports success**, because the send genuinely
  happened as far as the system is concerned; a developer reads the link out
  of the log.
* :class:`NullProvider` — no email configured. **Reports failure**, loudly and
  permanently.

That last distinction is the important one. Before this module the product
created invitations nobody was ever sent, and the invitation screen implied
otherwise. An unconfigured deployment must not quietly repeat that: it fails,
the delivery log says why, and the administrator can see that email was never
set up rather than discovering it from a customer.
"""

from __future__ import annotations

import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import structlog

from app.core.config import Settings

logger = structlog.get_logger(__name__)


class EmailNotConfiguredError(Exception):
    """No provider is configured, so nothing can be sent."""


@dataclass(frozen=True, slots=True)
class OutboundEmail:
    """A message ready to hand over."""

    to_address: str
    subject: str
    text_body: str
    html_body: str | None = None


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """What the provider said. ``message_id`` is their handle, not ours."""

    message_id: str
    provider: str


class EmailProvider(Protocol):
    """What the delivery handler needs from a provider."""

    name: str

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        """Hand one message over, or raise.

        A raise is retried by the outbox with backoff, so a provider should
        raise for anything transient and let the dispatcher decide. Raising
        :class:`~app.platform.events.service.PermanentEventError` from a
        caller is how a permanent rejection skips the retries.
        """
        ...


class NullProvider:
    """No email configured. Every send fails, on purpose."""

    name = "null"

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        raise EmailNotConfiguredError(
            "No email provider is configured. Set SMTP_HOST, or EMAIL_PROVIDER=console "
            "for development."
        )


class ConsoleProvider:
    """Writes the message to the log and calls it sent.

    For development, where there is no relay and a real send would be
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
            subject=message.subject,
            body=message.text_body,
        )
        return DeliveryReceipt(message_id=f"console-{uuid.uuid4()}", provider=self.name)


class SmtpProvider:
    """Sends over SMTP.

    Synchronous ``smtplib`` run in a thread rather than an async SMTP library:
    this is the worker, one message at a time, and a thread hop is a simpler
    dependency than another protocol implementation. If throughput ever needs
    concurrency the interface above is what makes that a swap.
    """

    name = "smtp"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        import anyio

        return await anyio.to_thread.run_sync(self._send_blocking, message)

    def _send_blocking(self, message: OutboundEmail) -> DeliveryReceipt:
        settings = self._settings
        host = settings.smtp_host
        if not host:
            raise EmailNotConfiguredError("SMTP_HOST is not set.")

        envelope = EmailMessage()
        envelope["From"] = settings.email_from_address
        envelope["To"] = message.to_address
        envelope["Subject"] = message.subject
        # A Message-ID we control, so a delivery can be traced from our log
        # into the provider's without relying on them to echo anything back.
        message_id = f"<{uuid.uuid4()}@{settings.email_message_id_domain}>"
        envelope["Message-ID"] = message_id
        envelope.set_content(message.text_body)
        if message.html_body:
            envelope.add_alternative(message.html_body, subtype="html")

        context = ssl.create_default_context()
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                host, settings.smtp_port, timeout=settings.smtp_timeout_seconds,
                context=context,
            ) as client:
                self._authenticate(client)
                client.send_message(envelope)
        else:
            with smtplib.SMTP(
                host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            ) as client:
                if settings.smtp_use_tls:
                    client.starttls(context=context)
                self._authenticate(client)
                client.send_message(envelope)

        return DeliveryReceipt(message_id=message_id, provider=self.name)

    def _authenticate(self, client: smtplib.SMTP) -> None:
        settings = self._settings
        if settings.smtp_username and settings.smtp_password:
            client.login(
                settings.smtp_username, settings.smtp_password.get_secret_value()
            )


def build_provider(settings: Settings) -> EmailProvider:
    """Choose a provider from configuration.

    Built once per process and reused, like the object storage client — every
    construction reparses settings, and the SMTP provider holds no connection
    between sends anyway.
    """
    choice = settings.email_provider
    if choice == "smtp":
        return SmtpProvider(settings)
    if choice == "console":
        return ConsoleProvider()
    return NullProvider()


__all__ = [
    "ConsoleProvider",
    "DeliveryReceipt",
    "EmailNotConfiguredError",
    "EmailProvider",
    "NullProvider",
    "OutboundEmail",
    "SmtpProvider",
    "build_provider",
]
