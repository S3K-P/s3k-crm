"""Inviting people into an organization, and redeeming those invitations.

**The security shape, in one place.**

*Issuing* requires ``users.CREATE`` in the organization the invitation is for,
and the organization is taken from the caller's verified tenant context — never
from the payload — so an administrator cannot invite somebody into a tenant
they do not administer.

*Redeeming* requires an authenticated user whose **own** email matches the
invited address. The token alone is deliberately not sufficient. A link that
worked for whoever held it would turn a forwarded email, a shared inbox or a
leaked chat message into organization access, and the invitation table is
RLS-exempt precisely because redemption happens before membership — so the
token is the only other thing standing in front of the tenant. Requiring both
means an intercepted link is useless without the invited person's password.

*The token itself* is 256 bits from :func:`secrets.token_urlsafe`, returned to
the inviting administrator exactly once and stored only as a SHA-256 digest.
Nothing can recover it from the database, so a dump yields no usable
invitations.

**On delivery.** There is no email infrastructure in this codebase — the
notifications module is an unimplemented Phase 0 placeholder — so the token is
returned to the inviting administrator once and they pass the link on
themselves. That is a real, complete flow rather than a pretend one. The link
is composed by the frontend, which knows its own origin; when an email backend
arrives it becomes a second consumer of the same token at the point of issue,
and nothing here has to change.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid

import structlog
from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ConflictError
from app.platform.organizations.models import (
    InvitationStatus,
    OrganizationInvitation,
)

logger = structlog.get_logger(__name__)

#: How long an invitation stays redeemable. Long enough to survive a weekend
#: and a forwarded message, short enough that a stale link in an old mailbox
#: stops working.
INVITATION_TTL_DAYS = 14

#: ``token_urlsafe(32)`` is 32 random bytes — 256 bits — rendered as ~43 URL
#: characters. Guessing one is not a threat model.
TOKEN_BYTES = 32


class InvitationNotRedeemableError(AppError):
    """The token is unknown, already used, revoked, or past its expiry.

    Deliberately one error for all four. Distinguishing them would let a caller
    holding a random string learn whether it was ever a real invitation, and
    none of the four has a different remedy: ask the administrator to send a
    fresh one.
    """

    status_code = status.HTTP_404_NOT_FOUND
    code = "invitation_not_redeemable"
    message = "This invitation link is no longer valid. Ask an administrator to resend it."


class InvitationAddressMismatchError(AppError):
    """The signed-in user is not the person who was invited."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "invitation_address_mismatch"
    message = (
        "This invitation was issued to a different email address. "
        "Sign in as the invited user to accept it."
    )


