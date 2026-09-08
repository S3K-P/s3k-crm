"""Which address the login throttle counts, and why it cannot be forged.

This is the whole security property of the throttle. The counting is
arithmetic; picking the *right* identity to count is the part an attacker
attacks, and getting it wrong makes the control decorative rather than merely
weak — an attacker who can choose their own key has an unlimited supply of
them.

``X-Forwarded-For`` grows left-to-right as a request crosses proxies, so its
left-most entry is whatever the original client wrote and its right-most was
written by the proxy nearest us. The tests below pin that we count from the
right, that a client cannot reach past our own hops, and that a chain shorter
than configured falls back to the socket peer rather than trusting a
client-written value.

The contrast worth holding in mind: ``app.core.request_context.client_address``
reads the *left-most* entry on purpose, because an audit record wants the
client's own claim. Two functions, two different jobs, and
``test_the_audit_address_and_the_throttle_address_disagree_on_purpose`` pins
that they are allowed to disagree.
"""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from app.core.rate_limit import (
    UNKNOWN_ADDRESS,
    client_address_for_limiting,
)
from app.core.request_context import client_address

#: What our own edge proxy would append for a request it received from 9.9.9.9.
EDGE = "203.0.113.7"


def _request(
    forwarded: str | None = None, *, peer: str | None = "198.51.100.1"
) -> Request:
    headers: dict[str, str] = {}
    if forwarded is not None:
        headers["x-forwarded-for"] = forwarded
    scope: dict[str, object] = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": Headers(headers).raw,
        "client": (peer, 51234) if peer else None,
        "scheme": "https",
        "server": ("testserver", 443),
        "query_string": b"",
    }
    return Request(scope)


# --- Counting from the right ------------------------------------------------


def test_one_proxy_yields_the_address_that_proxy_saw() -> None:
    """The standard deployment: Railway's edge is the only hop."""
    request = _request(f"9.9.9.9, {EDGE}")

    assert client_address_for_limiting(request, trusted_proxy_hops=1) == EDGE


def test_two_proxies_skip_both_of_ours() -> None:
    request = _request(f"9.9.9.9, {EDGE}, 10.0.0.5")

    assert client_address_for_limiting(request, trusted_proxy_hops=2) == EDGE


def test_no_proxy_ignores_the_header_entirely() -> None:
    """Exposed directly, the socket peer *is* the client and the header lies."""
    request = _request("9.9.9.9, 8.8.8.8", peer="198.51.100.1")

    assert client_address_for_limiting(request, trusted_proxy_hops=0) == "198.51.100.1"


# --- Resistance to forgery --------------------------------------------------


@pytest.mark.parametrize(
    "forged",
    [
        "1.1.1.1",
        "1.1.1.1, 2.2.2.2",
        "1.1.1.1, 2.2.2.2, 3.3.3.3, 4.4.4.4",
    ],
    ids=["one-entry", "two-entries", "many-entries"],
)
def test_an_attacker_cannot_change_their_bucket_by_prepending_entries(
    forged: str,
) -> None:
    """The point of the whole module.

    Whatever the client writes, our edge proxy appends the address it actually
    observed, and that is the entry counted. If this ever failed, an attacker
    would rotate ``X-Forwarded-For`` per request and never meet the limit.
    """
    request = _request(f"{forged}, {EDGE}")

    assert client_address_for_limiting(request, trusted_proxy_hops=1) == EDGE


def test_a_chain_shorter_than_configured_falls_back_to_the_socket_peer() -> None:
    """Two hops configured, one entry present: every entry is client-written.

    Reading entry zero here would trust the attacker's value. The socket peer
    is the honest answer, and it also makes the misconfiguration visible in the
    logs rather than silently disabling the limit.
    """
    request = _request("1.1.1.1", peer="198.51.100.1")

    assert client_address_for_limiting(request, trusted_proxy_hops=2) == "198.51.100.1"


def test_a_missing_header_behind_a_proxy_falls_back_to_the_socket_peer() -> None:
    request = _request(None, peer="198.51.100.1")

    assert client_address_for_limiting(request, trusted_proxy_hops=1) == "198.51.100.1"


# --- Canonicalisation -------------------------------------------------------


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        (" 203.0.113.7 ", "203.0.113.7"),
        ("203.0.113.7:443", "203.0.113.7"),
        ("[2001:db8::1]:443", "2001:db8::1"),
        ("2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
    ],
    ids=["whitespace", "ipv4-port", "ipv6-bracketed", "ipv6-long-form"],
)
def test_equivalent_spellings_share_one_bucket(written: str, expected: str) -> None:
    """Otherwise one address gets a fresh budget per spelling.

    An IPv6 address has many textual forms and an IPv4 octet tolerates leading
    zeros, so a limiter keyed on the raw string would hand an attacker several
    buckets for free.
    """
    request = _request(f"9.9.9.9, {written}")

    assert client_address_for_limiting(request, trusted_proxy_hops=1) == expected


def test_an_ambiguous_octal_octet_is_rejected_rather_than_guessed() -> None:
    """``203.0.113.007`` is refused, and falling back is the safe reading.

    Leading zeros make an octet ambiguous between decimal and octal, and
    parsers famously disagree — Python's ``ipaddress`` refuses it outright.
    Rather than normalising a value two systems would read differently, the
    entry is discarded and the socket peer used. The attacker gains nothing:
    the fallback is a bucket they do not control either.
    """
    request = _request("9.9.9.9, 203.0.113.007", peer="198.51.100.1")

    assert client_address_for_limiting(request, trusted_proxy_hops=1) == "198.51.100.1"


def test_a_value_that_is_not_an_address_falls_back_rather_than_becoming_a_key() -> None:
    """``unknown`` in the header must not become its own private bucket."""
    request = _request("9.9.9.9, not-an-address", peer="198.51.100.1")

    assert client_address_for_limiting(request, trusted_proxy_hops=1) == "198.51.100.1"


def test_with_no_address_at_all_everyone_shares_one_bucket() -> None:
    """The safe direction: stripping your address lands you in the busiest queue."""
    request = _request(None, peer=None)

    assert client_address_for_limiting(request, trusted_proxy_hops=1) == UNKNOWN_ADDRESS


# --- The two address functions are not interchangeable ----------------------


def test_the_audit_address_and_the_throttle_address_disagree_on_purpose() -> None:
    """One records what the client claimed; the other counts what we observed.

    Pinned because the obvious "cleanup" is to make both call one helper, and
    doing so would either put a forgeable value into the rate limiter or throw
    away the client's claim that the audit trail exists to record.
    """
    scope = _request(f"9.9.9.9, {EDGE}").scope

    assert client_address(scope) == "9.9.9.9"
    assert client_address_for_limiting(Request(scope), trusted_proxy_hops=1) == EDGE
