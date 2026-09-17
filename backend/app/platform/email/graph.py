"""Microsoft Graph email delivery — the platform's only email transport.

Every message the product sends — invitations, email verification, password
resets, reminders, notification emails and user-authored CRM mail — reaches a
mailbox through :class:`GraphEmailService`. There is no SMTP, SendGrid, Resend
or SES path beside it, and ``Settings`` offers no option that selects one.

**Authentication** is the OAuth2 client-credentials grant against Microsoft
Entra ID: an application identity, not a signed-in user, so the product never
holds anybody's mailbox password. The access token is cached in process memory
until shortly before it expires and is never logged, stored, returned to a
caller or placed in an error message — every error below is written to the
delivery log that administrators read, so each one carries an HTTP status and
Graph's error *code* and nothing else.

**Two delivery shapes, chosen by size.** Graph caps a single request at 4 MB,
and the CRM allows 20 MB of attachments on a message:

* A message whose base64-encoded request fits comfortably under that cap goes
  out in one ``POST /users/{sender}/sendMail`` call, not saved to Sent Items.
* A larger one is created as a draft, each attachment is added to it — small
  ones in one request, large ones through an upload session in chunks — and the
  draft is sent. This path needs the ``Mail.ReadWrite`` application permission
  in addition to ``Mail.Send``, and Graph files the sent message under the
  sender mailbox's Sent Items. A failure part-way deletes the draft on a best
  effort basis, so a retry starts clean rather than leaving half-built drafts
  in the mailbox.

**What Graph does not let us set.** ``sendMail`` accepts only custom ``X-``
internet headers, so the RFC 5322 ``In-Reply-To``/``References`` headers the
CRM composes cannot be sent. Our identifiers travel as ``X-S3K-Message-Id`` and
``X-S3K-In-Reply-To`` instead — enough to trace a delivery into Exchange's
message trace — and a reply threads in the recipient's client by subject.

**Failure classification** (see ``provider.py``): throttling (429), timeouts
(408), Graph outages (5xx) and network errors raise
:class:`~app.platform.email.provider.EmailTransientError`, which the outbox
retries with backoff. Every other refusal — a bad client secret, a missing
permission, an unknown sender mailbox, an invalid recipient — raises
:class:`~app.platform.email.provider.EmailRejectedError` and dead-letters. A
401 on a Graph call first discards the cached token and retries once, since a
token can be revoked before its advertised expiry.
"""

from __future__ import annotations

import asyncio
import base64
import time
import uuid
from typing import Any, Final
from urllib.parse import quote

import httpx
import structlog

from app.core.config import Settings
from app.platform.email.provider import (
    DeliveryReceipt,
    EmailAttachment,
    EmailNotConfiguredError,
    EmailRejectedError,
    EmailTransientError,
    OutboundEmail,
)

logger = structlog.get_logger(__name__)

TOKEN_URL: Final = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"  # noqa: S105 - a URL, not a credential
GRAPH_BASE_URL: Final = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE: Final = "https://graph.microsoft.com/.default"

#: Refresh this long before the advertised expiry, so a slow send never
#: presents a token that lapses mid-request.
TOKEN_REFRESH_MARGIN_SECONDS: Final = 120.0
DEFAULT_TOKEN_TTL_SECONDS: Final = 3600.0

#: Largest estimated request that is sent in one ``sendMail`` call. Graph's
#: hard limit is 4 MB; base64 and JSON overhead are why the budget is lower.
INLINE_REQUEST_BUDGET_BYTES: Final = 3 * 1024 * 1024
#: Largest attachment added to a draft in a single request. Anything bigger
#: goes through an upload session.
SINGLE_REQUEST_ATTACHMENT_BYTES: Final = 2 * 1024 * 1024
#: Upload-session chunk. Graph requires a multiple of 320 KiB, under 4 MiB.
UPLOAD_CHUNK_BYTES: Final = 320 * 1024 * 10

