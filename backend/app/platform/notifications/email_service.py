"""Microsoft Graph email delivery.

Microsoft Graph's ``sendMail`` endpoint is the only supported email transport
for the platform — no other provider (SMTP, SendGrid, Resend, etc.) is wired
in alongside or behind it. Authentication uses the OAuth2 client-credentials
grant against Azure AD (an application identity, not a signed-in user), and
the send itself is a direct REST call: a full Graph SDK isn't warranted for
one endpoint, and ``httpx`` is already this project's HTTP client dependency.

Callers should go through :mod:`app.platform.notifications.service` — the
module's public interface — rather than importing this module directly.
"""

from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
import structlog

from app.core.config import Settings
from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)

_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"  # noqa: S105 — URL, not a credential
_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
# Refresh ahead of actual expiry so a slow send never races a token that
# expires mid-request.
_TOKEN_REFRESH_MARGIN_SECONDS = 60.0
_DEFAULT_TOKEN_TTL_SECONDS = 3600.0
_REQUEST_TIMEOUT_SECONDS = 30.0


class EmailNotConfiguredError(AppError):
    """Raised when a Graph email send is attempted without full configuration."""

    status_code = 503
    code = "email_not_configured"
    message = "Microsoft Graph email is not configured."


class EmailDeliveryError(AppError):
    """Raised when Microsoft Graph rejects authentication or the send request."""

    status_code = 502
    code = "email_delivery_failed"
    message = "Microsoft Graph email delivery failed."


@dataclass(slots=True)
class EmailAttachment:
    """A file to attach to an outgoing email."""

    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass(slots=True)
class EmailMessage:
    """A provider-agnostic description of an email to send.

    Callers build one of these; the Graph-specific request shape is assembled
    internally so the provider can change without touching call sites.
    """

    to: list[str]
    subject: str
    html_body: str | None = None
    text_body: str | None = None
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    attachments: list[EmailAttachment] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.to:
            raise ValueError("EmailMessage requires at least one recipient in 'to'.")
        if self.html_body is None and self.text_body is None:
            raise ValueError("EmailMessage requires html_body or text_body.")


def _required_settings(settings: Settings) -> tuple[str, str, str, str]:
    """Return the four Graph settings, or raise naming exactly what's missing."""
    fields = {
        "MICROSOFT_TENANT_ID": settings.microsoft_tenant_id,
        "MICROSOFT_CLIENT_ID": settings.microsoft_client_id,
        "MICROSOFT_CLIENT_SECRET": settings.microsoft_client_secret,
        "MICROSOFT_GRAPH_SENDER_EMAIL": settings.microsoft_graph_sender_email,
    }
    missing = [name for name, value in fields.items() if not value]
    if missing:
        raise EmailNotConfiguredError(
            f"Microsoft Graph email is not configured. Missing: {', '.join(missing)}."
        )
    return (
        cast(str, settings.microsoft_tenant_id),
        cast(str, settings.microsoft_client_id),
        cast(str, settings.microsoft_client_secret),
        cast(str, settings.microsoft_graph_sender_email),
    )


def _graph_error_code(response: httpx.Response) -> str | None:
    """Best-effort extraction of Graph's error.code — never the error message,
    which may echo request details we don't want in logs."""
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _recipient(address: str) -> dict[str, Any]:
    return {"emailAddress": {"address": address}}


def _build_payload(message: EmailMessage) -> dict[str, Any]:
    if message.html_body is not None:
        body_content, content_type = message.html_body, "HTML"
    else:
        body_content, content_type = message.text_body or "", "Text"

    graph_message: dict[str, Any] = {
        "subject": message.subject,
        "body": {"contentType": content_type, "content": body_content},
        "toRecipients": [_recipient(address) for address in message.to],
    }
    if message.cc:
        graph_message["ccRecipients"] = [_recipient(address) for address in message.cc]
    if message.bcc:
        graph_message["bccRecipients"] = [_recipient(address) for address in message.bcc]
    if message.attachments:
        graph_message["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment.filename,
                "contentType": attachment.content_type,
                "contentBytes": base64.b64encode(attachment.content).decode("ascii"),
            }
            for attachment in message.attachments
        ]
    # Application-only sends have no mailbox "Sent Items" the caller expects
    # to see this in; Graph defaults to true, which would be surprising here.
    return {"message": graph_message, "saveToSentItems": "false"}


