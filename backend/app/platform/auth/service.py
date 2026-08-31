"""Authentication use cases (ADR-009, doc 13).

Everything security-relevant about signing in lives here rather than in the
router, so the rules are unit-testable without HTTP:

* failed logins are counted and lock the account after a threshold;
* every failure returns the **same** error regardless of cause, so the endpoint
  cannot be used to enumerate registered addresses;
* refresh tokens rotate on every use, and replaying a rotated token revokes the
  entire family.

**Auditing.** Every branch below that succeeds or fails for a *known* user
appends an audit record (`P1-W05-SEC-02`, `P1-W08-BE-03`). Two details govern
how:

*Failures are written out of band.* Each one raises, and raising rolls the
request transaction back — an in-transaction record of a rejected sign-in would
be discarded along with it. This mirrors ``_register_failure``, which already
commits the lockout counter through an independent session for the same reason.

*An unknown address is deliberately not audited to any tenant.* There is no
organization it belongs to, and attributing it to a guess would both be wrong
and turn the audit screen into the user-enumeration oracle the login response
is so careful not to be. It goes to the structured log, which is not
tenant-scoped, and stays there.
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
from app.core.tenant import get_tenant_context
from app.platform.audit.service import AUTH_MODULE, Action, AuditService, Status
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

#: Permission module recorded for actions on an identity — provisioning, a
#: profile edit, a password reset. Sign-in itself is recorded under
#: ``AUTH_MODULE`` instead, because it is not permission-gated at all.
USERS_MODULE = "users"


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
        audit: AuditService | None = None,
    ) -> None:
        self._repository = repository
        self._organizations = organizations
        self._hasher = hasher
        self._issuer = issuer
        self._settings = settings
        # Used only to persist failed-login bookkeeping outside the request
        # transaction — see :meth:`_register_failure`.
        self._session_factory = session_factory
        # Optional so provisioning callers (``app.bootstrap``, test fixtures)
        # can build the service without a database-backed audit trail. Every
        # HTTP path supplies one; ``_audit`` no-ops when it is absent rather
        # than making each call site check.
        self._audit = audit

    # --- Provisioning ------------------------------------------------------

    async def register_user(
        self,
        *,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> User:
        """Create a user and profile.

        Args:
            organization_id: tenant to record the provisioning against. Omitted
                by ``app.bootstrap`` and by test fixtures, which run before any
                organization exists to attribute it to; the HTTP path always
                supplies it.
            actor_id: the administrator doing the provisioning.

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

        if self._audit is not None and organization_id is not None:
            await self._audit.record(
                organization_id=organization_id,
                action=Action.USER_PROVISIONED,
                module=USERS_MODULE,
                actor_id=actor_id,
                entity_type="USER",
                entity_id=user.id,
                entity_label=normalised,
                # ``email`` is masked by the redaction layer; ``entity_label``
                # above keeps the full address, because identifying the account
                # an administrator created is the record's entire purpose.
                details={"email": normalised, "status": user.status},
            )
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
            await self._audit_auth_failure(
                user, action=Action.LOGIN_BLOCKED, reason="account_locked"
            )
            raise AccountLockedError

        if user.password_hash is None or not user.is_active:
            self._hasher.verify(password=password, password_hash=_dummy_hash())
            logger.info("login_failed", user_id=str(user.id), reason="inactive_or_no_password")
            await self._audit_auth_failure(
                user, action=Action.LOGIN_FAILED, reason="inactive_or_no_password"
            )
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
            organization_id=(
                str(resolved_organization_id) if resolved_organization_id else None
            ),
        )
        # In-transaction: a successful sign-in commits with the session row it
        # created, so the trail cannot claim a sign-in that did not persist.
        #
        # Skipped entirely when the session has no organization: audit rows are
        # tenant-scoped and RLS-protected, so there is no tenant to attribute
        # this sign-in to. The alternative — inventing one — would put a record
        # in some organization's trail that its administrators cannot act on.
        if self._audit is not None and resolved_organization_id is not None:
            await self._audit.record(
                organization_id=resolved_organization_id,
                action=Action.LOGIN_SUCCEEDED,
                module=AUTH_MODULE,
                actor_id=user.id,
                entity_type="USER",
                entity_id=user.id,
                entity_label=user.email,
                details={"session_id": tokens.session_id},
            )
        return tokens

    async def begin_onboarding_session(
        self,
        *,
        user: User,
        ip_address: str | None = None,
        user_agent: str | None = None,
        now: dt.datetime | None = None,
    ) -> IssuedTokens:
        """Open a session for a user who belongs to no organization yet.

        **Why this is not just ``authenticate``.** Login deliberately refuses a
        user with no usable organization (:class:`NoOrganizationError`): for
        someone signing in at ``/login``, landing in a product with no tenant
        is a dead end, and failing loudly is right. Signup is the one moment
        where that state is legitimate and expected — the account was created a
        millisecond ago and the tenant is the *next* screen. Loosening
        ``authenticate`` to allow it would remove the check for every ordinary
        login too, so the exception gets its own door instead.

        No credential check happens here, and none is needed: the only caller
        is the signup route, which was handed the password in the same request
        and used it to create this very user. It is deliberately **not** given
        an email/password signature, so it cannot be repurposed into a second
        authentication path that skips lockout.

        The session it issues is ordinary in every other respect — same table,
        same rotation, same revocation — and simply carries a null
        organization, which the token issuer, the tenant middleware and
        ``/auth/me`` all already model.
        """
        now = now or dt.datetime.now(dt.UTC)
        user.last_login_at = now

        tokens = await self._issue_session(
            user=user,
            organization_id=None,
            family_id=uuid.uuid4(),
            ip_address=ip_address,
            user_agent=user_agent,
            now=now,
        )
        logger.info("onboarding_session_issued", user_id=str(user.id))
        # No audit record: audit rows are tenant-scoped and there is no tenant
        # to attribute this to yet. The organization's own creation is audited
        # a moment later, with this user as its actor.
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
            await self._audit_auth_failure(
                user,
                action=Action.ACCOUNT_LOCKED,
                reason="too_many_failed_attempts",
                extra={
                    "locked_until": locked_until,
                    "threshold": self._settings.login_max_failed_attempts,
                },
            )
        else:
            logger.info(
                "login_failed", user_id=str(user.id), reason="bad_password", attempt=attempts
            )
            await self._audit_auth_failure(
                user,
                action=Action.LOGIN_FAILED,
                reason="bad_password",
                extra={"consecutive_failures": attempts},
            )

    async def _audit_auth_failure(
        self,
        user: User,
        *,
        action: Action,
        reason: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Record a rejected sign-in against the user's own organization.

        Written out of band because the caller raises immediately afterwards
        and the request transaction is rolled back.

        Attributed to the user's **default** organization. A member of several
        tenants produces one record, in the tenant that owns their sign-in, not
        one per organization: repeating a failed attempt across every tenant
        the person belongs to would tell each of those administrators that the
        others exist.

        Silently does nothing when the user has no organization — there is no
        tenant to attribute it to and no administrator who could act on it.
        """
        if self._audit is None:
            return
        organization_id = await self._organizations.default_organization_id(user.id)
        if organization_id is None:
            logger.info(
                "auth_audit_skipped",
                reason="user belongs to no organization",
                user_id=str(user.id),
            )
            return

        await self._audit.record_out_of_band(
            organization_id=organization_id,
            action=action,
            module=AUTH_MODULE,
            actor_id=user.id,
            entity_type="USER",
            entity_id=user.id,
            entity_label=user.email,
            status=Status.FAILURE,
            details={"reason": reason, **(extra or {})},
        )

    async def _audit_organization_for(self, user_id: uuid.UUID) -> uuid.UUID | None:
        """The organization a self-service account action belongs to.

        The active tenant when the request carried one — a password change made
        while working inside an organization belongs in *that* organization's
        trail — falling back to the user's default.
        """
        context = get_tenant_context()
        if context is not None:
            return context.organization_id
        return await self._organizations.default_organization_id(user_id)

    async def _resolve_organization(
        self, *, user_id: uuid.UUID, requested: uuid.UUID | None
    ) -> uuid.UUID | None:
        """Pick the organization the session will act in, if there is one.

        Two cases, and only one of them is a refusal.

        **A requested organization** is honoured only after membership is
        verified, so naming someone else's organization at login fails exactly
        as a forged header would. That is the security property
        ``test_logging_into_an_organization_you_do_not_belong_to_is_refused``
        exists to hold, and it is unchanged.

        **No requested organization and no memberships** returns ``None``
        rather than raising. Since self-service signup exists, "authenticated
        but not yet in a tenant" is an ordinary state: somebody who created an
        account and closed the tab before finishing onboarding, or who was
        removed from the only organization they were in. Refusing them at login
        left them permanently unable to sign in — with a valid password, a real
        account, and no way to reach the screen that would have fixed it.

        The token that results carries no organization, which the issuer, the
        tenant middleware and ``/auth/me`` all already model, and every
        tenant-scoped route still refuses it with 403 until the caller has a
        verified membership. So this widens where a user may *stand*, never
        what they may reach.
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

        return await self._organizations.default_organization_id(user_id)

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
            # The single strongest signal of a stolen credential this system
            # produces, so it belongs in the trail an administrator reads —
            # out of band, for the same reason the revocation above is.
            if self._audit is not None and session.organization_id is not None:
                await self._audit.record_out_of_band(
                    organization_id=session.organization_id,
                    action=Action.TOKEN_REUSE_DETECTED,
                    module=AUTH_MODULE,
                    actor_id=session.user_id,
                    entity_type="USER",
                    entity_id=session.user_id,
                    status=Status.FAILURE,
                    details={
                        "reason": "refresh_token_replayed",
                        "sessions_revoked": revoked,
                    },
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

        # The organization the caller is *acting in* takes precedence over the
        # one their refresh token was minted for. A user who belongs to two
        # tenants can switch by sending a different ``X-Organization-Id``
        # without re-authenticating, so the two legitimately differ — and the
        # request transaction is scoped to the active one, which is the only
        # organization a record may be written into from here.
        #
        # The middleware has already verified membership of that organization,
        # so this can never attribute a sign-out to a tenant the user does not
        # belong to.
        context = get_tenant_context()
        organization_id = (
            context.organization_id if context is not None else session.organization_id
        )
        if self._audit is not None and organization_id is not None:
            await self._audit.record(
                organization_id=organization_id,
                action=Action.LOGOUT,
                module=AUTH_MODULE,
                actor_id=session.user_id,
                entity_type="USER",
                entity_id=session.user_id,
                details={"family_id": session.family_id},
            )

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
        revoked = await self._repository.revoke_all_for_user(user.id, at=now)
        logger.info("password_changed", user_id=str(user.id))

        organization_id = await self._audit_organization_for(user.id)
        if self._audit is not None and organization_id is not None:
            await self._audit.record(
                organization_id=organization_id,
                action=Action.PASSWORD_CHANGED,
                module=USERS_MODULE,
                actor_id=user.id,
                entity_type="USER",
                entity_id=user.id,
                entity_label=user.email,
                # Neither password appears here, and neither can: ``details``
                # is redacted on the way in and both keys would match.
                details={"sessions_revoked": revoked, "self_service": True},
            )

    async def set_password(
        self,
        *,
        user: User,
        new_password: str,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Replace a password administratively, without the old one.

        Distinct from :meth:`change_password`, which the account holder calls
        and which proves possession of the current password first. Here the
        caller has already been authorized through ``users.ADMIN``, so no
        current password exists to check — which is exactly why the blast
        radius is contained the same way: every session the user holds is
        revoked and ``tokens_valid_from`` moves forward, so an access token
        already in flight stops working on its next request rather than
        lingering for its remaining TTL.

        Args:
            organization_id: tenant whose trail records this. Supplied by the
                caller because an administrator acts *within* an organization,
                and their own default tenant is not necessarily the subject's.
            actor_id: the administrator. Distinct from ``user.id`` — recording
                only the subject would leave "who took this account over?"
                unanswerable, which is the whole question here.

        Raises:
            WeakPasswordError: the new password fails the configured policy.
        """
        validate_password_policy(new_password, min_length=self._settings.password_min_length)

        now = dt.datetime.now(dt.UTC)
        user.password_hash = self._hasher.hash(new_password)
        user.tokens_valid_from = now
        # An administrator resetting a password is usually recovering an
        # account, so clear the brute-force lockout in the same step.
        user.failed_login_count = 0
        user.locked_until = None
        revoked = await self._repository.revoke_all_for_user(user.id, at=now)
        logger.info("password_reset_by_admin", user_id=str(user.id))

        if self._audit is not None and organization_id is not None:
            await self._audit.record(
                organization_id=organization_id,
                action=Action.PASSWORD_RESET_BY_ADMIN,
                module=USERS_MODULE,
                actor_id=actor_id,
                entity_type="USER",
                entity_id=user.id,
                entity_label=user.email,
                details={"sessions_revoked": revoked, "lockout_cleared": True},
            )

    async def update_profile(
        self,
        *,
        user: User,
        first_name: str | None = None,
        last_name: str | None = None,
        phone: str | None = None,
        timezone: str | None = None,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> UserProfile:
        """Edit a user's display attributes.

        A profile row is created when the identity has none — SSO-provisioned
        users may not have one — so this never silently does nothing.

        ``None`` means "leave unchanged" for the names, which are NOT NULL;
        ``phone`` is nullable, so passing ``None`` there also leaves it alone
        and an explicit empty string clears it.

        ``organization_id`` and ``actor_id`` drive the audit record and are
        optional for the same reason as on :meth:`register_user`. Nothing is
        recorded when the submitted values match what is already stored — an
        edit that changed nothing is not an event.
        """
        profile = user.profile
        if profile is None:
            profile = UserProfile(
                user_id=user.id,
                first_name=(first_name or "").strip() or "Unnamed",
                last_name=(last_name or "").strip() or "User",
            )
            await self._repository.add_profile(profile)

        before = {
            "first_name": profile.first_name,
            "last_name": profile.last_name,
            "phone": profile.phone,
            "timezone": profile.timezone,
        }

        if first_name is not None and first_name.strip():
            profile.first_name = first_name.strip()
        if last_name is not None and last_name.strip():
            profile.last_name = last_name.strip()
        if phone is not None:
            profile.phone = phone.strip() or None
        if timezone is not None and timezone.strip():
            profile.timezone = timezone.strip()

        logger.info("user_profile_updated", user_id=str(user.id))

        if self._audit is not None and organization_id is not None:
            await self._audit.record_change(
                organization_id=organization_id,
                action=Action.UPDATED,
                module=USERS_MODULE,
                entity_type="USER",
                entity_id=user.id,
                entity_label=user.email,
                actor_id=actor_id,
                before=before,
                after={
                    "first_name": profile.first_name,
                    "last_name": profile.last_name,
                    "phone": profile.phone,
                    "timezone": profile.timezone,
                },
            )
        return profile

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
