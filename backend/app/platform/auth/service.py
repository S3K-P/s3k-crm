"""Authentication use cases (ADR-009, doc 13).

Everything security-relevant about signing in lives here rather than in the
router, so the rules are unit-testable without HTTP:

* failed logins are counted and lock the account after a threshold;
* every failure returns the **same** error regardless of cause, so the endpoint
  cannot be used to enumerate registered addresses;
* refresh tokens rotate on every use, and replaying a rotated token revokes the
  entire family.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

import structlog
from fastapi import status
from sqlalchemy import CursorResult, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.exceptions import AppError, ConflictError
from app.platform.auth.models import Session, User, UserProfile, UserStatus
from app.platform.auth.repository import AuthRepository
from app.platform.auth.security import (
    PasswordHasher,
    RefreshTokenFactory,
    TokenIssuer,
    validate_password_policy,
)
from app.platform.organizations.repository import OrganizationRepository

logger = structlog.get_logger(__name__)

@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A real argon2 digest of a throwaway value.

    Verified against when no user matches so the unknown-address path costs the
    same as a wrong-password path. It must be a genuine digest: a malformed
    string would be rejected immediately and reintroduce the timing signal.
    Computed once, lazily, because hashing is deliberately slow.
    """
    return PasswordHasher().hash("timing-equalisation-placeholder")


class AuthenticationError(AppError):
    """Credentials were not accepted.

    One error for every cause — unknown address, wrong password, disabled
    account — so the response body reveals nothing about which.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_credentials"
    message = "Email or password is incorrect."


class AccountLockedError(AppError):
    """Too many consecutive failures; the account is temporarily locked."""

    status_code = status.HTTP_423_LOCKED
    code = "account_locked"
    message = "This account is temporarily locked after repeated failed sign-in attempts."


class NoOrganizationError(AppError):
    """Authentication succeeded but the user belongs to no usable organization."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "no_organization"
    message = "Your account is not an active member of any organization."


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """What a successful login or refresh produces."""

    access_token: str
    access_expires_at: dt.datetime
    refresh_token: str
    refresh_expires_at: dt.datetime
    session_id: uuid.UUID
    organization_id: uuid.UUID | None


