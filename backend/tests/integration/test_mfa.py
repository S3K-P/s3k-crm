"""Multi-factor authentication against the real database (Checkpoint 8).

Assumes ``backend/.env`` has ``MFA_ENCRYPTION_KEY`` set — the same
requirement every other environment-gated integration test here has (see
``s3k-minio-random-credentials`` for the attachment tests' equivalent). A
deployment with no key still gets exercised indirectly: every unit test in
``tests/unit/test_mfa.py`` covers ``MfaNotConfiguredError`` directly, no
database required.
"""

from __future__ import annotations

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import TEST_PASSWORD, ApiSession, Tenant

pytestmark = pytest.mark.integration


def _login(client: TestClient, prefix: str, email: str, password: str = TEST_PASSWORD):  # noqa: ANN202
    return client.post(f"{prefix}/auth/login", json={"email": email, "password": password})


def _enroll(session: ApiSession) -> dict[str, object]:
    response = session.post("/auth/mfa/enroll")
    assert response.status_code == 201, response.text
    return response.json()


def _enroll_and_confirm(session: ApiSession) -> tuple[str, list[str]]:
    """Returns ``(secret, recovery_codes)`` for an account MFA is now active on."""
    body = _enroll(session)
    secret = body["secret"]
    code = pyotp.TOTP(secret).now()
    confirmed = session.post("/auth/mfa/enroll/confirm", json={"code": code})
    assert confirmed.status_code == 204, confirmed.text
    return secret, body["recovery_codes"]


# --- Enrollment ---------------------------------------------------------------


def test_status_starts_disabled(as_alpha_admin: ApiSession) -> None:
    body = as_alpha_admin.get("/auth/mfa/status").json()

    assert body == {"enabled": False, "pending": False}


def test_enrolling_returns_a_secret_and_ten_recovery_codes_once(
    as_alpha_admin: ApiSession,
) -> None:
    body = _enroll(as_alpha_admin)

    assert body["secret"]
    assert body["provisioning_uri"].startswith("otpauth://totp/")
    assert len(body["recovery_codes"]) == 10
    assert len(set(body["recovery_codes"])) == 10


def test_enrolling_leaves_status_pending_not_enabled(as_alpha_admin: ApiSession) -> None:
    _enroll(as_alpha_admin)

    body = as_alpha_admin.get("/auth/mfa/status").json()
    assert body == {"enabled": False, "pending": True}


def test_confirming_with_the_right_code_enables_it(as_alpha_admin: ApiSession) -> None:
    _enroll_and_confirm(as_alpha_admin)

    body = as_alpha_admin.get("/auth/mfa/status").json()
    assert body == {"enabled": True, "pending": False}


