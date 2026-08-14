"""Organization and membership use cases.

The membership rules here are the foundation of tenant isolation: a user may
only ever act inside an organization they hold an ACTIVE membership in, and
that check is made against the database on every request rather than trusted
from a token or a header.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence

import structlog

from app.core.exceptions import ConflictError, NotFoundError
from app.platform.organizations.models import (
    MembershipStatus,
    Organization,
    OrganizationMembership,
)
from app.platform.organizations.repository import OrganizationRepository

logger = structlog.get_logger(__name__)

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated slug derived from a name."""
    return _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")


class OrganizationService:
    """Creating organizations and managing who belongs to them."""

    def __init__(self, repository: OrganizationRepository) -> None:
        self._repository = repository

    # --- Organizations -----------------------------------------------------

    async def create_organization(
        self, *, name: str, slug: str | None = None, created_by_id: uuid.UUID | None = None
    ) -> Organization:
        """Create a tenant.

        Raises:
            ConflictError: the slug is already taken. Slugs are global, so this
                is checked without tenant scope.
        """
        candidate = slugify(slug or name)
        if not candidate:
            raise ConflictError(
                "Organization name must contain at least one alphanumeric character."
            )
        if await self._repository.get_by_slug(candidate) is not None:
            raise ConflictError(f"The slug '{candidate}' is already in use.")

        organization = Organization(name=name.strip(), slug=candidate)
        await self._repository.add(organization)
        logger.info(
            "organization_created",
            organization_id=str(organization.id),
            created_by_id=str(created_by_id) if created_by_id else None,
        )
        return organization

    async def get_organization(self, organization_id: uuid.UUID) -> Organization:
        organization = await self._repository.get(organization_id)
        if organization is None:
            raise NotFoundError("Organization not found.")
        return organization

    async def get_organization_for_member(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> Organization:
        """Fetch an organization only if the caller belongs to it.

        Returns 404 rather than 403 for a non-member: confirming that an
        organization exists is itself information a stranger should not get.
        """
        if not await self._repository.has_active_membership(
            organization_id=organization_id, user_id=user_id
        ):
            raise NotFoundError("Organization not found.")
        return await self.get_organization(organization_id)

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Organization]:
        return await self._repository.list_for_user(user_id)

    # --- Memberships -------------------------------------------------------

    async def add_member(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        status: MembershipStatus = MembershipStatus.ACTIVE,
        is_default: bool = False,
    ) -> OrganizationMembership:
        """Add a user to an organization.

        Raises:
            ConflictError: the user is already a member. The unique constraint
                would catch it anyway; failing here gives a usable message.
        """
        existing = await self._repository.get_membership(
            organization_id=organization_id, user_id=user_id
        )
        if existing is not None:
            raise ConflictError("That user is already a member of this organization.")

        membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=user_id,
            status=status,
            is_default=is_default,
        )
        await self._repository.add_membership(membership)
        logger.info(
            "membership_created",
            organization_id=str(organization_id),
            user_id=str(user_id),
            status=status.value,
        )
        return membership

    async def get_membership(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMembership:
        membership = await self._repository.get_membership(
            organization_id=organization_id, user_id=user_id
        )
        if membership is None:
            raise NotFoundError("Membership not found.")
        return membership

    async def list_members(
        self, organization_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> tuple[Sequence[OrganizationMembership], int]:
        items = await self._repository.list_memberships_in_organization(
            organization_id, limit=limit, offset=offset
        )
        total = await self._repository.count_memberships_in_organization(organization_id)
        return items, total

    async def list_memberships_for_user(
        self, user_id: uuid.UUID
    ) -> Sequence[OrganizationMembership]:
        return await self._repository.list_memberships_for_user(user_id)

    async def set_member_status(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID, status: MembershipStatus
    ) -> OrganizationMembership:
        """Activate or suspend a member.

        Suspension takes effect on the next request: the membership verifier
        reads status on every call, so access is cut immediately rather than
        when the member's token happens to expire.
        """
        membership = await self.get_membership(
            organization_id=organization_id, user_id=user_id
        )
        membership.status = status
        logger.info(
            "membership_status_changed",
            organization_id=str(organization_id),
            user_id=str(user_id),
            status=status.value,
        )
        return membership

    async def is_active_member(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        return await self._repository.has_active_membership(
            organization_id=organization_id, user_id=user_id
        )


__all__ = ["OrganizationService", "slugify"]
