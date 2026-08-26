"""Password hashing, policy and JWT issuance — no database required."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core.config import Settings
from app.platform.auth.security import (
    InvalidTokenError,
    PasswordHasher,
    RefreshTokenFactory,
    TokenIssuer,
    WeakPasswordError,
    validate_password_policy,
)

VALID_PASSWORD = "Str0ngPassphrase!"


# --- Hashing ----------------------------------------------------------------


def test_hashing_never_returns_the_plaintext() -> None:
    digest = PasswordHasher().hash(VALID_PASSWORD)

    assert VALID_PASSWORD not in digest
    assert digest.startswith("$argon2")


def test_the_same_password_hashes_differently_each_time() -> None:
    """Salting: identical passwords must not produce identical digests."""
    hasher = PasswordHasher()

    assert hasher.hash(VALID_PASSWORD) != hasher.hash(VALID_PASSWORD)


def test_a_correct_password_verifies() -> None:
    hasher = PasswordHasher()
    digest = hasher.hash(VALID_PASSWORD)

    valid, _ = hasher.verify(password=VALID_PASSWORD, password_hash=digest)

    assert valid is True


def test_a_wrong_password_does_not_verify() -> None:
    hasher = PasswordHasher()
    digest = hasher.hash(VALID_PASSWORD)

    valid, _ = hasher.verify(password="not-the-password", password_hash=digest)

    assert valid is False


def test_a_corrupt_digest_fails_closed_rather_than_raising() -> None:
    """The caller must not be able to tell corruption from a bad password."""
    valid, needs_rehash = PasswordHasher().verify(
        password=VALID_PASSWORD, password_hash="not-a-hash"
    )

    assert (valid, needs_rehash) == (False, False)


# --- Policy -----------------------------------------------------------------


def test_a_compliant_password_is_accepted() -> None:
    validate_password_policy(VALID_PASSWORD, min_length=12)


@pytest.mark.parametrize(
    ("password", "expected"),
    [
        ("Short1A", "at least"),
        ("alllowercase123", "uppercase"),
        ("ALLUPPERCASE123", "lowercase"),
        ("NoDigitsAtAllHere", "digit"),
    ],
)
def test_a_non_compliant_password_is_rejected(password: str, expected: str) -> None:
    with pytest.raises(WeakPasswordError) as exc_info:
        validate_password_policy(password, min_length=12)

    requirements = " ".join(exc_info.value.details["requirements"])
    assert expected in requirements


def test_every_unmet_rule_is_reported_at_once() -> None:
    """One failure per attempt would be a poor experience and a slow oracle."""
    with pytest.raises(WeakPasswordError) as exc_info:
        validate_password_policy("abc", min_length=12)

    assert len(exc_info.value.details["requirements"]) == 3


# --- Refresh tokens ---------------------------------------------------------


def test_refresh_tokens_are_unique_and_hashed() -> None:
    first = RefreshTokenFactory.issue()
    second = RefreshTokenFactory.issue()

    assert first.value != second.value
    assert first.digest == RefreshTokenFactory.digest(first.value)
    assert first.value not in first.digest


# --- Access tokens ----------------------------------------------------------


@pytest.fixture
def issuer(settings: Settings) -> TokenIssuer:
    return TokenIssuer(settings)


def test_an_issued_token_verifies_and_round_trips_its_claims(
    issuer: TokenIssuer,
) -> None:
    user_id, session_id, organization_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = dt.datetime.now(dt.UTC)

    token, expires_at = issuer.issue(
        user_id=user_id, session_id=session_id, organization_id=organization_id, now=now
    )
    claims = issuer.verify(token)

    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert claims.organization_id == organization_id
    assert expires_at > now


def test_an_expired_token_is_rejected(issuer: TokenIssuer) -> None:
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
    token, _ = issuer.issue(
        user_id=uuid.uuid4(), session_id=uuid.uuid4(), organization_id=None, now=past
    )

    with pytest.raises(InvalidTokenError):
        issuer.verify(token)


def test_a_tampered_token_is_rejected(issuer: TokenIssuer) -> None:
    token, _ = issuer.issue(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        organization_id=None,
        now=dt.datetime.now(dt.UTC),
    )
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}x.{signature}"

    with pytest.raises(InvalidTokenError):
        issuer.verify(tampered)


def test_a_token_from_a_different_issuer_is_rejected(settings: Settings) -> None:
    """Two deployments must not accept each other's tokens."""
    theirs = TokenIssuer(settings.model_copy(update={"jwt_issuer": "someone-else"}))
    token, _ = theirs.issue(
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        organization_id=None,
        now=dt.datetime.now(dt.UTC),
    )

    with pytest.raises(InvalidTokenError):
        TokenIssuer(settings).verify(token)


def test_garbage_is_rejected(issuer: TokenIssuer) -> None:
    with pytest.raises(InvalidTokenError):
        issuer.verify("not-a-token")
