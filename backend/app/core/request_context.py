"""Per-request correlation context (doc 13 "Investigation: correlation IDs").

Carries the three facts an audit record needs about *how* a request arrived —
its correlation id, the client address and the user agent — without threading
them through every service signature.

Stored in a :mod:`contextvars` variable for the same reason
:mod:`app.core.tenant` is: a pure-ASGI middleware sets it in the task that runs
the endpoint, so the database session, the logger and any service reached from
the handler all read the same value.

**This context is descriptive, never authoritative.** Everything in it comes
from the client (headers, socket address) and it is used only for
correlation and forensics. No authorization decision may read it — the tenant
and the principal come from :mod:`app.core.tenant` and
``app.platform.auth.dependencies``, both of which verify what they accept.

An inbound ``X-Request-Id`` is honoured so a trace survives a reverse proxy,
but it is length-capped and stripped of anything outside a conservative
character set: it lands in a database column and in structured logs, and an
attacker-supplied value must not be able to forge log structure.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token
from dataclasses import dataclass

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Header carrying a correlation id across service hops.
REQUEST_ID_HEADER = "X-Request-Id"

#: Header a reverse proxy uses to report the original client address.
FORWARDED_FOR_HEADER = "X-Forwarded-For"

#: Fits comfortably in the audit column and in a log line.
MAX_REQUEST_ID_LENGTH = 64

#: IPv6 addresses reach 45 characters in their longest textual form.
MAX_IP_LENGTH = 45

MAX_USER_AGENT_LENGTH = 512

#: Anything else in an inbound request id is dropped. Deliberately narrow:
#: UUIDs, ULIDs and typical trace ids all fit.
_REQUEST_ID_ALLOWED = re.compile(r"[^A-Za-z0-9._:-]")

#: Pre-encoded response header name, lower-cased as ASGI requires.
_REQUEST_ID_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode("latin-1")


@dataclass(frozen=True, slots=True)
class RequestContext:
    """How the current request reached the application."""

    request_id: str
    ip_address: str | None = None
    user_agent: str | None = None


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "request_context", default=None
)


def get_request_context() -> RequestContext | None:
    """Return the current request's context, or ``None`` outside a request."""
    return _request_context.get()


def set_request_context(context: RequestContext | None) -> Token[RequestContext | None]:
    """Bind ``context`` for the current task. Returns a token for :func:`reset`."""
    return _request_context.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    _request_context.reset(token)


def sanitize_request_id(raw: str | None) -> str:
    """Return a safe correlation id, generating one when none was supplied.

    A client-supplied value is kept only after unsupported characters are
    removed and the result is truncated; an empty result falls back to a fresh
    UUID rather than to the empty string, so every request is correlatable.
    """
    if raw:
        cleaned = _REQUEST_ID_ALLOWED.sub("", raw)[:MAX_REQUEST_ID_LENGTH]
        if cleaned:
            return cleaned
    return str(uuid.uuid4())


def client_address(scope: Scope) -> str | None:
    """Best available client address for the request.

    ``X-Forwarded-For``'s left-most entry is preferred because the application
    is deployed behind a reverse proxy (doc 11), falling back to the socket
    peer. Neither is trustworthy for authorization — a client controls the
    header and the peer is the proxy — which is why this only ever reaches an
    audit record and a log line.
    """
    forwarded = _header_value(scope, FORWARDED_FOR_HEADER)
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first[:MAX_IP_LENGTH]

    client = scope.get("client")
    if client:
        return str(client[0])[:MAX_IP_LENGTH]
    return None


class RequestContextMiddleware:
    """Establish :class:`RequestContext` for every request.

    Pure ASGI, and installed *outside* the tenant middleware, so the
    correlation id is already bound while tenant resolution runs and its
    warnings can be traced back to the request that caused them.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        context = RequestContext(
            request_id=sanitize_request_id(_header_value(scope, REQUEST_ID_HEADER)),
            ip_address=client_address(scope),
            user_agent=(_header_value(scope, "User-Agent") or "")[:MAX_USER_AGENT_LENGTH]
            or None,
        )
        token = set_request_context(context)
        structlog.contextvars.bind_contextvars(request_id=context.request_id)

        async def send_with_request_id(message: Message) -> None:
            """Echo the correlation id back so a client can quote it in a report."""
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.append(
                    (_REQUEST_ID_HEADER_BYTES, context.request_id.encode("latin-1"))
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_context(token)
            structlog.contextvars.unbind_contextvars("request_id")


def _header_value(scope: Scope, name: str) -> str | None:
    """Case-insensitive header lookup against the raw ASGI scope."""
    wanted = name.lower().encode("latin-1")
    headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
    for key, value in headers:
        if key.lower() == wanted:
            return str(value.decode("latin-1"))
    return None


__all__ = [
    "FORWARDED_FOR_HEADER",
    "MAX_IP_LENGTH",
    "MAX_REQUEST_ID_LENGTH",
    "MAX_USER_AGENT_LENGTH",
    "REQUEST_ID_HEADER",
    "RequestContext",
    "RequestContextMiddleware",
    "client_address",
    "get_request_context",
    "reset_request_context",
    "sanitize_request_id",
    "set_request_context",
]
