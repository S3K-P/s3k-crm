"""Tests for Microsoft Graph email delivery.

Graph is exercised through ``httpx.MockTransport`` rather than a live
network call: no real Graph credentials are available in this environment
(see the final task report), so these tests validate the request/response
handling contract, not a live send.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import pytest

from app.core.config import Settings
from app.platform.notifications.email_service import (
    EmailAttachment,
    EmailDeliveryError,
    EmailMessage,
    EmailNotConfiguredError,
    GraphEmailService,
)

TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/s3k_test"
TEST_REDIS_URL = "redis://localhost:6379/15"

TOKEN_RESPONSE = {"access_token": "fake-token", "expires_in": 3600, "token_type": "Bearer"}


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": TEST_DATABASE_URL,
        "redis_url": TEST_REDIS_URL,
        "microsoft_tenant_id": "tenant-123",
        "microsoft_client_id": "client-123",
        "microsoft_client_secret": "secret-123",
        "microsoft_graph_sender_email": "notifications@s3k.example.com",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg, arg-type]


def _message(**overrides: object) -> EmailMessage:
    defaults: dict[str, object] = {
        "to": ["someone@example.com"],
        "subject": "Hello",
        "html_body": "<p>Hi</p>",
    }
    defaults.update(overrides)
    return EmailMessage(**defaults)  # type: ignore[arg-type]


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _is_token_request(request: httpx.Request) -> bool:
    return request.url.path.endswith("/oauth2/v2.0/token")


# --- EmailMessage validation -------------------------------------------------


def test_email_message_requires_a_recipient() -> None:
    with pytest.raises(ValueError, match="recipient"):
        EmailMessage(to=[], subject="Hi", html_body="<p>hi</p>")


def test_email_message_requires_a_body() -> None:
    with pytest.raises(ValueError, match="body"):
        EmailMessage(to=["a@example.com"], subject="Hi")


# --- Missing environment variables ------------------------------------------


async def test_send_fails_fast_when_fully_unconfigured() -> None:
    settings = _settings(
        microsoft_tenant_id=None,
        microsoft_client_id=None,
        microsoft_client_secret=None,
        microsoft_graph_sender_email=None,
    )
    service = GraphEmailService(settings)

    with pytest.raises(EmailNotConfiguredError) as exc_info:
        await service.send(_message())

    message = str(exc_info.value)
    assert "MICROSOFT_TENANT_ID" in message
    assert "MICROSOFT_CLIENT_ID" in message
    assert "MICROSOFT_CLIENT_SECRET" in message
    assert "MICROSOFT_GRAPH_SENDER_EMAIL" in message


async def test_send_fails_fast_when_partially_configured() -> None:
    settings = _settings(microsoft_client_secret=None)
    service = GraphEmailService(settings)

    with pytest.raises(EmailNotConfiguredError, match="MICROSOFT_CLIENT_SECRET"):
        await service.send(_message())


async def test_unconfigured_send_never_reaches_the_network() -> None:
    """A missing-config send must fail before any HTTP call is attempted."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=TOKEN_RESPONSE)

    settings = _settings(microsoft_client_secret=None)
    service = GraphEmailService(settings, client=_client(handler))

    with pytest.raises(EmailNotConfiguredError):
        await service.send(_message())

    assert calls == []


# --- Authentication / client creation ---------------------------------------


async def test_successful_send_acquires_a_token_first() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if _is_token_request(request):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(202)

    service = GraphEmailService(_settings(), client=_client(handler))
    await service.send(_message())

    assert len(calls) == 2
    assert _is_token_request(calls[0])
    assert calls[1].headers["authorization"] == "Bearer fake-token"


async def test_token_request_uses_client_credentials_grant() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            captured.update(dict(httpx.QueryParams(request.content.decode())))
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(202)

    service = GraphEmailService(_settings(), client=_client(handler))
    await service.send(_message())

    assert captured["grant_type"] == "client_credentials"
    assert captured["scope"] == "https://graph.microsoft.com/.default"
    assert captured["client_id"] == "client-123"
    assert captured["client_secret"] == "secret-123"  # noqa: S105 — OAuth2 field name, not a real secret


