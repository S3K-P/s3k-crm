"""Data access for organizations and memberships.

Neither table carries an RLS policy (see the note in the Phase 1 migration), so
**every method here must filter explicitly**. A membership query that forgets
its ``user_id`` predicate is a cross-tenant disclosure.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.platform.auth.models import User, UserProfile
from app.platform.organizations.models import (
    MembershipStatus,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)


class OrganizationRepository:
    """Queries over ``organizations`` and ``organization_memberships``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """The session this repository reads and writes through.

        Exposed for the same reason ``TenantScopedRepository`` exposes it: so
        the service can provision a new organization's product entitlements on
        the *same* transaction that created it, rather than taking a second
        dependency in its constructor. Not an invitation to build queries for
        this module's tables elsewhere.
        """
        return self._session

    # --- Organizations -----------------------------------------------------

    async def get(self, organization_id: uuid.UUID) -> Organization | None:
        result = await self._session.execute(
            select(Organization).where(
                Organization.id == organization_id, Organization.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(
            select(Organization).where(
                Organization.slug == slug, Organization.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()

    async def add(self, organization: Organization) -> Organization:
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Organization]:
        """Organizations the user holds any membership in."""
        result = await self._session.execute(
            select(Organization)
            .join(
                OrganizationMembership,
                OrganizationMembership.organization_id == Organization.id,
            )
            .where(
                OrganizationMembership.user_id == user_id,
                Organization.deleted_at.is_(None),
            )
            .order_by(Organization.name)
        )
        return result.scalars().all()

    # --- Memberships -------------------------------------------------------

    def _membership_query(self) -> Select[tuple[OrganizationMembership]]:
        return select(OrganizationMembership).options(
            selectinload(OrganizationMembership.organization)
        )

    async def get_membership(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> OrganizationMembership | None:
        """The membership joining one user to one organization, if any."""
        result = await self._session.execute(
            self._membership_query().where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_memberships_for_user(
        self, user_id: uuid.UUID
    ) -> Sequence[OrganizationMembership]:
        result = await self._session.execute(
            self._membership_query()
            .where(OrganizationMembership.user_id == user_id)
            .order_by(OrganizationMembership.created_at)
        )
        return result.scalars().all()

    async def list_memberships_in_organization(
        self, organization_id: uuid.UUID, *, limit: int, offset: int
    ) -> Sequence[OrganizationMembership]:
        result = await self._session.execute(
            self._membership_query()
            .where(OrganizationMembership.organization_id == organization_id)
            .order_by(OrganizationMembership.created_at)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def member_identities(
        self, organization_id: uuid.UUID, user_ids: Collection[uuid.UUID]
    ) -> Sequence[tuple[uuid.UUID, str, str | None]]:
        """``(user_id, email, full_name)`` for members of this organization.

        Scoped by the membership join, not only by the ids passed in: a caller
        that supplies an id belonging to another tenant gets no row back
        rather than that person's email address. The ids come from CRM
        ``owner_id`` columns, which are ordinary data — treating them as
        untrusted here is what keeps a crafted or stale value from becoming a
        directory lookup across the tenant boundary.

        One query for a whole page of rows, in the shape
        ``AuditService._resolve_actors`` already uses for the same problem.
        """
        if not user_ids:
            return []
        result = await self._session.execute(
            select(User.id, User.email, UserProfile.first_name, UserProfile.last_name)
            .join(
                OrganizationMembership,
                OrganizationMembership.user_id == User.id,
            )
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                User.id.in_(list(user_ids)),
            )
        )
        rows: list[tuple[uuid.UUID, str, str | None]] = []
        for user_id, email, first_name, last_name in result.all():
            name = f"{first_name or ''} {last_name or ''}".strip()
            rows.append((user_id, email, name or None))
        return rows

    async def count_memberships_in_organization(self, organization_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(OrganizationMembership.organization_id == organization_id)
        )
        return int(result.scalar_one())

    async def add_membership(
        self, membership: OrganizationMembership
    ) -> OrganizationMembership:
        self._session.add(membership)
        await self._session.flush()
        return membership

    async def has_active_membership(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """The single predicate tenant isolation ultimately rests on.

        Requires the membership to be ACTIVE *and* the organization itself to
        be ACTIVE and not soft-deleted: suspending an organization must cut off
        its members immediately, not just hide it from listings.
        """
        result = await self._session.execute(
            select(func.count())
            .select_from(OrganizationMembership)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
                Organization.status == OrganizationStatus.ACTIVE,
                Organization.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one()) > 0

    async def default_organization_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        """The organization to open a session in when the client names none.

        Prefers the membership flagged default, otherwise the oldest active
        one, so a user with exactly one organization never has to choose.
        """
        result = await self._session.execute(
            select(OrganizationMembership.organization_id)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
                Organization.status == OrganizationStatus.ACTIVE,
                Organization.deleted_at.is_(None),
            )
            .order_by(
                OrganizationMembership.is_default.desc(),
                OrganizationMembership.created_at.asc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


__all__ = ["OrganizationRepository"]