def test_confirming_with_a_wrong_code_is_refused_and_leaves_it_pending(
    as_alpha_admin: ApiSession,
) -> None:
    _enroll(as_alpha_admin)

    response = as_alpha_admin.post("/auth/mfa/enroll/confirm", json={"code": "000000"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_mfa_code"
    assert as_alpha_admin.get("/auth/mfa/status").json() == {"enabled": False, "pending": True}


def test_confirming_with_nothing_pending_is_a_conflict(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post("/auth/mfa/enroll/confirm", json={"code": "000000"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_enrolling_again_while_already_enabled_is_a_conflict(as_alpha_admin: ApiSession) -> None:
    _enroll_and_confirm(as_alpha_admin)

    response = as_alpha_admin.post("/auth/mfa/enroll")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_re_enrolling_while_only_pending_replaces_the_secret(as_alpha_admin: ApiSession) -> None:
    """An abandoned enrollment is not a lock-out — starting over is allowed."""
    first = _enroll(as_alpha_admin)
    second = _enroll(as_alpha_admin)

    assert first["secret"] != second["secret"]
    # The first secret's code no longer confirms anything real.
    stale_code = pyotp.TOTP(first["secret"]).now()
    response = as_alpha_admin.post("/auth/mfa/enroll/confirm", json={"code": stale_code})
    assert response.status_code == 401


# --- Login now requires a challenge --------------------------------------------


def test_login_with_mfa_enabled_returns_a_challenge_not_tokens(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    _enroll_and_confirm(as_alpha_admin)

    response = _login(client, integration_settings.api_prefix, alpha.admin.email)

    assert response.status_code == 200
    body = response.json()
    assert body["mfa_required"] is True
    assert body["mfa_challenge_token"]
    assert "access_token" not in body
    assert integration_settings.refresh_cookie_name not in response.headers.get("set-cookie", "")


def test_verifying_with_the_right_totp_code_completes_login(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    secret, _ = _enroll_and_confirm(as_alpha_admin)
    prefix = integration_settings.api_prefix
    challenge = _login(client, prefix, alpha.admin.email).json()["mfa_challenge_token"]

    response = client.post(
        f"{prefix}/auth/mfa/verify",
        json={"mfa_challenge_token": challenge, "code": pyotp.TOTP(secret).now()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert integration_settings.refresh_cookie_name in response.headers.get("set-cookie", "")

    # The session this produced actually works.
    me = client.get(
        f"{prefix}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["user"]["email"] == alpha.admin.email


def test_verifying_with_a_wrong_code_is_refused(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    _enroll_and_confirm(as_alpha_admin)
    prefix = integration_settings.api_prefix
    challenge = _login(client, prefix, alpha.admin.email).json()["mfa_challenge_token"]

    response = client.post(
        f"{prefix}/auth/mfa/verify",
        json={"mfa_challenge_token": challenge, "code": "000000"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_mfa_code"


def test_a_challenge_token_cannot_be_used_as_a_bearer_token(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Only a real access token from /verify may call an authenticated route."""
    _enroll_and_confirm(as_alpha_admin)
    prefix = integration_settings.api_prefix
    challenge = _login(client, prefix, alpha.admin.email).json()["mfa_challenge_token"]

    response = client.get(f"{prefix}/auth/me", headers={"Authorization": f"Bearer {challenge}"})

    assert response.status_code == 401


def test_a_recovery_code_completes_login_exactly_once(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    _, recovery_codes = _enroll_and_confirm(as_alpha_admin)
    prefix = integration_settings.api_prefix
    recovery_code = recovery_codes[0]

    first_challenge = _login(client, prefix, alpha.admin.email).json()["mfa_challenge_token"]
    first = client.post(
        f"{prefix}/auth/mfa/verify",
        json={"mfa_challenge_token": first_challenge, "code": recovery_code},
    )
    assert first.status_code == 200, first.text

    second_challenge = _login(client, prefix, alpha.admin.email).json()["mfa_challenge_token"]
    second = client.post(
        f"{prefix}/auth/mfa/verify",
        json={"mfa_challenge_token": second_challenge, "code": recovery_code},
    )
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "invalid_mfa_code"


def test_repeated_wrong_mfa_codes_lock_the_account(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """The same account-lockout counter a wrong password trips."""
    _enroll_and_confirm(as_alpha_admin)
    prefix = integration_settings.api_prefix

    for _ in range(integration_settings.login_max_failed_attempts):
        challenge = _login(client, prefix, alpha.admin.email).json()["mfa_challenge_token"]
        client.post(
            f"{prefix}/auth/mfa/verify",
            json={"mfa_challenge_token": challenge, "code": "000000"},
        )

    # Even a correct password no longer reaches the MFA step while locked.
    response = _login(client, prefix, alpha.admin.email)
    assert response.status_code == 423
    assert response.json()["error"]["code"] == "account_locked"


# --- Disabling ------------------------------------------------------------------


def test_disabling_with_the_wrong_password_is_refused(as_alpha_admin: ApiSession) -> None:
    _enroll_and_confirm(as_alpha_admin)

    response = as_alpha_admin.post(
        "/auth/mfa/disable", json={"current_password": "WrongPassword123"}
    )

    assert response.status_code == 401
    assert as_alpha_admin.get("/auth/mfa/status").json()["enabled"] is True


def test_disabling_with_the_right_password_removes_it(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    _enroll_and_confirm(as_alpha_admin)

    response = as_alpha_admin.post(
        "/auth/mfa/disable", json={"current_password": TEST_PASSWORD}
    )

    assert response.status_code == 204
    assert as_alpha_admin.get("/auth/mfa/status").json() == {"enabled": False, "pending": False}

    # Login goes back to issuing tokens directly.
    plain = _login(client, integration_settings.api_prefix, alpha.admin.email)
    assert plain.status_code == 200
    assert "access_token" in plain.json()


def test_disabling_when_not_enabled_is_a_conflict(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post("/auth/mfa/disable", json={"current_password": TEST_PASSWORD})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


# --- Isolation --------------------------------------------------------------


def test_mfa_on_one_account_does_not_gate_another(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    _enroll_and_confirm(as_alpha_admin)

    response = _login(client, integration_settings.api_prefix, alpha.member.email)

    assert response.status_code == 200
    assert "access_token" in response.json()