async def test_token_is_cached_across_sends() -> None:
    token_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_requests
        if _is_token_request(request):
            token_requests += 1
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(202)

    service = GraphEmailService(_settings(), client=_client(handler))
    await service.send(_message())
    await service.send(_message())

    assert token_requests == 1


async def test_authentication_failure_raises_delivery_error_without_leaking_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_client", "error_description": "secret"})

    service = GraphEmailService(_settings(), client=_client(handler))

    with pytest.raises(EmailDeliveryError) as exc_info:
        await service.send(_message())

    assert "secret" not in str(exc_info.value)
    assert "invalid_client" not in str(exc_info.value)


# --- sendMail request / successful email ------------------------------------


async def test_sendmail_posts_to_the_configured_sender_mailbox() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if _is_token_request(request):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(202)

    service = GraphEmailService(_settings(), client=_client(handler))
    await service.send(_message())

    assert "/v1.0/users/notifications@s3k.example.com/sendMail" in seen_paths


async def test_sendmail_payload_includes_recipients_and_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        captured["body"] = json.loads(request.content)
        return httpx.Response(202)

    service = GraphEmailService(_settings(), client=_client(handler))
    await service.send(
        _message(
            to=["a@example.com", "b@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            subject="Quarterly report",
            html_body="<p>See attached</p>",
        )
    )

    body = captured["body"]
    assert isinstance(body, dict)
    graph_message = body["message"]
    assert graph_message["subject"] == "Quarterly report"
    assert graph_message["body"] == {"contentType": "HTML", "content": "<p>See attached</p>"}
    assert graph_message["toRecipients"] == [
        {"emailAddress": {"address": "a@example.com"}},
        {"emailAddress": {"address": "b@example.com"}},
    ]
    assert graph_message["ccRecipients"] == [{"emailAddress": {"address": "cc@example.com"}}]
    assert graph_message["bccRecipients"] == [{"emailAddress": {"address": "bcc@example.com"}}]
    assert body["saveToSentItems"] == "false"


async def test_sendmail_omits_cc_and_bcc_when_absent() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        captured["body"] = json.loads(request.content)
        return httpx.Response(202)

    service = GraphEmailService(_settings(), client=_client(handler))
    await service.send(_message())

    graph_message = captured["body"]["message"]  # type: ignore[index]
    assert "ccRecipients" not in graph_message
    assert "bccRecipients" not in graph_message


async def test_sendmail_uses_text_content_type_when_no_html_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        captured["body"] = json.loads(request.content)
        return httpx.Response(202)

    service = GraphEmailService(_settings(), client=_client(handler))
    await service.send(_message(html_body=None, text_body="plain text"))

    graph_message = captured["body"]["message"]  # type: ignore[index]
    assert graph_message["body"] == {"contentType": "Text", "content": "plain text"}


async def test_attachments_are_base64_encoded_file_attachments() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        captured["body"] = json.loads(request.content)
        return httpx.Response(202)

    service = GraphEmailService(_settings(), client=_client(handler))
    await service.send(
        _message(
            attachments=[
                EmailAttachment(
                    filename="report.txt", content=b"hello world", content_type="text/plain"
                )
            ]
        )
    )

    attachment = captured["body"]["message"]["attachments"][0]  # type: ignore[index]
    assert attachment["@odata.type"] == "#microsoft.graph.fileAttachment"
    assert attachment["name"] == "report.txt"
    assert attachment["contentType"] == "text/plain"
    assert base64.b64decode(attachment["contentBytes"]) == b"hello world"


# --- Graph API failure --------------------------------------------------------


async def test_graph_send_failure_raises_delivery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        return httpx.Response(400, json={"error": {"code": "ErrorInvalidRecipients"}})

    service = GraphEmailService(_settings(), client=_client(handler))

    with pytest.raises(EmailDeliveryError):
        await service.send(_message())


async def test_network_failure_during_send_raises_delivery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if _is_token_request(request):
            return httpx.Response(200, json=TOKEN_RESPONSE)
        raise httpx.ConnectError("connection refused", request=request)

    service = GraphEmailService(_settings(), client=_client(handler))

    with pytest.raises(EmailDeliveryError):
        await service.send(_message())


async def test_malformed_token_response_raises_delivery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer"})  # no access_token

    service = GraphEmailService(_settings(), client=_client(handler))

    with pytest.raises(EmailDeliveryError):
        await service.send(_message())
