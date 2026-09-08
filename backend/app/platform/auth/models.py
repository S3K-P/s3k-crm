"""SQLAlchemy models for the auth module (doc 04 "Core Models").

Four tables, all in the ``platform`` schema:

``users``          global identity. **Deliberately not tenant-scoped**: one
                   person may belong to several organizations, so the row
                   cannot carry a single ``organization_id`` and must not have
                   RLS. Scoping happens through ``organization_memberships``.
``user_profiles``  display attributes, split off so the identity row stays
                   narrow and cacheable.
``sessions``       refresh-token family state. Only the *hash* of a refresh
                   token is ever stored (ADR-009).
``password_reset_tokens``
                   outstanding self-service reset requests. Like the three
                   above it is untenanted, because a password belongs to the
                   identity and not to any organization the identity happens
                   to be a member of.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

PLATFORM_SCHEMA = "platform"


class UserStatus(enum.StrEnum):
    """Lifecycle of a platform identity."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    PENDING = "PENDING"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A platform identity.

    No ``organization_id`` and no RLS by design: identity is global and a user
    can be a member of many organizations. Anything tenant-specific about a
    user lives on :class:`~app.platform.organizations.models.OrganizationMembership`.
    """

    __tablename__ = "users"
    __table_args__ = ({"schema": PLATFORM_SCHEMA},)

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    email_verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: argon2id digest. Nullable so SSO-only identities remain possible later.
    #: A plaintext password is never stored, logged or returned.
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", schema=PLATFORM_SCHEMA, native_enum=True),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )

    # --- Brute-force protection (doc 13) -----------------------------------
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Refresh tokens issued before this instant are rejected. Bumped on
    #: password change and administrative revocation.
    tokens_valid_from: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE and self.deleted_at is None

    def is_locked_at(self, now: dt.datetime) -> bool:
        """Whether the account is inside a brute-force lockout window."""
        return self.locked_until is not None and self.locked_until > now


class UserProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Display attributes for a user."""

    __tablename__ = "user_profiles"
    __table_args__ = ({"schema": PLATFORM_SCHEMA},)

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    locale: Mapped[str] = mapped_column(
        String(16), nullable=False, default="en", server_default="en"
    )
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    user: Mapped[User] = relationship(back_populates="profile")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Session(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One refresh-token lineage.

    Rotation creates a new row and marks the old one ``rotated_at`` while
    keeping ``family_id`` constant. Presenting an already-rotated token means
    the token leaked, so the whole family is revoked (doc 13, P1-W05-SEC-01).

    ``refresh_token_hash`` is a SHA-256 digest of the opaque token. The token
    itself is returned to the client once and never persisted.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_refresh_token_hash", "refresh_token_hash", unique=True),
        Index("ix_sessions_family_id", "family_id"),
        {"schema": PLATFORM_SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Constant across every rotation of one login, so reuse detection can
    #: revoke the entire lineage in a single statement.
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Organization the session is currently acting in; nullable because a user
    #: may authenticate before choosing one.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_usable_at(self, now: dt.datetime) -> bool:
        """A session may be exchanged only while live, unrotated and unexpired."""
        return self.revoked_at is None and self.rotated_at is None and self.expires_at > now


class PasswordResetToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One outstanding request to choose a new password.

    Not RLS-protected, for the same reason ``users`` is not: a password
    belongs to a global identity. The person redeeming one may belong to
    several organizations, or — having signed up and not yet founded or joined
    one — to none at all, and there is no organization to scope the row to.
    Isolation comes from the token: a row is reachable only by presenting the
    secret whose digest it holds, and never by listing.

    ``token_hash`` is a SHA-256 digest of a 48-byte urlsafe token, the same
    construction and the same reasoning as ``Session.refresh_token_hash``:
    generated entropy rather than a human-chosen secret, so it is not
    brute-forceable and the digest has to stay cheap to look up. The token
    itself exists only in the email.

    ``used_at`` rather than deleting the row on redemption. A used token that
    is presented again is a signal — either the person clicked twice, or
    somebody else has the link — and a deleted row is indistinguishable from
    one that never existed, which turns that signal into "invalid token" and
    loses it.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("uq_password_reset_tokens_token_hash", "token_hash", unique=True),
        Index("ix_password_reset_tokens_user_id", "user_id"),
        {"schema": PLATFORM_SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{PLATFORM_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Where the request came from, for the security event a person sees after
    #: the fact. Nullable because a request can arrive without one.
    requested_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    def is_redeemable_at(self, now: dt.datetime) -> bool:
        """A token may be spent once, before it expires."""
        return self.used_at is None and self.expires_at > now


__all__ = [
    "PLATFORM_SCHEMA",
    "PasswordResetToken",
    "Session",
    "User",
    "UserProfile",
    "UserStatus",
]
