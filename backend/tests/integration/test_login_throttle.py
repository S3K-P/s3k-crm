"""Per-address throttling on the credential endpoints.

The account lockout already tested in ``test_auth_flow`` stops one account
being guessed repeatedly. It is blind to the attack that actually happens:
one password tried against a thousand accounts, where every account sees a
single failure and none of them ever locks. These tests are about that second
attack, and about the ways a limiter can be made useless.

Redis is real here, not faked. The limiter's whole behaviour is Redis
semantics — ``INCR`` creating a key, ``EXPIRE`` bounding it, a TTL that has to
survive a second call — and a fake would be asserting my own idea of Redis
rather than Redis.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from redis import Redis as SyncRedis

from app.core.config import Settings
from app.platform.auth.throttle import AUTH_BUCKET
from tests.integration.conftest import TEST_PASSWORD, Tenant

pytestmark = pytest.mark.integration

LOGIN = "/auth/login"
SIGNUP = "/auth/signup"

#: Our edge proxy's view of the caller. Everything left of this in
#: ``X-Forwarded-For`` is client-written and must not affect the bucket.
EDGE = "203.0.113.9"


def _forwarded(client_claim: str = "9.9.9.9", edge: str = EDGE) -> dict[str, str]:
    """Headers as Railway's proxy would present them."""
    return {"X-Forwarded-For": f"{client_claim}, {edge}"}


@pytest.fixture
def api(integration_settings: Settings) -> str:
    return integration_settings.api_prefix


@pytest.fixture(autouse=True)
def _clear_buckets(integration_settings: Settings) -> Iterator[None]:
    """Empty the limiter's keys around every test.

    Buckets outlive a test run — the window is five minutes — so without this
    a second run inside that window inherits the first one's exhausted budgets
    and fails for reasons that have nothing to do with what it asserts.

    A synchronous client on purpose: these tests drive the app through
    ``TestClient`` and are themselves synchronous, so an async fixture would
    need an event loop that the test does not have.
    """
    def clear() -> None:
        redis = SyncRedis.from_url(integration_settings.redis_url, decode_responses=True)
        try:
            keys = list(redis.scan_iter(f"ratelimit:{AUTH_BUCKET}:*"))
            if keys:
                redis.delete(*keys)
        finally:
            redis.close()

    clear()
    yield
    # Cleared afterwards too, so a failing test does not poison the next file.
    clear()


def _login(
    client: TestClient, api: str, email: str, password: str, **kwargs: Any
) -> Response:
    return client.post(
        f"{api}{LOGIN}", json={"email": email, "password": password}, **kwargs
    )


# --- The attack the lockout cannot see --------------------------------------


def test_one_address_working_through_many_accounts_is_throttled(
    client: TestClient, api: str, integration_settings: Settings, alpha: Tenant
) -> None:
    """Credential stuffing, and the reason this module exists.

    Every attempt below names a *different* account, so no account ever
    approaches its own lockout threshold. Only a per-address control can stop
    this, and the response must be 429 rather than another 401 — a 401 would
    tell the attacker to keep going.
    """
    limit = integration_settings.login_rate_limit_attempts
    headers = _forwarded()

    statuses = [
        _login(
            client, api, f"victim-{index}-{uuid.uuid4().hex[:8]}@example.com",
            "Wr0ngPassphrase!", headers=headers,
        ).status_code
        for index in range(limit + 5)
    ]

    assert statuses[0] == 401, "the first attempt is a normal rejection"
    assert 429 in statuses, "the address must eventually be refused outright"
    assert statuses[-1] == 429, "and stay refused for the rest of the window"


def test_the_refusal_says_nothing_about_the_account(
    client: TestClient, api: str, integration_settings: Settings, alpha: Tenant
) -> None:
    """A throttled response for a real account and a fictional one is identical.

    If the 429 body differed, the limit would become an oracle: an attacker
    could burn their budget deliberately and then read account existence off
    the refusals.
    """
    limit = integration_settings.login_rate_limit_attempts
    headers = _forwarded("9.9.9.9", "203.0.113.11")
    for _ in range(limit + 1):
        _login(client, api, "nobody@example.com", "Wr0ngPassphrase!", headers=headers)

    real = _login(client, api, alpha.admin.email, "Wr0ngPassphrase!", headers=headers)
    fake = _login(client, api, "ghost@example.com", "Wr0ngPassphrase!", headers=headers)

    assert real.status_code == fake.status_code == 429
    assert real.json()["error"]["code"] == fake.json()["error"]["code"] == "too_many_attempts"
    assert real.json()["error"]["message"] == fake.json()["error"]["message"]


def test_a_throttled_caller_is_told_when_to_come_back(
    client: TestClient, api: str, integration_settings: Settings
) -> None:
    limit = integration_settings.login_rate_limit_attempts
    headers = _forwarded("9.9.9.9", "203.0.113.12")
    for _ in range(limit + 1):
        _login(client, api, "nobody@example.com", "Wr0ngPassphrase!", headers=headers)

    refused = _login(client, api, "nobody@example.com", "Wr0ngPassphrase!", headers=headers)

    assert refused.status_code == 429
    retry_after = refused.json()["error"]["details"]["retry_after_seconds"]
    assert 0 < retry_after <= integration_settings.login_rate_limit_window_seconds


# --- Forgery resistance, end to end -----------------------------------------


