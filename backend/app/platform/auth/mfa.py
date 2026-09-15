"""TOTP-based multi-factor authentication: secrets, codes and recovery codes.

Kept separate from ``security.py`` because it depends on an *optional*
deployment key (``Settings.mfa_encryption_key``) that the rest of auth does
not — a TOTP secret cannot be one-way hashed like a password (the server has
to recover the plaintext to compute the next code), so it is encrypted at
rest instead, and every function here that touches a secret refuses outright
when no key is configured rather than falling back to storing it in the
clear. This is the same "built but not switched on" shape ``email_provider``
already has (see ``platform/email/provider.py``'s own docstring): the
enrollment flow is fully implemented and tested, and a deployment opts in by
setting one environment variable.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import pyotp
import structlog
from cryptography.fernet import Fernet, InvalidToken
from fastapi import status

from app.core.config import Settings
from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)

#: Shown as the "issuer" in an authenticator app next to the account email.
ISSUER_NAME = "S3K CRM"

#: Codes issued at enrollment, each usable exactly once, for the case where
#: the authenticator device is lost. Ten matches the common industry default
#: (GitHub, Google) — enough to not run out from routine use, few enough that
#: regenerating periodically is still meaningful.
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 10
#: Excludes characters that are easy to transpose or confuse when copied by
#: hand (0/O, 1/I/L), the same reasoning a picklist or invite-code alphabet
#: elsewhere in this codebase would use.
_RECOVERY_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

#: A code is accepted if it matches the current 30-second step or one step to
#: either side — the standard TOTP tolerance for clock drift between the
#: server and the phone generating it. Widening this further starts trading
#: security for convenience; RFC 6238 itself recommends against more.
_TOTP_VALID_WINDOW = 1


class MfaNotConfiguredError(AppError):
    """No ``MFA_ENCRYPTION_KEY`` is set, so no secret can be stored or read.

    503, matching ``ai_not_configured``/``email_not_configured`` — this is an
    environment gap, not a caller error, and is never silently downgraded
    into storing a secret nobody configured a key to protect.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "mfa_not_configured"
    message = "Multi-factor authentication is not available in this deployment."


class MfaSecretCipher:
    """Encrypts and decrypts TOTP secrets with the deployment's Fernet key.

    Fernet (authenticated symmetric encryption) rather than the argon2
    hashing the rest of this module uses for passwords: a password is only
    ever *compared*, but a TOTP code can only be computed from the secret
    itself, so the server must be able to recover the plaintext. Generate a
    key with ``Fernet.generate_key()`` and set it as ``MFA_ENCRYPTION_KEY``.
    """

    def __init__(self, settings: Settings) -> None:
        key = settings.mfa_encryption_key
        self._fernet = Fernet(key.get_secret_value().encode()) if key is not None else None

    @property
    def configured(self) -> bool:
        return self._fernet is not None

    def encrypt(self, secret: str) -> str:
        if self._fernet is None:
            raise MfaNotConfiguredError
        return self._fernet.encrypt(secret.encode()).decode()

    def decrypt(self, token: str) -> str:
        """Raises :class:`MfaNotConfiguredError` if no key, or the key changed since encryption."""
        if self._fernet is None:
            raise MfaNotConfiguredError
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            logger.error("mfa_secret_undecryptable", detail="key rotated or corrupted row")
            raise MfaNotConfiguredError from exc


def generate_totp_secret() -> str:
    """A fresh random base32 secret, suitable for ``pyotp.TOTP``."""
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, account_email: str) -> str:
    """The ``otpauth://`` URI an authenticator app scans or accepts by hand."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=ISSUER_NAME)


def verify_totp_code(*, secret: str, code: str) -> bool:
    """Whether ``code`` is valid for ``secret`` right now (within the drift window)."""
    normalised = code.strip().replace(" ", "")
    if not normalised.isdigit():
        return False
    return pyotp.totp.TOTP(secret).verify(normalised, valid_window=_TOTP_VALID_WINDOW)


@dataclass(frozen=True, slots=True)
class RecoveryCodeBatch:
    """A freshly generated set of recovery codes, plaintext, shown exactly once."""

    plaintext_codes: tuple[str, ...]


def generate_recovery_codes() -> RecoveryCodeBatch:
    alphabet = _RECOVERY_CODE_ALPHABET
    codes = tuple(
        "".join(secrets.choice(alphabet) for _ in range(RECOVERY_CODE_LENGTH))
        for _ in range(RECOVERY_CODE_COUNT)
    )
    return RecoveryCodeBatch(plaintext_codes=codes)


__all__ = [
    "ISSUER_NAME",
    "RECOVERY_CODE_COUNT",
    "MfaNotConfiguredError",
    "MfaSecretCipher",
    "RecoveryCodeBatch",
    "generate_recovery_codes",
    "generate_totp_secret",
    "provisioning_uri",
    "verify_totp_code",
]
