"""Password hashing, refresh-token handling and JWT issuance (ADR-009, doc 13).

Three separable concerns, kept out of ``service.py`` so the use cases stay
readable and each primitive is unit-testable on its own:

* :class:`PasswordHasher` — argon2id, with transparent rehashing when the cost
  parameters are raised.
* :class:`RefreshTokenFactory` — opaque high-entropy tokens; only their SHA-256
  digest is ever persisted.
* :class:`TokenIssuer` — EdDSA (Ed25519) access tokens.

A plaintext password is never stored, logged, or returned by anything here.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Any, Final

import jwt
import structlog
from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import status

from app.core.config import Settings
from app.core.exceptions import AppError

logger = structlog.get_logger(__name__)

JWT_ALGORITHM: Final = "EdDSA"
TOKEN_TYPE_ACCESS: Final = "access"  # noqa: S105 - a claim value, not a secret


class InvalidTokenError(AppError):
    """The presented token is missing, malformed, expired or not trusted."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_token"
    message = "Your session is invalid or has expired. Please sign in again."


class WeakPasswordError(AppError):
    """The supplied password does not meet the configured policy."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "weak_password"
    message = "The password does not meet the security policy."


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


class PasswordHasher:
    """argon2id hashing with constant-time verification.

    ``verify`` returns a ``needs_rehash`` flag so the caller can upgrade a
    stored digest to current cost parameters during a successful login, without
    ever needing the plaintext at any other time.
    """

    def __init__(self) -> None:
        # argon2-cffi's defaults track the current OWASP recommendation.
        self._hasher = Argon2Hasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, *, password: str, password_hash: str) -> tuple[bool, bool]:
        """Return ``(is_valid, needs_rehash)``.

        Every failure mode collapses to ``(False, False)``: the caller must not
        be able to distinguish "wrong password" from "corrupt digest", and the
        reason never reaches the client.
        """
        try:
            self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False, False
        return True, bool(self._hasher.check_needs_rehash(password_hash))


def validate_password_policy(password: str, *, min_length: int) -> None:
    """Enforce the password policy from ``P1-W04-BE-02``.

    Raises:
        WeakPasswordError: listing every unmet rule at once, so the user is not
            forced through one failure per attempt.
    """
    problems: list[str] = []

    if len(password) < min_length:
        problems.append(f"must be at least {min_length} characters")
    if not any(character.islower() for character in password):
        problems.append("must contain a lowercase letter")
    if not any(character.isupper() for character in password):
        problems.append("must contain an uppercase letter")
    if not any(character.isdigit() for character in password):
        problems.append("must contain a digit")

    if problems:
        raise WeakPasswordError(details={"requirements": problems})


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RefreshToken:
    """A refresh token and the digest that will be stored in its place."""

    value: str
    digest: str


class RefreshTokenFactory:
    """Creates opaque refresh tokens and hashes them for storage.

    SHA-256 rather than argon2 is correct here: the token is 256 bits of
    generated entropy, not a human-chosen secret, so it is not brute-forceable
    and the digest must stay cheap enough to look up on every refresh.
    """

    @staticmethod
    def issue() -> RefreshToken:
        value = secrets.token_urlsafe(48)
        return RefreshToken(value=value, digest=RefreshTokenFactory.digest(value))

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Access tokens
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """The verified contents of an access token."""

    user_id: uuid.UUID
    session_id: uuid.UUID
    organization_id: uuid.UUID | None
    issued_at: dt.datetime
    expires_at: dt.datetime


class TokenIssuer:
    """Signs and verifies Ed25519 access tokens.

    Outside development and test the keypair must be supplied by configuration.
    In development an ephemeral keypair is generated so a fresh clone runs with
    no key material on disk; tokens then die with the process, which is
    acceptable locally and refused by :class:`~app.core.config.Settings`
    anywhere else.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self._ttl = dt.timedelta(seconds=settings.access_token_ttl_seconds)

        if settings.jwt_private_key and settings.jwt_public_key:
            self._private_key = settings.jwt_private_key
            self._public_key = settings.jwt_public_key
        else:
            self._private_key, self._public_key = _generate_ephemeral_keypair()
            logger.warning(
                "jwt_ephemeral_keypair_generated",
                environment=settings.environment,
                detail=(
                    "No JWT_PRIVATE_KEY/JWT_PUBLIC_KEY configured. Tokens are signed "
                    "with a process-local key and become invalid on restart."
                ),
            )

    def issue(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        now: dt.datetime,
    ) -> tuple[str, dt.datetime]:
        """Return ``(token, expires_at)``."""
        expires_at = now + self._ttl
        claims: dict[str, Any] = {
            "sub": str(user_id),
            "sid": str(session_id),
            "org": str(organization_id) if organization_id else None,
            "typ": TOKEN_TYPE_ACCESS,
            "iss": self._issuer,
            "aud": self._audience,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(claims, self._private_key, algorithm=JWT_ALGORITHM)
        return token, expires_at

    def verify(self, token: str) -> AccessTokenClaims:
        """Validate signature, expiry, issuer and audience.

        Raises:
            InvalidTokenError: for every failure, with an identical message, so
                nothing about *why* verification failed leaks to the caller.
        """
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._public_key,
                algorithms=[JWT_ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            logger.info("access_token_rejected", reason=type(exc).__name__)
            raise InvalidTokenError from exc

        if payload.get("typ") != TOKEN_TYPE_ACCESS:
            # A refresh token must never be accepted as a bearer credential.
            raise InvalidTokenError

        try:
            user_id = uuid.UUID(str(payload["sub"]))
            session_id = uuid.UUID(str(payload["sid"]))
            raw_org = payload.get("org")
            organization_id = uuid.UUID(str(raw_org)) if raw_org else None
        except (KeyError, ValueError) as exc:
            raise InvalidTokenError from exc

        return AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            organization_id=organization_id,
            issued_at=dt.datetime.fromtimestamp(int(payload["iat"]), tz=dt.UTC),
            expires_at=dt.datetime.fromtimestamp(int(payload["exp"]), tz=dt.UTC),
        )


def _generate_ephemeral_keypair() -> tuple[str, str]:
    """Generate a throwaway Ed25519 keypair in PEM form."""
    private = ed25519.Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_pem, public_pem


__all__ = [
    "AccessTokenClaims",
    "InvalidTokenError",
    "PasswordHasher",
    "RefreshToken",
    "RefreshTokenFactory",
    "TokenIssuer",
    "WeakPasswordError",
    "validate_password_policy",
]
