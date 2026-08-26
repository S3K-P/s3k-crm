"""Authentication behaviour against the real database (P1-W04-QA-01, P1-W05-QA-01)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import TEST_PASSWORD, ApiSession, Tenant

pytestmark = pytest.mark.integration


def _login(client: TestClient, prefix: str, email: str, password: str):  # noqa: ANN202
    return client.post(f"{prefix}/auth/login", json={"email": email, "password": password})


# --- Login ------------------------------------------------------------------


def test_login_with_valid_credentials_returns_an_access_token(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    response = _login(
        client, integration_settings.api_prefix, alpha.admin.email, TEST_PASSWORD
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["organization_id"] == str(alpha.organization_id)


def test_login_sets_the_refresh_token_as_an_httponly_cookie(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """The refresh token must be unreadable by script (SEC01)."""
    response = _login(
        client, integration_settings.api_prefix, alpha.admin.email, TEST_PASSWORD
    )

    cookie = response.headers.get("set-cookie", "")
    assert integration_settings.refresh_cookie_name in cookie
    assert "HttpOnly" in cookie


def test_the_refresh_token_never_appears_in_the_response_body(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    response = _login(
        client, integration_settings.api_prefix, alpha.admin.email, TEST_PASSWORD
    )

    assert "refresh_token" not in response.json()


def test_login_with_a_wrong_password_is_rejected(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    response = _login(
        client, integration_settings.api_prefix, alpha.admin.email, "WrongPassword123"
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_an_unknown_address_is_indistinguishable_from_a_wrong_password(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """The endpoint must not be usable to enumerate registered addresses."""
    unknown = _login(
        client, integration_settings.api_prefix, "nobody@alpha.example", TEST_PASSWORD
    )
    wrong = _login(
        client, integration_settings.api_prefix, alpha.admin.email, "WrongPassword123"
    )

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_the_password_hash_is_never_returned_by_the_api(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.get("/auth/me")

    assert response.status_code == 200
    assert "password" not in response.text.lower()


# --- Brute-force protection -------------------------------------------------


def test_repeated_failures_lock_the_account(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """After the configured threshold the account is locked, not merely denied."""
    prefix = integration_settings.api_prefix
    for _ in range(integration_settings.login_max_failed_attempts):
        _login(client, prefix, alpha.member.email, "WrongPassword123")

    # Even the *correct* password is refused while the lock holds.
    response = _login(client, prefix, alpha.member.email, TEST_PASSWORD)

    assert response.status_code == 423
    assert response.json()["error"]["code"] == "account_locked"


def test_a_successful_login_clears_earlier_failures(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    prefix = integration_settings.api_prefix
    for _ in range(integration_settings.login_max_failed_attempts - 1):
        _login(client, prefix, alpha.manager.email, "WrongPassword123")

    assert _login(client, prefix, alpha.manager.email, TEST_PASSWORD).status_code == 200
    # The counter reset, so a fresh run of failures is needed to lock.
    for _ in range(integration_settings.login_max_failed_attempts - 1):
        _login(client, prefix, alpha.manager.email, "WrongPassword123")
    assert _login(client, prefix, alpha.manager.email, TEST_PASSWORD).status_code == 200


# --- Protected endpoints ----------------------------------------------------


def test_a_protected_endpoint_rejects_a_request_with_no_token(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    response = client.get(f"{integration_settings.api_prefix}/auth/me")

    assert response.status_code == 401


def test_a_protected_endpoint_rejects_a_garbage_token(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    response = client.get(
        f"{integration_settings.api_prefix}/auth/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401


def test_a_token_signed_by_another_key_is_rejected(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """Guards against accepting an unsigned or foreign-signed JWT."""
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    attacker_key = ed25519.Ed25519PrivateKey.generate().private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    forged = jwt.encode(
        {
            "sub": str(alpha.admin.user_id),
            "sid": str(uuid.uuid4()),
            "org": str(alpha.organization_id),
            "typ": "access",
            "iss": integration_settings.jwt_issuer,
            "aud": integration_settings.jwt_audience,
            "iat": 1,
            "exp": 9_999_999_999,
        },
        attacker_key,
        algorithm="EdDSA",
    )

    response = client.get(
        f"{integration_settings.api_prefix}/auth/me",
        headers={"Authorization": f"Bearer {forged}"},
    )

    assert response.status_code == 401


def test_me_returns_memberships_and_effective_permissions(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    response = as_alpha_admin.get("/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == alpha.admin.email
    assert body["active_organization_id"] == str(alpha.organization_id)
    assert [m["organization_id"] for m in body["memberships"]] == [
        str(alpha.organization_id)
    ]
    assert "Admin" in body["memberships"][0]["roles"]
    # Admin holds the whole catalogue.
    assert "leads.DELETE" in body["permissions"]


def test_permissions_differ_per_role(as_alpha_member: ApiSession) -> None:
    body = as_alpha_member.get("/auth/me").json()

    assert "leads.CREATE" in body["permissions"]
    assert "leads.DELETE" not in body["permissions"]


# --- Refresh rotation and reuse detection -----------------------------------


def test_refresh_issues_a_new_access_token(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    prefix = integration_settings.api_prefix
    _login(client, prefix, alpha.admin.email, TEST_PASSWORD)

    response = client.post(f"{prefix}/auth/refresh", json={})

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_replaying_a_rotated_refresh_token_is_rejected(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """Reuse detection: a token already exchanged must never work again."""
    prefix = integration_settings.api_prefix
    _login(client, prefix, alpha.admin.email, TEST_PASSWORD)
    stolen = client.cookies.get(integration_settings.refresh_cookie_name)
    assert stolen is not None

    assert client.post(f"{prefix}/auth/refresh", json={}).status_code == 200

    # The endpoint prefers the cookie, which now holds the *rotated* token.
    # Clearing it is what makes this an actual replay of the stolen one.
    client.cookies.clear()
    replay = client.post(f"{prefix}/auth/refresh", json={"refresh_token": stolen})

    assert replay.status_code == 401


def test_replay_revokes_the_whole_token_family(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """A stolen token must not leave the legitimate session usable either."""
    prefix = integration_settings.api_prefix
    cookie_name = integration_settings.refresh_cookie_name

    _login(client, prefix, alpha.admin.email, TEST_PASSWORD)
    stolen = client.cookies.get(cookie_name)
    assert stolen is not None

    client.post(f"{prefix}/auth/refresh", json={})  # legitimate rotation
    legitimate = client.cookies.get(cookie_name)
    assert legitimate is not None and legitimate != stolen

    client.cookies.clear()
    client.post(f"{prefix}/auth/refresh", json={"refresh_token": stolen})  # attacker

    # The legitimate holder's current token is collateral damage, by design.
    replay = client.post(f"{prefix}/auth/refresh", json={"refresh_token": legitimate})

    assert replay.status_code == 401


def test_logout_revokes_the_session(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    prefix = integration_settings.api_prefix
    _login(client, prefix, alpha.admin.email, TEST_PASSWORD)

    assert client.post(f"{prefix}/auth/logout").status_code == 204
    assert client.post(f"{prefix}/auth/refresh", json={}).status_code == 401


def test_logout_is_idempotent_and_never_leaks_token_validity(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    prefix = integration_settings.api_prefix

    assert client.post(f"{prefix}/auth/logout").status_code == 204
    assert client.post(f"{prefix}/auth/logout").status_code == 204
