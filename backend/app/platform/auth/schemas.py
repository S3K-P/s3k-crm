"""Pydantic v2 contracts for the auth module.

SQLAlchemy models are never returned directly: every response is one of these
shapes, so a column added to a table cannot silently start leaking through the
API. ``password_hash`` in particular has no representation here at all.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

from app.platform.auth.models import UserStatus


class LoginRequest(BaseModel):
    """Credentials, plus an optional organization to start the session in."""

    email: EmailStr
    #: ``SecretStr`` keeps the value out of logs and ``repr`` output.
    password: SecretStr = Field(min_length=1, max_length=256)
    organization_id: uuid.UUID | None = None


class RefreshRequest(BaseModel):
    """Body form of refresh, for clients that cannot use cookies."""

    refresh_token: SecretStr | None = None


class TokenResponse(BaseModel):
    """The access token. The refresh token travels only in an httpOnly cookie.

    Returning the refresh token in the body would defeat the XSS protection the
    cookie exists to provide, so it is deliberately absent.
    """

    access_token: str
    token_type: str = "Bearer"  # noqa: S105 - an OAuth token *type*, not a secret
    expires_at: dt.datetime
    organization_id: uuid.UUID | None = None


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    first_name: str
    last_name: str
    avatar_url: str | None = None
    timezone: str
    locale: str
    phone: str | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    status: UserStatus
    email_verified_at: dt.datetime | None = None
    last_login_at: dt.datetime | None = None
    profile: UserProfileResponse | None = None


class MembershipSummary(BaseModel):
    """One organization the caller belongs to."""

    organization_id: uuid.UUID
    organization_name: str
    organization_slug: str
    status: str
    is_default: bool
    roles: list[str]


class CurrentUserResponse(BaseModel):
    """``GET /auth/me`` — identity, memberships and effective permissions.

    ``permissions`` is scoped to ``active_organization_id``: the same user can
    hold different roles in different organizations, so a permission list
    without its organization would be meaningless.
    """

    user: UserResponse
    memberships: list[MembershipSummary]
    active_organization_id: uuid.UUID | None
    permissions: list[str]


class RegisterUserRequest(BaseModel):
    """Administrative user provisioning."""

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=256)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)


class SignupRequest(BaseModel):
    """Self-service account creation — the public front door to S3K.

    Shaped identically to :class:`RegisterUserRequest` but kept separate: that
    one is an administrator provisioning somebody else inside an organization
    that already exists, this one is an anonymous stranger creating an identity
    with no tenant at all. They authorize differently and they will diverge
    (terms acceptance, captcha, email verification), so sharing the schema
    would couple two things that only look alike today.
    """

    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=256)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)


class ForgotPasswordRequest(BaseModel):
    """Ask for a reset link. Always answered identically — see the route."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Redeem a reset token for a new password."""

    token: SecretStr = Field(min_length=1, max_length=512)
    new_password: SecretStr = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: SecretStr = Field(min_length=1, max_length=256)
    new_password: SecretStr = Field(min_length=1, max_length=256)


__all__ = [
    "ChangePasswordRequest",
    "CurrentUserResponse",
    "ForgotPasswordRequest",
    "LoginRequest",
    "MembershipSummary",
    "RefreshRequest",
    "RegisterUserRequest",
    "ResetPasswordRequest",
    "SignupRequest",
    "TokenResponse",
    "UserProfileResponse",
    "UserResponse",
]
