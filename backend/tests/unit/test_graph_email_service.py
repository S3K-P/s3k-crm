"""Microsoft Graph email transport, against a mocked Graph.

Nothing here reaches the network: ``httpx.MockTransport`` stands in for Entra
ID and Graph, and each test asserts on the exact requests the service made.
What is pinned:

* the request shape — recipients, CC, BCC, reply-to, display name, body type,
  our identifier headers, inline attachments;
* token caching, and the one retry on a 401;
* the large-message path — draft, attachment uploads in chunks, send — and
  that a failure part-way deletes the draft;
* failure classification: throttling and outages are transient, refusals are
  permanent, a missing setting is "not configured";
* that no credential or access token ever appears in an error message, since
  those messages are written to the delivery log administrators read.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import Settings
from app.platform.email.graph import (
    IN_REPLY_TO_HEADER,
    MESSAGE_ID_HEADER,
    SINGLE_REQUEST_ATTACHMENT_BYTES,
    UPLOAD_CHUNK_BYTES,
    GraphEmailService,
    estimated_inline_request_bytes,
    graph_error_code,
)
from app.platform.email.provider import (
    PERMANENT_EMAIL_FAILURES,
    ConsoleProvider,
    EmailAttachment,
    EmailNotConfiguredError,
    EmailRejectedError,
    EmailTransientError,
    NullProvider,
    OutboundEmail,
    build_provider,
)

SECRET = "super-secret-client-value"  # a fixture, asserted never to leak
TOKEN = "eyJ-access-token-value"  # a fixture, asserted never to leak
SENDER = "notifications@s3k.example.com"
MAILBOX = f"https://graph.microsoft.com/v1.0/users/{SENDER}"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_url": "postgresql+asyncpg://user:pw@db:5432/s3k",
        "redis_url": "redis://cache:6379/0",
        "email_provider": "graph",
        "microsoft_tenant_id": "tenant-123",
        "microsoft_client_id": "client-456",
        "microsoft_client_secret": SECRET,
        "microsoft_graph_sender_email": SENDER,
        "email_message_id_domain": "s3k.test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@dataclass
class FakeGraph:
    """Answers token and Graph requests, and remembers every one."""

    requests: list[httpx.Request] = field(default_factory=list)
    token_status: int = 200
    token_body: dict[str, Any] = field(
        default_factory=lambda: {"access_token": TOKEN, "expires_in": 3600}
    )
    #: (method, path suffix) -> list of responses consumed in order; the last
    #: one repeats.
    routes: dict[tuple[str, str], list[httpx.Response]] = field(default_factory=dict)
    raise_on: tuple[str, str] | None = None

    def route(self, method: str, suffix: str, *responses: httpx.Response) -> None:
        self.routes[(method, suffix)] = list(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if "login.microsoftonline.com" in url:
            return httpx.Response(self.token_status, json=self.token_body)
        for (method, suffix), responses in self.routes.items():
            if request.method == method and url.endswith(suffix):
                if self.raise_on == (method, suffix):
                    raise httpx.ConnectError("boom", request=request)
                return responses.pop(0) if len(responses) > 1 else responses[0]
        return httpx.Response(404, json={"error": {"code": "UnexpectedRoute"}})

    def service(self, settings: Settings | None = None) -> GraphEmailService:
        return GraphEmailService(
            settings or _settings(), transport=httpx.MockTransport(self.handler)
        )

    def matching(self, predicate: Callable[[httpx.Request], bool]) -> list[httpx.Request]:
        return [request for request in self.requests if predicate(request)]

    def token_requests(self) -> list[httpx.Request]:
        return self.matching(lambda r: "login.microsoftonline.com" in str(r.url))


def _message(**overrides: Any) -> OutboundEmail:
    values: dict[str, Any] = {
        "to_address": "ravi@customer.example",
        "subject": "Proposal",
        "text_body": "Plain body",
    }
    values.update(overrides)
    return OutboundEmail(**values)


def _json(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content)  # type: ignore[no-any-return]


# --- Small messages: one sendMail call ----------------------------------------


async def test_a_plain_message_is_sent_with_one_sendmail_call() -> None:
    graph = FakeGraph()
    graph.route("POST", "/sendMail", httpx.Response(202))

    receipt = await graph.service().send(_message())

    send = graph.matching(lambda r: str(r.url) == f"{MAILBOX}/sendMail")
    assert len(send) == 1
    assert send[0].headers["Authorization"] == f"Bearer {TOKEN}"
    payload = _json(send[0])
    assert payload["saveToSentItems"] is False
    message = payload["message"]
    assert message["subject"] == "Proposal"
    assert message["body"] == {"contentType": "Text", "content": "Plain body"}
    assert message["toRecipients"] == [{"emailAddress": {"address": "ravi@customer.example"}}]
    assert "attachments" not in message
    assert receipt.provider == "graph"
    assert receipt.message_id.startswith("<") and receipt.message_id.endswith("@s3k.test>")


async def test_the_token_request_uses_client_credentials() -> None:
    graph = FakeGraph()
    graph.route("POST", "/sendMail", httpx.Response(202))

    await graph.service().send(_message())

    (token,) = graph.token_requests()
    assert str(token.url) == (
        "https://login.microsoftonline.com/tenant-123/oauth2/v2.0/token"
    )
    form = parse_qs(token.content.decode())
    assert form["grant_type"] == ["client_credentials"]
    assert form["client_id"] == ["client-456"]
    assert form["scope"] == ["https://graph.microsoft.com/.default"]


async def test_recipients_copies_reply_to_and_display_name_map_onto_graph() -> None:
    graph = FakeGraph()
    graph.route("POST", "/sendMail", httpx.Response(202))

    await graph.service().send(
        _message(
            to_addresses=("second@customer.example",),
            cc_addresses=("cc@customer.example",),
            bcc_addresses=("hidden@customer.example",),
            reply_to="rep@s3k.example.com",
            from_name="Ravi Menon",
            html_body="<p>Hello</p>",
            message_id="<abc@s3k.test>",
            in_reply_to="<parent@s3k.test>",
        )
    )

    (send,) = graph.matching(lambda r: str(r.url).endswith("/sendMail"))
    message = _json(send)["message"]
    assert [r["emailAddress"]["address"] for r in message["toRecipients"]] == [
        "ravi@customer.example",
        "second@customer.example",
    ]
    assert message["ccRecipients"] == [{"emailAddress": {"address": "cc@customer.example"}}]
    assert message["bccRecipients"] == [
        {"emailAddress": {"address": "hidden@customer.example"}}
    ]
    assert message["replyTo"] == [{"emailAddress": {"address": "rep@s3k.example.com"}}]
    # The address is always the configured mailbox; only the name varies.
    assert message["from"] == {"emailAddress": {"address": SENDER, "name": "Ravi Menon"}}
    # HTML wins when both bodies exist.
    assert message["body"] == {"contentType": "HTML", "content": "<p>Hello</p>"}
    assert {"name": MESSAGE_ID_HEADER, "value": "<abc@s3k.test>"} in message[
        "internetMessageHeaders"
    ]
    assert {"name": IN_REPLY_TO_HEADER, "value": "<parent@s3k.test>"} in message[
        "internetMessageHeaders"
    ]


async def test_blind_copies_never_appear_in_visible_recipient_fields() -> None:
    graph = FakeGraph()
    graph.route("POST", "/sendMail", httpx.Response(202))

    await graph.service().send(_message(bcc_addresses=("secret-bcc@customer.example",)))

    (send,) = graph.matching(lambda r: str(r.url).endswith("/sendMail"))
    message = _json(send)["message"]
    visible = json.dumps(
        [message.get("toRecipients"), message.get("ccRecipients"), message.get("replyTo")]
    )
    assert "secret-bcc" not in visible


async def test_small_attachments_are_sent_inline_as_file_attachments() -> None:
    graph = FakeGraph()
    graph.route("POST", "/sendMail", httpx.Response(202))
    content = b"%PDF-1.7 quote"

    await graph.service().send(
        _message(
            attachments=(
                EmailAttachment(filename="quote.pdf", mime_type="application/pdf", content=content),
            )
        )
    )

    (send,) = graph.matching(lambda r: str(r.url).endswith("/sendMail"))
    (attachment,) = _json(send)["message"]["attachments"]
    assert attachment == {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": "quote.pdf",
        "contentType": "application/pdf",
        "contentBytes": base64.b64encode(content).decode(),
    }


async def test_the_access_token_is_cached_between_sends() -> None:
    graph = FakeGraph()
    graph.route("POST", "/sendMail", httpx.Response(202))
    service = graph.service()

    await service.send(_message())
    await service.send(_message())

    assert len(graph.token_requests()) == 1


async def test_a_401_refreshes_the_token_and_retries_once() -> None:
    graph = FakeGraph()
    graph.route(
        "POST",
        "/sendMail",
        httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}}),
        httpx.Response(202),
    )

    await graph.service().send(_message())

    assert len(graph.token_requests()) == 2
    assert len(graph.matching(lambda r: str(r.url).endswith("/sendMail"))) == 2


async def test_a_persistent_401_is_a_permanent_rejection() -> None:
    graph = FakeGraph()
    graph.route(
        "POST",
        "/sendMail",
        httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken"}}),
    )

    with pytest.raises(EmailRejectedError, match="HTTP 401"):
        await graph.service().send(_message())


# --- Failure classification ------------------------------------------------------


@pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504])
async def test_throttling_and_outages_are_transient(status_code: int) -> None:
    graph = FakeGraph()
    graph.route(
        "POST",
        "/sendMail",
        httpx.Response(status_code, json={"error": {"code": "ServiceUnavailable"}}),
    )

    with pytest.raises(EmailTransientError, match=f"HTTP {status_code}"):
        await graph.service().send(_message())


@pytest.mark.parametrize(
    ("status_code", "code"),
    [
        (400, "ErrorInvalidRecipients"),
        (403, "ErrorAccessDenied"),
        (404, "ErrorInvalidUser"),
        (413, "RequestEntityTooLarge"),
    ],
)
async def test_refusals_are_permanent_and_name_graphs_error_code(
    status_code: int, code: str
) -> None:
    graph = FakeGraph()
    graph.route(
        "POST",
        "/sendMail",
        httpx.Response(
            status_code,
            json={"error": {"code": code, "message": "details that may echo the request"}},
        ),
    )

    with pytest.raises(EmailRejectedError) as raised:
        await graph.service().send(_message())

    assert code in str(raised.value)
    assert "echo the request" not in str(raised.value)
    assert isinstance(raised.value, PERMANENT_EMAIL_FAILURES)


async def test_a_rejected_client_secret_is_permanent_and_leaks_nothing() -> None:
    graph = FakeGraph(
        token_status=401,
        token_body={
            "error": "invalid_client",
            "error_description": f"AADSTS7000215: Invalid client secret {SECRET}",
        },
    )

    with pytest.raises(EmailRejectedError) as raised:
        await graph.service().send(_message())

    text = str(raised.value)
    assert "invalid_client" in text
    assert SECRET not in text
    assert "AADSTS" not in text
    assert not graph.matching(lambda r: "graph.microsoft.com" in str(r.url))


async def test_an_entra_id_outage_is_transient() -> None:
    graph = FakeGraph(token_status=503, token_body={})

    with pytest.raises(EmailTransientError):
        await graph.service().send(_message())


async def test_a_network_failure_is_transient_and_leaks_nothing() -> None:
    graph = FakeGraph()
    graph.route("POST", "/sendMail", httpx.Response(202))
    graph.raise_on = ("POST", "/sendMail")

    with pytest.raises(EmailTransientError) as raised:
        await graph.service().send(_message())

    assert TOKEN not in str(raised.value)
    assert SECRET not in str(raised.value)


async def test_a_malformed_token_response_is_not_treated_as_success() -> None:
    graph = FakeGraph(token_body={"token_type": "Bearer"})

    with pytest.raises(EmailTransientError):
        await graph.service().send(_message())


@pytest.mark.parametrize(
    "missing",
    [
        "microsoft_tenant_id",
        "microsoft_client_id",
        "microsoft_client_secret",
        "microsoft_graph_sender_email",
    ],
)
async def test_an_incomplete_configuration_fails_before_any_request(missing: str) -> None:
    graph = FakeGraph()
    settings = _settings(email_provider="null", **{missing: None})

    with pytest.raises(EmailNotConfiguredError, match=missing.upper()):
        await graph.service(settings).send(_message())

    assert graph.requests == []


def test_graph_error_code_reads_both_error_shapes() -> None:
    assert graph_error_code(httpx.Response(400, json={"error": {"code": "X"}})) == "X"
    assert graph_error_code(httpx.Response(400, json={"error": "invalid_client"})) == (
        "invalid_client"
    )
    assert graph_error_code(httpx.Response(500, text="<html>")) is None


# --- Large messages: draft, upload, send ------------------------------------------


def _large_attachment_routes(graph: FakeGraph) -> None:
    graph.route("POST", "/messages", httpx.Response(201, json={"id": "draft-1"}))
    graph.route("POST", "/messages/draft-1/attachments", httpx.Response(201, json={}))
    graph.route(
        "POST",
        "/messages/draft-1/attachments/createUploadSession",
        httpx.Response(201, json={"uploadUrl": "https://upload.example/session-1"}),
    )
    graph.route("PUT", "https://upload.example/session-1", httpx.Response(200, json={}))
    graph.route("POST", "/messages/draft-1/send", httpx.Response(202))
    graph.route("DELETE", "/messages/draft-1", httpx.Response(204))


async def test_a_message_over_the_inline_budget_goes_through_a_draft() -> None:
    graph = FakeGraph()
    _large_attachment_routes(graph)
    small = EmailAttachment(filename="a.txt", mime_type="text/plain", content=b"a" * 1024)
    large = EmailAttachment(
        filename="deck.pdf",
        mime_type="application/pdf",
        content=b"x" * (UPLOAD_CHUNK_BYTES * 2 + 100),
    )
    message = _message(attachments=(small, large))

    await graph.service().send(message)

    urls = [(r.method, str(r.url)) for r in graph.requests if "login." not in str(r.url)]
    assert urls[0] == ("POST", f"{MAILBOX}/messages")
    assert ("POST", f"{MAILBOX}/messages/draft-1/attachments") in urls
    assert ("POST", f"{MAILBOX}/messages/draft-1/attachments/createUploadSession") in urls
    assert urls[-1] == ("POST", f"{MAILBOX}/messages/draft-1/send")
    assert not graph.matching(lambda r: str(r.url).endswith("/sendMail"))

    draft = _json(graph.requests[1])
    assert "attachments" not in draft
    assert draft["toRecipients"] == [{"emailAddress": {"address": "ravi@customer.example"}}]

    session = _json(
        graph.matching(lambda r: str(r.url).endswith("/createUploadSession"))[0]
    )
    assert session["AttachmentItem"]["size"] == len(large.content)

    puts = graph.matching(lambda r: r.method == "PUT")
    assert len(puts) == 3
    total = len(large.content)
    assert puts[0].headers["Content-Range"] == f"bytes 0-{UPLOAD_CHUNK_BYTES - 1}/{total}"
    assert puts[-1].headers["Content-Range"] == (
        f"bytes {UPLOAD_CHUNK_BYTES * 2}-{total - 1}/{total}"
    )
    # The upload URL is pre-authenticated; a bearer token there is refused.
    assert all("Authorization" not in put.headers for put in puts)
    assert b"".join(put.content for put in puts) == large.content


async def test_a_failed_upload_deletes_the_draft_and_is_classified() -> None:
    graph = FakeGraph()
    _large_attachment_routes(graph)
    graph.route(
        "PUT",
        "https://upload.example/session-1",
        httpx.Response(503, json={"error": {"code": "serviceNotAvailable"}}),
    )
    large = EmailAttachment(
        filename="deck.pdf",
        mime_type="application/pdf",
        content=b"x" * (SINGLE_REQUEST_ATTACHMENT_BYTES + 1) * 2,
    )

    with pytest.raises(EmailTransientError):
        await graph.service().send(_message(attachments=(large,)))

    assert graph.matching(
        lambda r: r.method == "DELETE" and str(r.url) == f"{MAILBOX}/messages/draft-1"
    )
    assert not graph.matching(lambda r: str(r.url).endswith("/send"))


def test_the_inline_estimate_accounts_for_base64_growth() -> None:
    content = b"x" * 3000
    estimate = estimated_inline_request_bytes(
        _message(attachments=(EmailAttachment("f", "text/plain", content),))
    )
    assert estimate >= 4000


# --- Provider selection -----------------------------------------------------------


def test_build_provider_selects_graph_console_or_null() -> None:
    assert isinstance(build_provider(_settings()), GraphEmailService)
    assert isinstance(build_provider(_settings(email_provider="console")), ConsoleProvider)
    assert isinstance(
        build_provider(
            _settings(
                email_provider="null",
                microsoft_tenant_id=None,
                microsoft_client_id=None,
                microsoft_client_secret=None,
                microsoft_graph_sender_email=None,
            )
        ),
        NullProvider,
    )


async def test_the_null_provider_fails_permanently() -> None:
    with pytest.raises(EmailNotConfiguredError, match="EMAIL_PROVIDER=graph"):
        await NullProvider().send(_message())