#: Headers carrying our identifiers. Graph accepts only ``X-`` headers.
MESSAGE_ID_HEADER: Final = "X-S3K-Message-Id"
IN_REPLY_TO_HEADER: Final = "X-S3K-In-Reply-To"

_JSON_OVERHEAD_BYTES: Final = 16 * 1024


class GraphEmailService:
    """Sends email through Microsoft Graph using app-only authentication.

    Configuration is read on every send rather than at construction, so
    building the service never fails — only attempting to send without full
    configuration does. ``transport`` exists for tests, which substitute an
    ``httpx.MockTransport``; production uses httpx's default network
    transport.
    """

    name = "graph"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    # --- The provider interface ------------------------------------------------

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        """Deliver ``message``, or raise.

        Raises:
            EmailNotConfiguredError: a required Microsoft setting is missing.
            EmailRejectedError: Entra ID or Graph refused; retrying won't help.
            EmailTransientError: throttled, unavailable or unreachable.
        """
        sender = self._sender()
        message_id = message.message_id or (
            f"<{uuid.uuid4()}@{self._settings.email_message_id_domain}>"
        )
        graph_message = build_graph_message(message, sender=sender, message_id=message_id)

        async with httpx.AsyncClient(
            transport=self._transport, timeout=self._settings.graph_timeout_seconds
        ) as client:
            if estimated_inline_request_bytes(message) <= INLINE_REQUEST_BUDGET_BYTES:
                if message.attachments:
                    graph_message["attachments"] = [
                        _file_attachment(attachment) for attachment in message.attachments
                    ]
                await self._request(
                    client,
                    "POST",
                    f"{GRAPH_BASE_URL}/users/{_segment(sender)}/sendMail",
                    json={"message": graph_message, "saveToSentItems": False},
                    expected=(202,),
                    action="sendMail",
                )
            else:
                await self._send_via_draft(client, sender, graph_message, message.attachments)

        logger.info(
            "graph_email_sent",
            recipients=len(message.envelope_recipients()),
            attachments=len(message.attachments),
        )
        return DeliveryReceipt(message_id=message_id, provider=self.name)

    # --- Large messages ----------------------------------------------------------

    async def _send_via_draft(
        self,
        client: httpx.AsyncClient,
        sender: str,
        graph_message: dict[str, Any],
        attachments: tuple[EmailAttachment, ...],
    ) -> None:
        mailbox = f"{GRAPH_BASE_URL}/users/{_segment(sender)}"
        created = await self._request(
            client,
            "POST",
            f"{mailbox}/messages",
            json=graph_message,
            expected=(201,),
            action="create draft",
        )
        draft_id = _json_string(created, "id", action="create draft")
        draft = f"{mailbox}/messages/{_segment(draft_id)}"

        try:
            for attachment in attachments:
                if len(attachment.content) <= SINGLE_REQUEST_ATTACHMENT_BYTES:
                    await self._request(
                        client,
                        "POST",
                        f"{draft}/attachments",
                        json=_file_attachment(attachment),
                        expected=(201,),
                        action="add attachment",
                    )
                else:
                    await self._upload_large_attachment(client, draft, attachment)
            await self._request(
                client, "POST", f"{draft}/send", json=None, expected=(202,), action="send draft"
            )
        except Exception:
            await self._discard_draft(client, draft)
            raise

    async def _upload_large_attachment(
        self, client: httpx.AsyncClient, draft: str, attachment: EmailAttachment
    ) -> None:
        size = len(attachment.content)
        session = await self._request(
            client,
            "POST",
            f"{draft}/attachments/createUploadSession",
            json={
                "AttachmentItem": {
                    "attachmentType": "file",
                    "name": attachment.filename,
                    "size": size,
                    "contentType": attachment.mime_type or "application/octet-stream",
                }
            },
            expected=(201,),
            action="create upload session",
        )
        upload_url = _json_string(session, "uploadUrl", action="create upload session")

        for start in range(0, size, UPLOAD_CHUNK_BYTES):
            chunk = attachment.content[start : start + UPLOAD_CHUNK_BYTES]
            end = start + len(chunk) - 1
            try:
                # No Authorization header: the upload URL is pre-authenticated,
                # and Graph rejects a request that presents a bearer token too.
                response = await client.put(
                    upload_url,
                    content=chunk,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Range": f"bytes {start}-{end}/{size}",
                    },
                )
            except httpx.HTTPError as failure:
                raise _network_failure("upload attachment", failure) from failure
            if response.status_code not in (200, 201):
                raise _http_failure("upload attachment", response)

    async def _discard_draft(self, client: httpx.AsyncClient, draft: str) -> None:
        """Delete a half-built draft. Best effort: the original error matters more."""
        try:
            token = await self._access_token(client)
            await client.delete(draft, headers={"Authorization": f"Bearer {token}"})
        except Exception:  # never mask the failure that brought us here
            logger.warning("graph_draft_cleanup_failed")

    # --- Requests and authentication ---------------------------------------------

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None,
        expected: tuple[int, ...],
        action: str,
    ) -> httpx.Response:
        """One authenticated Graph call, retried once on a stale token."""
        for attempt in (1, 2):
            token = await self._access_token(client, force_refresh=attempt == 2)
            try:
                response = await client.request(
                    method, url, json=json, headers={"Authorization": f"Bearer {token}"}
                )
            except httpx.HTTPError as failure:
                raise _network_failure(action, failure) from failure

            if response.status_code in expected:
                return response
            if response.status_code == 401 and attempt == 1:
                logger.info("graph_token_refused_refreshing", action=action)
                continue
            raise _http_failure(action, response)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _access_token(
        self, client: httpx.AsyncClient, *, force_refresh: bool = False
    ) -> str:
        tenant_id, client_id, client_secret = self._credentials()
        async with self._token_lock:
            now = time.monotonic()
            if force_refresh:
                self._token = None
            if self._token is not None and now < self._token_expires_at:
                return self._token

            try:
                response = await client.post(
                    TOKEN_URL.format(tenant_id=quote(tenant_id, safe="")),
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": GRAPH_SCOPE,
                        "grant_type": "client_credentials",
                    },
                )
            except httpx.HTTPError as failure:
                raise _network_failure("authenticate", failure) from failure
            if response.status_code != 200:
                raise _http_failure("authenticate", response)

            token = _json_string(response, "access_token", action="authenticate")
            try:
                ttl = float(response.json().get("expires_in", DEFAULT_TOKEN_TTL_SECONDS))
            except (TypeError, ValueError):
                ttl = DEFAULT_TOKEN_TTL_SECONDS
            self._token = token
            self._token_expires_at = now + max(ttl - TOKEN_REFRESH_MARGIN_SECONDS, 0.0)
            return token

    def _credentials(self) -> tuple[str, str, str]:
        settings = self._settings
        secret = settings.microsoft_client_secret
        values = {
            "MICROSOFT_TENANT_ID": settings.microsoft_tenant_id,
            "MICROSOFT_CLIENT_ID": settings.microsoft_client_id,
            "MICROSOFT_CLIENT_SECRET": secret.get_secret_value() if secret else None,
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise EmailNotConfiguredError(
                f"Microsoft Graph email is not configured. Missing: {', '.join(missing)}."
            )
        return (
            str(values["MICROSOFT_TENANT_ID"]),
            str(values["MICROSOFT_CLIENT_ID"]),
            str(values["MICROSOFT_CLIENT_SECRET"]),
        )

    def _sender(self) -> str:
        sender = self._settings.microsoft_graph_sender_email
        if not sender:
            raise EmailNotConfiguredError(
                "Microsoft Graph email is not configured. Missing: MICROSOFT_GRAPH_SENDER_EMAIL."
            )
        # Checked before any network call, so a missing secret is reported as
        # configuration rather than as a rejected token request.
        self._credentials()
        return sender


# --- Request shape ------------------------------------------------------------------


def build_graph_message(
    message: OutboundEmail, *, sender: str, message_id: str
) -> dict[str, Any]:
    """The Graph ``message`` resource for ``message``, without attachments."""
    if message.html_body:
        body = {"contentType": "HTML", "content": message.html_body}
    else:
        body = {"contentType": "Text", "content": message.text_body}

    graph_message: dict[str, Any] = {
        "subject": message.subject,
        "body": body,
        "toRecipients": _recipients((message.to_address, *message.to_addresses)),
    }
    if message.cc_addresses:
        graph_message["ccRecipients"] = _recipients(message.cc_addresses)
    if message.bcc_addresses:
        graph_message["bccRecipients"] = _recipients(message.bcc_addresses)
    if message.reply_to:
        graph_message["replyTo"] = _recipients((message.reply_to,))
    if message.from_name:
        # The address is always the configured mailbox — app-only sending
        # cannot impersonate another one — and only the display name varies.
        graph_message["from"] = {
            "emailAddress": {"address": sender, "name": message.from_name}
        }

    headers = [{"name": MESSAGE_ID_HEADER, "value": message_id}]
    if message.in_reply_to:
        headers.append({"name": IN_REPLY_TO_HEADER, "value": message.in_reply_to})
    graph_message["internetMessageHeaders"] = headers
    return graph_message


def estimated_inline_request_bytes(message: OutboundEmail) -> int:
    """An upper estimate of the ``sendMail`` request size for ``message``."""
    attachments = sum(4 * ((len(item.content) + 2) // 3) for item in message.attachments)
    bodies = len((message.html_body or message.text_body).encode("utf-8"))
    return attachments + bodies + len(message.subject.encode("utf-8")) + _JSON_OVERHEAD_BYTES


def _recipients(addresses: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{"emailAddress": {"address": address}} for address in addresses if address]


def _file_attachment(attachment: EmailAttachment) -> dict[str, Any]:
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": attachment.filename,
        "contentType": attachment.mime_type or "application/octet-stream",
        "contentBytes": base64.b64encode(attachment.content).decode("ascii"),
    }


def _segment(value: str) -> str:
    return quote(value, safe="@")


# --- Errors -----------------------------------------------------------------------


def graph_error_code(response: httpx.Response) -> str | None:
    """Graph's (or Entra ID's) error *code*, never its free-text message.

    Graph answers ``{"error": {"code": ...}}``; the token endpoint answers
    ``{"error": "invalid_client"}``. The descriptions are left out on purpose:
    they can echo request details, and these strings end up in the delivery log.
    """
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        return code if isinstance(code, str) else None
    return error if isinstance(error, str) else None


def _http_failure(action: str, response: httpx.Response) -> Exception:
    code = graph_error_code(response)
    status = response.status_code
    detail = f"Microsoft Graph {action} failed with HTTP {status}" + (
        f" ({code})." if code else "."
    )
    logger.warning(
        "graph_email_request_failed", action=action, status_code=status, graph_error=code
    )
    if status in (408, 429) or status >= 500:
        return EmailTransientError(detail)
    return EmailRejectedError(detail)


def _network_failure(action: str, failure: httpx.HTTPError) -> EmailTransientError:
    logger.warning("graph_email_network_error", action=action, error_type=type(failure).__name__)
    return EmailTransientError(
        f"Could not reach Microsoft Graph to {action} ({type(failure).__name__})."
    )


def _json_string(response: httpx.Response, key: str, *, action: str) -> str:
    try:
        value = response.json().get(key)
    except (ValueError, AttributeError):
        value = None
    if not isinstance(value, str) or not value:
        raise EmailTransientError(f"Microsoft Graph {action} returned an unexpected response.")
    return value


__all__ = [
    "GRAPH_BASE_URL",
    "INLINE_REQUEST_BUDGET_BYTES",
    "IN_REPLY_TO_HEADER",
    "MESSAGE_ID_HEADER",
    "SINGLE_REQUEST_ATTACHMENT_BYTES",
    "TOKEN_URL",
    "UPLOAD_CHUNK_BYTES",
    "GraphEmailService",
    "build_graph_message",
    "estimated_inline_request_bytes",
    "graph_error_code",
]
