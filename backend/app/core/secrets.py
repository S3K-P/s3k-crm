"""Reversible encryption for secrets that must be *used*, not just verified.

Everything secret in this codebase up to now has been one-way: passwords are
argon2id, refresh and invitation tokens are SHA-256 digests. None of them is
ever read back, because verification only needs a comparison.

A provider API key is different in kind. The gateway has to present the actual
value to Anthropic on every call, so a digest is useless and the plaintext has
to be recoverable. That is a genuinely weaker position than hashing, and the
job of this module is to make the weakening as small and as explicit as
possible: ciphertext at rest, one key, held outside the database it protects.

**Fernet** (AES-128-CBC with an HMAC-SHA256 authentication tag) from
``cryptography``, which is already a dependency — the JWT signing code uses it.
Authenticated encryption matters here rather than raw AES: a tampered row must
fail loudly instead of decrypting to rubbish that gets sent to a provider as a
credential.

**The key lives in the environment, never in the database.** Storing the
key-encryption key beside the ciphertext it protects would mean anyone who can
read the table can read the secrets, which is the same as not encrypting. It
therefore has to be supplied by the deployment, and when it is absent this
module refuses to encrypt rather than inventing one — see
:class:`SecretsNotConfiguredError`.

**Why not a generated fallback in development.** An ephemeral key would let
credentials be saved and then silently fail to decrypt after the next restart,
presenting as "my provider key stopped working" with nothing in the logs to
explain it. Refusing up front is the kinder failure.
"""

from __future__ import annotations

import hashlib

import structlog
from cryptography.fernet import Fernet, InvalidToken
from fastapi import status

from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)

#: How many trailing characters of a credential may be shown back to a client.
#: Four is the convention card issuers use and is enough for a human to tell
#: two keys apart without being enough to reconstruct either.
MASK_VISIBLE_CHARS = 4


class SecretsNotConfiguredError(AppError):
    """No encryption key is configured, so secrets cannot be stored.

    A first-class deployment state rather than a bug, reported the same way
    ``ai_not_configured`` and the storage checks are: the interface can render
    an accurate explanation instead of a generic failure.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "secret_storage_not_configured"
    message = (
        "Credential storage is not configured on this deployment. An operator "
        "must set AI_CREDENTIAL_ENCRYPTION_KEY before credentials can be saved."
    )


class SecretDecryptionError(AppError):
    """Stored ciphertext could not be decrypted with the configured key.

    Means the key was rotated or the row was tampered with. Deliberately not
    silent: returning nothing would look identical to "no credential set", and
    an operator would go looking for the wrong problem.
    """

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "secret_undecryptable"
    message = (
        "A stored credential could not be read with the current encryption "
        "key. It must be re-entered."
    )


class SecretBox:
    """Encrypts and decrypts values with one symmetric key.

    Construct it from :meth:`from_key`, which tolerates the key being absent —
    the common case in development, where AI runs from the environment
    variable instead and nothing is ever written to the table.
    """

    def __init__(self, fernet: Fernet | None) -> None:
        self._fernet = fernet

    @classmethod
    def from_key(cls, key: str | None) -> SecretBox:
        """Build a box, or an unusable one when no key is configured.

        An invalid key is treated as absent and logged, rather than raised: the
        alternative is an application that will not start because of a typo in
        an optional variable, taking the whole CRM down over a feature nobody
        may be using.
        """
        if not key or not key.strip():
            return cls(None)
        try:
            return cls(Fernet(key.strip().encode("utf-8")))
        except (ValueError, TypeError):
            logger.error(
                "secret_encryption_key_invalid",
                detail="AI_CREDENTIAL_ENCRYPTION_KEY is not a valid Fernet key; "
                "credential storage is disabled. Generate one with "
                "`python -c \"from cryptography.fernet import Fernet; "
                'print(Fernet.generate_key().decode())"`.',
            )
            return cls(None)

    @property
    def available(self) -> bool:
        """Whether this box can actually encrypt."""
        return self._fernet is not None

    def encrypt(self, plaintext: str) -> str:
        """Return ciphertext for ``plaintext``.

        Raises:
            SecretsNotConfiguredError: no usable key is configured.
        """
        if self._fernet is None:
            raise SecretsNotConfiguredError
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """Recover the plaintext.

        Raises:
            SecretsNotConfiguredError: no usable key is configured.
            SecretDecryptionError: the key does not match, or the row was
                altered — Fernet's authentication tag catches both.
        """
        if self._fernet is None:
            raise SecretsNotConfiguredError
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            # The ciphertext is deliberately not logged: it is the secret.
            logger.error("secret_decryption_failed")
            raise SecretDecryptionError from exc


def mask_secret(plaintext: str) -> str:
    """A display form that identifies a credential without revealing it.

    ``sk-ant-api03-…AB9f`` rather than the value. Short inputs collapse to
    dots entirely instead of leaking a meaningful fraction of themselves.
    """
    cleaned = plaintext.strip()
    if len(cleaned) <= MASK_VISIBLE_CHARS * 2:
        return "•" * 8
    return f"{'•' * 8}{cleaned[-MASK_VISIBLE_CHARS:]}"


def fingerprint_secret(plaintext: str) -> str:
    """A stable digest of a credential, safe to store and compare.

    Lets the application answer "is this the same key I already hold?" — for
    idempotent updates and for audit — without decrypting anything. SHA-256
    rather than argon2 for the reason
    :class:`app.platform.auth.security.RefreshTokenFactory` gives: the input is
    high-entropy machine-generated material, not a human-chosen password, so
    there is nothing for a slow KDF to defend.
    """
    return hashlib.sha256(plaintext.strip().encode("utf-8")).hexdigest()


__all__ = [
    "MASK_VISIBLE_CHARS",
    "SecretBox",
    "SecretDecryptionError",
    "SecretsNotConfiguredError",
    "fingerprint_secret",
    "mask_secret",
]