def hash_token(token: str) -> str:
    """The digest stored in ``token_hash``.

    SHA-256 rather than a password hash on purpose: the token is 256 bits of
    machine-generated entropy, not a human-chosen secret, so there is nothing
    for a slow KDF to protect against and the lookup has to be a single indexed
    equality test.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class InvitationRepository:
    """Data access for invitations.

    **Every administrator-facing query filters on ``organization_id``.** The
    table carries no RLS policy (see the model and the migration), so this
    class *is* the tenant isolation for it. A query added here without that
    filter is a cross-tenant leak, not a style problem.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session

    async def add(self, invitation: OrganizationInvitation) -> None:
        self._session.add(invitation)
        await self._session.flush()

    async def get_by_token_hash(self, token_hash: str) -> OrganizationInvitation | None:
        """The only lookup not scoped by organization — it cannot be.

        Redemption happens before membership exists, so there is no tenant to
        filter by; the token digest is the whole credential, and it is unique.
        """
        result = await self._session.execute(
            select(OrganizationInvitation).where(
                OrganizationInvitation.token_hash == token_hash
            )
        )
        return result.scalar_one_or_none()

    async def get_for_organization(
        self, *, invitation_id: uuid.UUID, organization_id: uuid.UUID
    ) -> OrganizationInvitation | None:
        result = await self._session.execute(
            select(OrganizationInvitation).where(
                OrganizationInvitation.id == invitation_id,
                OrganizationInvitation.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_organization(
        self, organization_id: uuid.UUID
    ) -> list[OrganizationInvitation]:
        result = await self._session.execute(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.organization_id == organization_id)
            .order_by(OrganizationInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_pending_for_email(
        self, *, organization_id: uuid.UUID, email: str
    ) -> OrganizationInvitation | None:
        result = await self._session.execute(
            select(OrganizationInvitation).where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.email == email,
                OrganizationInvitation.status == InvitationStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()


class InvitationService:
    """Issuing, listing, revoking and redeeming invitations."""

    def __init__(self, repository: InvitationRepository) -> None:
        self._repository = repository

    async def invite(
        self,
        *,
        organization_id: uuid.UUID,
        email: str,
        role_id: uuid.UUID | None,
        invited_by_id: uuid.UUID,
        now: dt.datetime | None = None,
    ) -> tuple[OrganizationInvitation, str]:
        """Create an invitation, returning it **and its one-time token**.

        The plaintext token is returned here and nowhere else; it is not stored
        and cannot be read back afterwards. A caller that loses it must revoke
        and re-invite.

        Raises:
            ConflictError: a live invitation already exists for that address.
                Re-inviting is revoke-then-invite, so an administrator cannot
                accidentally leave two working links for one person.
        """
        now = now or dt.datetime.now(dt.UTC)
        normalised = email.strip().lower()

        existing = await self._repository.get_pending_for_email(
            organization_id=organization_id, email=normalised
        )
        if existing is not None and existing.is_redeemable(now=now):
            raise ConflictError("That address already has a pending invitation.")
        if existing is not None:
            # Expired but still PENDING: retire it so the partial unique index
            # does not block the replacement.
            existing.status = InvitationStatus.REVOKED

        token = secrets.token_urlsafe(TOKEN_BYTES)
        invitation = OrganizationInvitation(
            organization_id=organization_id,
            email=normalised,
            role_id=role_id,
            token_hash=hash_token(token),
            status=InvitationStatus.PENDING,
            expires_at=now + dt.timedelta(days=INVITATION_TTL_DAYS),
            invited_by_id=invited_by_id,
        )
        await self._repository.add(invitation)
        logger.info(
            "invitation_created",
            organization_id=str(organization_id),
            invited_by_id=str(invited_by_id),
        )
        return invitation, token

    async def list_invitations(
        self, organization_id: uuid.UUID
    ) -> list[OrganizationInvitation]:
        return await self._repository.list_for_organization(organization_id)

    async def revoke(
        self, *, invitation_id: uuid.UUID, organization_id: uuid.UUID
    ) -> OrganizationInvitation | None:
        """Withdraw a pending invitation. Returns ``None`` if it is not theirs.

        Scoped by ``organization_id`` so an administrator cannot revoke an
        invitation belonging to another tenant by guessing its id.
        """
        invitation = await self._repository.get_for_organization(
            invitation_id=invitation_id, organization_id=organization_id
        )
        if invitation is None:
            return None
        if invitation.status is InvitationStatus.PENDING:
            invitation.status = InvitationStatus.REVOKED
            await self._repository.session.flush()
            logger.info("invitation_revoked", invitation_id=str(invitation_id))
        return invitation

    async def peek(self, token: str, *, now: dt.datetime | None = None) -> OrganizationInvitation:
        """Resolve a token without redeeming it, so the UI can name the tenant.

        Read-only, and it reveals only the organization the holder was already
        given a link to. It does **not** check the caller's address: the accept
        screen has to be able to say "you were invited to Acme, sign in as
        ada@acme.com" to somebody who is not signed in yet.

        Raises:
            InvitationNotRedeemableError: unknown, used, revoked or expired.
        """
        now = now or dt.datetime.now(dt.UTC)
        invitation = await self._repository.get_by_token_hash(hash_token(token))
        if invitation is None or not invitation.is_redeemable(now=now):
            raise InvitationNotRedeemableError
        return invitation

    async def redeem(
        self,
        *,
        token: str,
        user_id: uuid.UUID,
        user_email: str,
        now: dt.datetime | None = None,
    ) -> OrganizationInvitation:
        """Mark an invitation accepted for ``user_id``.

        Does **not** create the membership — that is the organizations
        service's job, and the caller sequences the two in one transaction.
        Keeping them apart means this function has one responsibility and the
        membership is created by the code that already knows how.

        Raises:
            InvitationNotRedeemableError: unknown, used, revoked or expired.
            InvitationAddressMismatchError: the signed-in user is not the
                invitee. This is the check that makes a leaked link useless.
        """
        now = now or dt.datetime.now(dt.UTC)
        invitation = await self._repository.get_by_token_hash(hash_token(token))
        if invitation is None or not invitation.is_redeemable(now=now):
            raise InvitationNotRedeemableError

        if invitation.email != user_email.strip().lower():
            logger.warning(
                "invitation_address_mismatch",
                invitation_id=str(invitation.id),
                user_id=str(user_id),
            )
            raise InvitationAddressMismatchError

        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = now
        invitation.accepted_by_id = user_id
        await self._repository.session.flush()
        logger.info(
            "invitation_accepted",
            invitation_id=str(invitation.id),
            organization_id=str(invitation.organization_id),
            user_id=str(user_id),
        )
        return invitation


def invitations_for_session(session: AsyncSession) -> InvitationService:
    """Build the service from a session, for callers holding only that."""
    return InvitationService(InvitationRepository(session))


__all__ = [
    "INVITATION_TTL_DAYS",
    "InvitationAddressMismatchError",
    "InvitationNotRedeemableError",
    "InvitationRepository",
    "InvitationService",
    "hash_token",
    "invitations_for_session",
]
