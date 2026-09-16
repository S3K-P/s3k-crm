"""TOTP secret encryption, code verification and recovery codes — no database required."""

from __future__ import annotations

import pyotp
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from app.core.config import Settings
from app.platform.auth.mfa import (
    RECOVERY_CODE_COUNT,
    MfaNotConfiguredError,
    MfaSecretCipher,
    generate_recovery_codes,
    generate_totp_secret,
    provisioning_uri,
    verify_totp_code,
)

# --- MfaSecretCipher ---------------------------------------------------------


@pytest.fixture
def configured_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"mfa_encryption_key": SecretStr(Fernet.generate_key().decode())}
    )


@pytest.fixture
def unconfigured_settings(settings: Settings) -> Settings:
    # Explicit rather than trusting the shared ``settings`` fixture to leave
    # this unset: pydantic-settings still reads ``backend/.env`` for any
    # field a test does not override, so a real MFA_ENCRYPTION_KEY in a
    # developer's own .env would otherwise leak into a test that means to
    # exercise the "no key configured" path.
    return settings.model_copy(update={"mfa_encryption_key": None})


def test_unconfigured_settings_leave_the_cipher_unconfigured(
    unconfigured_settings: Settings,
) -> None:
    cipher = MfaSecretCipher(unconfigured_settings)

    assert cipher.configured is False


def test_configured_settings_make_the_cipher_configured(configured_settings: Settings) -> None:
    cipher = MfaSecretCipher(configured_settings)

    assert cipher.configured is True


def test_an_unconfigured_cipher_refuses_to_encrypt(unconfigured_settings: Settings) -> None:
    with pytest.raises(MfaNotConfiguredError):
        MfaSecretCipher(unconfigured_settings).encrypt("JBSWY3DPEHPK3PXP")


def test_an_unconfigured_cipher_refuses_to_decrypt(unconfigured_settings: Settings) -> None:
    with pytest.raises(MfaNotConfiguredError):
        MfaSecretCipher(unconfigured_settings).decrypt("whatever")


def test_encryption_round_trips_the_secret(configured_settings: Settings) -> None:
    cipher = MfaSecretCipher(configured_settings)
    secret = generate_totp_secret()

    encrypted = cipher.encrypt(secret)

    assert secret not in encrypted
    assert cipher.decrypt(encrypted) == secret


def test_a_secret_encrypted_with_one_key_cannot_be_read_with_another(
    configured_settings: Settings,
) -> None:
    """A rotated key must not silently produce garbage claiming to be the secret."""
    cipher = MfaSecretCipher(configured_settings)
    encrypted = cipher.encrypt(generate_totp_secret())

    other_settings = configured_settings.model_copy(
        update={"mfa_encryption_key": SecretStr(Fernet.generate_key().decode())}
    )
    other_cipher = MfaSecretCipher(other_settings)

    with pytest.raises(MfaNotConfiguredError):
        other_cipher.decrypt(encrypted)


# --- TOTP ---------------------------------------------------------------------


def test_generated_secrets_are_valid_base32_and_unique() -> None:
    first, second = generate_totp_secret(), generate_totp_secret()

    assert first != second
    # pyotp.TOTP would raise on a malformed secret; constructing one is the check.
    pyotp.TOTP(first)


def test_the_current_code_for_a_secret_verifies() -> None:
    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()

    assert verify_totp_code(secret=secret, code=code) is True


def test_a_code_from_a_different_secret_does_not_verify() -> None:
    secret = generate_totp_secret()
    wrong_code = pyotp.TOTP(generate_totp_secret()).now()

    assert verify_totp_code(secret=secret, code=wrong_code) is False


def test_a_non_numeric_code_does_not_verify() -> None:
    secret = generate_totp_secret()

    assert verify_totp_code(secret=secret, code="not-a-code") is False


def test_a_code_with_stray_whitespace_still_verifies() -> None:
    """Copy-pasted from an authenticator app, spaces and all."""
    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()

    assert verify_totp_code(secret=secret, code=f" {code} ") is True


def test_provisioning_uri_names_the_account_and_the_issuer() -> None:
    secret = generate_totp_secret()

    uri = provisioning_uri(secret=secret, account_email="ada@example.com")

    assert uri.startswith("otpauth://totp/")
    assert "ada%40example.com" in uri or "ada@example.com" in uri
    assert "S3K" in uri


# --- Recovery codes -------------------------------------------------------------


def test_generates_the_expected_count_of_codes() -> None:
    batch = generate_recovery_codes()

    assert len(batch.plaintext_codes) == RECOVERY_CODE_COUNT


def test_recovery_codes_are_unique() -> None:
    batch = generate_recovery_codes()

    assert len(set(batch.plaintext_codes)) == len(batch.plaintext_codes)


def test_recovery_codes_avoid_ambiguous_characters() -> None:
    batch = generate_recovery_codes()

    for code in batch.plaintext_codes:
        assert not set(code) & set("0O1IL")