class AuthService:
    """Sign-in, token rotation and sign-out."""

    def __init__(
        self,
        *,
        repository: AuthRepository,
        organizations: OrganizationRepository,
        hasher: PasswordHasher,
        issuer: TokenIssuer,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._repository = repository
        self._organizations = organizations
        self._hasher = hasher
        self._issuer = issuer
        self._settings = settings
        # Used only to persist failed-login bookkeeping outside the request
        # transaction — see :meth:`_register_failure`.
        self._session_factory = session_factory

    # --- Provisioning ------------------------------------------------------

    async def register_user(
        self, *, email: str, password: str, first_name: str, last_name: str
    ) -> User:
        """Create a user and profile.

        Raises:
            WeakPasswordError: the password fails the configured policy.
            ConflictError: the address is already registered.
        """
        validate_password_policy(password, min_length=self._settings.password_min_length)

        normalised = email.strip().lower()
        if await self._repository.get_user_by_email(normalised) is not None:
            raise ConflictError("An account with that email address already exists.")

        user = User(
            email=normalised,
            password_hash=self._hasher.hash(password),
            status=UserStatus.ACTIVE,
        )
        await self._repository.add_user(user)
        await self._repository.add_profile(
            UserProfile(user_id=user.id, first_name=first_name, last_name=last_name)
        )
        logger.info("user_registered", user_id=str(user.id))
        return user

    # --- Login -------------------------------------------------------------

    async def authenticate(
        self,
        *,
        email: str,
        password: str,
        organization_id: uuid.UUID | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        now: dt.datetime | None = None,
    ) -> IssuedTokens:
        """Verify credentials and open a session.

        Raises:
            AccountLockedError: the account is inside a lockout window.
            AuthenticationError: for every other failure, indistinguishably.
            NoOrganizationError: credentials were valid but no organization is
                available, or the caller asked for one they do not belong to.
        """
        now = now or dt.datetime.now(dt.UTC)
        user = await self._repository.get_user_by_email(email)

        if user is None:
            # Spend comparable time so a missing account is not detectable.
            self._hasher.verify(password=password, password_hash=_dummy_hash())
            logger.info("login_failed", reason="unknown_email")
            raise AuthenticationError

        if user.is_locked_at(now):
            logger.warning("login_blocked", user_id=str(user.id), reason="locked")
            raise AccountLockedError

        if user.password_hash is None or not user.is_active:
            self._hasher.verify(password=password, password_hash=_dummy_hash())
            logger.info("login_failed", user_id=str(user.id), reason="inactive_or_no_password")
            raise AuthenticationError

        valid, needs_rehash = self._hasher.verify(
            password=password, password_hash=user.password_hash
        )
        if not valid:
            await self._register_failure(user, now=now)
            raise AuthenticationError

        if needs_rehash:
            # Opportunistic upgrade: the plaintext is only available here.
            user.password_hash = self._hasher.hash(password)

        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = now

        resolved_organization_id = await self._resolve_organization(
            user_id=user.id, requested=organization_id
        )

        tokens = await self._issue_session(
            user=user,
            organization_id=resolved_organization_id,
            family_id=uuid.uuid4(),
            ip_address=ip_address,
            user_agent=user_agent,
            now=now,
        )
        logger.info(
            "login_succeeded",
            user_id=str(user.id),
            organization_id=str(resolved_organization_id),
        )
        return tokens

    async def _register_failure(self, user: User, *, now: dt.datetime) -> None:
        """Count a failed attempt and lock the account at the threshold.

        The caller raises immediately afterwards, which rolls the *request*
        transaction back — so writing the counter there would discard it and
        the lockout would never trigger. The update is therefore committed
        through an independent session.
        """
        attempts = user.failed_login_count + 1
        locked_until: dt.datetime | None = None
        if attempts >= self._settings.login_max_failed_attempts:
            locked_until = now + dt.timedelta(seconds=self._settings.login_lockout_seconds)
            attempts = 0

        # Keep the in-memory instance consistent for the rest of this request.
        user.failed_login_count = attempts
        user.locked_until = locked_until

        if self._session_factory is not None:
            async with self._session_factory() as bookkeeping:
                await bookkeeping.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(failed_login_count=attempts, locked_until=locked_until)
                )
                await bookkeeping.commit()

        if locked_until is not None:
            logger.warning(
                "account_locked", user_id=str(user.id), until=locked_until.isoformat()
            )
        else:
            logger.info(
                "login_failed", user_id=str(user.id), reason="bad_password", attempt=attempts
            )

    async def _resolve_organization(
        self, *, user_id: uuid.UUID, requested: uuid.UUID | None
    ) -> uuid.UUID:
        """Pick the organization the session will act in.

        A requested organization is honoured only after membership is verified,
        so naming someone else's organization at login fails exactly as a
        forged header would.
        """
        if requested is not None:
            if not await self._organizations.has_active_membership(
                organization_id=requested, user_id=user_id
            ):
                logger.warning(
                    "login_organization_denied",
                    user_id=str(user_id),
                    organization_id=str(requested),
                )
                raise NoOrganizationError
            return requested

        default = await self._organizations.default_organization_id(user_id)
        if default is None:
            raise NoOrganizationError
        return default

    # --- Refresh -----------------------------------------------------------

    async def refresh(
        self,
        *,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        now: dt.datetime | None = None,
    ) -> IssuedTokens:
        """Exchange a refresh token for a new pair, rotating the old one.

        Raises:
            AuthenticationError: unknown, expired, revoked or **replayed**
                token. A replay revokes every session in the family before
                raising, on the assumption the token was stolen.
        """
        now = now or dt.datetime.now(dt.UTC)
        digest = RefreshTokenFactory.digest(refresh_token)
        session = await self._repository.get_session_by_token_hash(digest)

        if session is None:
            logger.warning("refresh_failed", reason="unknown_token")
            raise AuthenticationError

        if session.rotated_at is not None or session.revoked_at is not None:
            # Reuse detection (P1-W05-SEC-01): a token that was already
            # exchanged is in circulation twice. Assume compromise and kill the
            # whole lineage rather than just this session.
            #
            # The revocation is committed out of band: this method raises
            # immediately afterwards, and that rollback would otherwise undo
            # the revocation, leaving the stolen family alive.
            revoked = await self._revoke_family_out_of_band(session.family_id, at=now)
            logger.warning(
                "refresh_token_reuse_detected",
                user_id=str(session.user_id),
                family_id=str(session.family_id),
                sessions_revoked=revoked,
            )
            raise AuthenticationError

        if not session.is_usable_at(now):
            logger.info("refresh_failed", reason="expired")
            raise AuthenticationError

        user = await self._repository.get_user(session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError

        # Sessions issued before a password change or admin revocation are dead.
        if session.created_at < user.tokens_valid_from:
            logger.info("refresh_failed", reason="issued_before_revocation_cutoff")
            raise AuthenticationError

        await self._repository.mark_rotated(session.id, at=now)

        return await self._issue_session(
            user=user,
            organization_id=session.organization_id,
            family_id=session.family_id,
            ip_address=ip_address,
            user_agent=user_agent,
            now=now,
        )

    # --- Logout ------------------------------------------------------------

    async def logout(self, *, refresh_token: str | None, now: dt.datetime | None = None) -> None:
        """Revoke the presented session's family.

        Never raises for an unknown token: sign-out is idempotent and must not
        become an oracle for whether a token was valid.
        """
        if not refresh_token:
            return
        now = now or dt.datetime.now(dt.UTC)
        session = await self._repository.get_session_by_token_hash(
            RefreshTokenFactory.digest(refresh_token)
        )
        if session is None:
            return
        await self._repository.revoke_family(session.family_id, at=now)
        logger.info("logout", user_id=str(session.user_id))

    async def _revoke_family_out_of_band(
        self, family_id: uuid.UUID, *, at: dt.datetime
    ) -> int:
        """Revoke a token family in its own committed transaction.

        Used on the reuse-detection path, where the caller raises and the
        request transaction is rolled back. Falls back to the request session
        when no independent factory was supplied (unit tests), which is still
        correct for callers that do not raise.
        """
        if self._session_factory is None:
            return await self._repository.revoke_family(family_id, at=at)

        async with self._session_factory() as revocation:
            result = cast(
                "CursorResult[Any]",
                await revocation.execute(
                    update(Session)
                    .where(Session.family_id == family_id, Session.revoked_at.is_(None))
                    .values(revoked_at=at)
                ),
            )
            await revocation.commit()
            return int(result.rowcount or 0)

    async def revoke_all_sessions(self, user_id: uuid.UUID) -> int:
        now = dt.datetime.now(dt.UTC)
        return await self._repository.revoke_all_for_user(user_id, at=now)

    # --- Password ----------------------------------------------------------

    async def change_password(
        self, *, user: User, current_password: str, new_password: str
    ) -> None:
        """Rotate a password and invalidate every existing session.

        Raises:
            AuthenticationError: the current password is wrong.
            WeakPasswordError: the new password fails the policy.
        """
        if user.password_hash is None:
            raise AuthenticationError
        valid, _ = self._hasher.verify(
            password=current_password, password_hash=user.password_hash
        )
        if not valid:
            raise AuthenticationError

        validate_password_policy(new_password, min_length=self._settings.password_min_length)

        now = dt.datetime.now(dt.UTC)
        user.password_hash = self._hasher.hash(new_password)
        # Anything issued before now stops working, including on other devices.
        user.tokens_valid_from = now
        await self._repository.revoke_all_for_user(user.id, at=now)
        logger.info("password_changed", user_id=str(user.id))

    # --- Internals ---------------------------------------------------------

    async def _issue_session(
        self,
        *,
        user: User,
        organization_id: uuid.UUID | None,
        family_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
        now: dt.datetime,
    ) -> IssuedTokens:
        refresh = RefreshTokenFactory.issue()
        refresh_expires_at = now + dt.timedelta(seconds=self._settings.refresh_token_ttl_seconds)

        # ``id`` is left to the uuid7 column default so session ids stay
        # time-ordered like every other primary key; it is populated by the
        # flush inside ``add_session`` below, before the access token is signed.
        session = Session(
            user_id=user.id,
            family_id=family_id,
            refresh_token_hash=refresh.digest,
            organization_id=organization_id,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:512] or None,
            expires_at=refresh_expires_at,
            created_at=now,
        )
        await self._repository.add_session(session)

        access_token, access_expires_at = self._issuer.issue(
            user_id=user.id,
            session_id=session.id,
            organization_id=organization_id,
            now=now,
        )

        return IssuedTokens(
            access_token=access_token,
            access_expires_at=access_expires_at,
            refresh_token=refresh.value,
            refresh_expires_at=refresh_expires_at,
            session_id=session.id,
            organization_id=organization_id,
        )


__all__ = [
    "AccountLockedError",
    "AuthService",
    "AuthenticationError",
    "IssuedTokens",
    "NoOrganizationError",
]