def test_rotating_the_forwarded_header_does_not_buy_a_fresh_budget(
    client: TestClient, api: str, integration_settings: Settings
) -> None:
    """The end-to-end version of the unit tests on address selection.

    A different claimed client address on every request, but the same edge
    proxy entry — which is what a real attacker's traffic looks like. If the
    limiter keyed on the left-most entry, every one of these would be attempt
    number one and the response would never be 429.
    """
    limit = integration_settings.login_rate_limit_attempts
    edge = "203.0.113.13"

    statuses = [
        _login(
            client, api, "nobody@example.com", "Wr0ngPassphrase!",
            headers={"X-Forwarded-For": f"10.0.0.{index % 250}, {edge}"},
        ).status_code
        for index in range(limit + 3)
    ]

    assert 429 in statuses


def test_two_different_networks_do_not_share_a_budget(
    client: TestClient, api: str, integration_settings: Settings
) -> None:
    """One customer's office being attacked must not lock out another's.

    The mirror image of the test above: the limit has to be *specific* as well
    as unforgeable, or it becomes a denial-of-service tool.
    """
    limit = integration_settings.login_rate_limit_attempts
    for _ in range(limit + 1):
        _login(
            client, api, "nobody@example.com", "Wr0ngPassphrase!",
            headers=_forwarded("9.9.9.9", "203.0.113.20"),
        )

    other_office = _login(
        client, api, "nobody@example.com", "Wr0ngPassphrase!",
        headers=_forwarded("9.9.9.9", "203.0.113.21"),
    )

    assert other_office.status_code == 401, "a different address still gets a normal answer"


# --- Not punishing the innocent ---------------------------------------------


def test_a_successful_sign_in_clears_the_address(
    client: TestClient, api: str, integration_settings: Settings, alpha: Tenant
) -> None:
    """A shared office address must not be spent by one person's typos.

    Someone mistyping their password several times, then getting it right,
    leaves the floor's budget intact — a successful authentication is the
    strongest evidence available that this address is not an attacker.

    The failures below name accounts that do not exist, deliberately: aiming
    them at the admin would trip the *account* lockout after five and the test
    would then be measuring the wrong control.
    """
    headers = _forwarded("9.9.9.9", "203.0.113.30")
    limit = integration_settings.login_rate_limit_attempts

    for index in range(limit - 1):
        _login(
            client, api, f"typo-{index}@example.com", "Wr0ngPassphrase!", headers=headers
        )

    ok = _login(client, api, alpha.admin.email, TEST_PASSWORD, headers=headers)
    assert ok.status_code == 200, ok.text

    # The counter was reset, so a colleague on the same address gets the full
    # budget rather than one attempt.
    after = [
        _login(
            client, api, f"colleague-{index}@example.com", "Wr0ngPassphrase!",
            headers=headers,
        ).status_code
        for index in range(limit - 1)
    ]
    assert 429 not in after


def test_the_throttle_does_not_replace_the_account_lockout(
    client: TestClient, api: str, integration_settings: Settings, alpha: Tenant
) -> None:
    """Both controls, and they are independent.

    Guessing one account from *many* addresses defeats the throttle by design
    — it is per address — and must still hit the per-account lockout. This
    pins that adding the throttle did not let anybody quietly weaken the
    control that was already there.
    """
    attempts = integration_settings.login_max_failed_attempts + 1
    for index in range(attempts):
        _login(
            client, api, alpha.manager.email, "Wr0ngPassphrase!",
            headers=_forwarded("9.9.9.9", f"198.51.100.{index + 40}"),
        )

    # Correct password, brand-new address: the throttle has nothing to say, so
    # anything other than a rejection here means the lockout stopped working.
    # 423 rather than 401 — the lockout has its own status, so that somebody
    # who is locked out is told to wait rather than left retrying a password
    # they know is right.
    locked = _login(
        client, api, alpha.manager.email, TEST_PASSWORD,
        headers=_forwarded("9.9.9.9", "198.51.100.200"),
    )

    assert locked.status_code == 423
    assert locked.json()["error"]["code"] == "account_locked"


# --- Coverage of the other credential route ---------------------------------


def test_signup_shares_the_budget_with_login(
    client: TestClient, api: str, integration_settings: Settings
) -> None:
    """One bucket for both, so alternating routes cannot double the budget."""
    limit = integration_settings.login_rate_limit_attempts
    headers = _forwarded("9.9.9.9", "203.0.113.40")

    for _ in range(limit):
        _login(client, api, "nobody@example.com", "Wr0ngPassphrase!", headers=headers)

    refused = client.post(
        f"{api}{SIGNUP}",
        json={
            "email": f"new-{uuid.uuid4().hex[:8]}@example.com",
            "password": TEST_PASSWORD,
            "first_name": "New",
            "last_name": "Person",
        },
        headers=headers,
    )

    assert refused.status_code == 429, refused.text


def test_refresh_is_deliberately_not_throttled(
    client: TestClient, api: str, integration_settings: Settings, alpha: Tenant
) -> None:
    """Documented exemption, pinned so it is not "fixed" by accident.

    Refresh needs an unguessable rotating token and has its own reuse
    detection. Throttling it by address would let one attacker on a shared
    network log everybody else out by exhausting the budget.
    """
    headers = _forwarded("9.9.9.9", "203.0.113.50")
    signed_in = _login(client, api, alpha.admin.email, TEST_PASSWORD, headers=headers)
    assert signed_in.status_code == 200, signed_in.text

    limit = integration_settings.login_rate_limit_attempts
    for _ in range(limit + 2):
        _login(client, api, "nobody@example.com", "Wr0ngPassphrase!", headers=headers)

    refreshed = client.post(f"{api}/auth/refresh", json={}, headers=headers)

    assert refreshed.status_code == 200, refreshed.text
