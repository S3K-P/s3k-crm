"""Correlation context: what is accepted from a client, and what is not.

``request_id`` is the one field of an audit record that originates with the
caller. It is written into a database column, echoed back in a response header
and merged into every structured log line for the request — three places where
an unfiltered client string would be a problem — so the sanitiser is the piece
worth testing hardest.

The client address is here for the opposite reason: it is *not* trustworthy,
and these tests pin that it is only ever descriptive. Nothing authorizes on it.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.request_context import (
    MAX_REQUEST_ID_LENGTH,
    REQUEST_ID_HEADER,
    client_address,
    get_request_context,
    sanitize_request_id,
)


def _scope(headers: dict[str, str], *, client: tuple[str, int] | None = None) -> dict[str, object]:
    return {
        "type": "http",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in headers.items()
        ],
        "client": client,
    }


# --- Sanitising an inbound correlation id -----------------------------------


def test_a_well_formed_id_from_a_proxy_is_honoured() -> None:
    """A trace must survive the hop, or correlation across services is lost."""
    supplied = str(uuid.uuid4())

    assert sanitize_request_id(supplied) == supplied


def test_a_missing_id_produces_a_fresh_one() -> None:
    """Every request must be correlatable, including the ones nobody tagged."""
    generated = sanitize_request_id(None)

    assert uuid.UUID(generated)


@pytest.mark.parametrize(
    "hostile",
    [
        'evil" injected="yes',
        "line\nbreak",
        "carriage\rreturn",
        "null\x00byte",
        "<script>alert(1)</script>",
        "tab\tseparated",
    ],
)
def test_characters_that_could_forge_log_structure_are_stripped(hostile: str) -> None:
    """The id lands in a JSON log line and a response header.

    A newline is the one that matters: without this it would let a caller
    append an entirely fabricated log record after their own.
    """
    cleaned = sanitize_request_id(hostile)

    assert not any(character in cleaned for character in '\n\r\t"<>\x00')


def test_an_over_long_id_is_truncated_to_the_column_width() -> None:
    cleaned = sanitize_request_id("a" * 500)

    assert len(cleaned) == MAX_REQUEST_ID_LENGTH


def test_an_id_of_nothing_but_rejected_characters_falls_back_to_a_new_one() -> None:
    """Truncating to the empty string would leave the request uncorrelatable."""
    cleaned = sanitize_request_id("<<<>>>")

    assert uuid.UUID(cleaned)


# --- Client address ---------------------------------------------------------


def test_the_forwarded_header_wins_over_the_socket_peer() -> None:
    """Behind a reverse proxy the socket peer is the proxy, not the client."""
    scope = _scope({"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}, client=("10.0.0.1", 5000))

    assert client_address(scope) == "203.0.113.7"


def test_the_socket_peer_is_used_when_nothing_was_forwarded() -> None:
    assert client_address(_scope({}, client=("198.51.100.4", 5000))) == "198.51.100.4"


def test_no_address_is_reported_rather_than_a_placeholder() -> None:
    """``NULL`` in the column is honest; ``"unknown"`` would be a fake address."""
    assert client_address(_scope({}, client=None)) is None


def test_an_over_long_forwarded_value_cannot_overflow_the_column() -> None:
    """``ip_address`` is ``VARCHAR(45)`` — an IPv6 address at its longest."""
    address = client_address(_scope({"X-Forwarded-For": "9" * 400}))

    assert address is not None
    assert len(address) <= 45


# --- Through the real middleware --------------------------------------------


def test_a_request_id_is_bound_for_the_duration_of_a_request(client: TestClient) -> None:
    """Proves the contextvar is set in the task that runs the endpoint.

    ``BaseHTTPMiddleware`` would run the handler in a separate task and the
    value would not propagate — which is exactly why the middleware is written
    as raw ASGI, and why this is asserted rather than assumed.
    """
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]


def test_the_supplied_correlation_id_is_echoed_back(client: TestClient) -> None:
    supplied = str(uuid.uuid4())

    response = client.get("/health", headers={REQUEST_ID_HEADER: supplied})

    assert response.headers[REQUEST_ID_HEADER] == supplied


def test_the_context_does_not_leak_past_the_request(client: TestClient) -> None:
    """A pooled worker must not carry one caller's id into the next request."""
    client.get("/health", headers={REQUEST_ID_HEADER: "leaked-id"})

    assert get_request_context() is None