class GraphEmailService:
    """Sends email through Microsoft Graph using app-only (client-credentials) auth.

    Configuration is read lazily from ``settings`` on every ``send`` call
    rather than at construction, so building the service never fails — only
    attempting to actually send without full configuration does.
    """

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client
        self._owns_client = client is None
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    def _client_for_requests(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS)
        return self._client

    async def aclose(self) -> None:
        """Release the HTTP client, if this service created its own."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get_access_token(
        self, client: httpx.AsyncClient, tenant_id: str, client_id: str, client_secret: str
    ) -> str:
        async with self._token_lock:
            now = time.monotonic()
            if self._token is not None and now < self._token_expires_at:
                return self._token

            try:
                response = await client.post(
                    _TOKEN_URL.format(tenant_id=tenant_id),
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": _GRAPH_SCOPE,
                        "grant_type": "client_credentials",
                    },
                )
            except httpx.HTTPError as exc:
                logger.warning("graph_token_request_failed", error_type=type(exc).__name__)
                raise EmailDeliveryError(
                    "Could not reach Microsoft Entra ID to authenticate."
                ) from exc

            if response.status_code != httpx.codes.OK:
                logger.warning(
                    "graph_token_request_rejected",
                    status_code=response.status_code,
                    graph_error=_graph_error_code(response),
                )
                raise EmailDeliveryError(
                    "Microsoft Graph authentication failed.",
                    details={"status_code": response.status_code},
                )

            payload = response.json()
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                logger.warning("graph_token_response_malformed")
                raise EmailDeliveryError("Microsoft Graph authentication response was malformed.")

            expires_in = payload.get("expires_in", _DEFAULT_TOKEN_TTL_SECONDS)
            self._token = token
            self._token_expires_at = now + max(
                float(expires_in) - _TOKEN_REFRESH_MARGIN_SECONDS, 0.0
            )
            return self._token

    async def send(self, message: EmailMessage) -> None:
        """Send ``message`` via Graph ``sendMail``.

        Raises:
            EmailNotConfiguredError: one or more of the four required
                settings is missing.
            EmailDeliveryError: authentication or the Graph send request
                failed.
        """
        tenant_id, client_id, client_secret, sender = _required_settings(self._settings)
        client = self._client_for_requests()

        access_token = await self._get_access_token(client, tenant_id, client_id, client_secret)

        try:
            response = await client.post(
                _SEND_MAIL_URL.format(sender=sender),
                headers={"Authorization": f"Bearer {access_token}"},
                json=_build_payload(message),
            )
        except httpx.HTTPError as exc:
            logger.warning("graph_send_mail_network_error", error_type=type(exc).__name__)
            raise EmailDeliveryError("Could not reach Microsoft Graph to send the email.") from exc

        if response.status_code != httpx.codes.ACCEPTED:
            logger.warning(
                "graph_send_mail_rejected",
                status_code=response.status_code,
                graph_error=_graph_error_code(response),
            )
            raise EmailDeliveryError(
                "Microsoft Graph rejected the email send request.",
                details={"status_code": response.status_code},
            )

        logger.info(
            "graph_send_mail_succeeded",
            recipient_count=len(message.to) + len(message.cc) + len(message.bcc),
            attachment_count=len(message.attachments),
        )


def create_email_service(settings: Settings) -> GraphEmailService:
    """Build the Graph email client. Safe to call regardless of configuration —
    validation happens lazily, at send time."""
    return GraphEmailService(settings)


async def send_email(settings: Settings, message: EmailMessage) -> None:
    """One-shot convenience wrapper: build a client, send, and close it."""
    service = create_email_service(settings)
    try:
        await service.send(message)
    finally:
        await service.aclose()
