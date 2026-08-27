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
from fastapi import status as http_status

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import AuditService
from app.platform.authorization.catalog import ADMIN_ROLE
from app.platform.authorization.service import AuthorizationService
from app.platform.organizations.models import (
    MembershipStatus,
    Organization,
    OrganizationMembership,
)
from app.platform.organizations.repository import OrganizationRepository

logger = structlog.get_logger(__name__)


class LastAdministratorError(AppError):
    """The change would leave the organization with no active administrator."""

    status_code = http_status.HTTP_409_CONFLICT
    code = "last_administrator"
    message = (
        "This organization must keep at least one active administrator. "
        "Grant the Admin role to another active member first."
    )

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated slug derived from a name."""
    return _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")


#: Permission module membership changes are recorded under. Adding, suspending
#: or reinstating a member is a ``users``-level act rather than an
#: ``organizations`` one: it changes what a *person* can reach, which is the
#: question an audit reader is asking.
USERS_MODULE = "users"


class OrganizationService:
    """Creating organizations and managing who belongs to them."""

    def __init__(
        self, repository: OrganizationRepository, *, audit: AuditService | None = None
    ) -> None:
        self._repository = repository
        # Optional so ``app.bootstrap`` and test fixtures can provision an
        # organization before any tenant context or request exists.
        self._audit = audit

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

        # Entitle the new tenant to the products it is created with (ADR-011).
        # In the same transaction as the organization itself: a tenant that
        # exists but cannot open any product is a half-provisioned state
        # somebody would have to notice and repair by hand, and the product
        # gate would refuse them with a 403 that looks like a bug.
        #
        # Imported here rather than at module scope because the products
        # service imports organization types; a top-level import is a cycle.
        from app.platform.products.service import products_for_session

        await products_for_session(self._repository.session).grant_default_products(
            organization.id
        )

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
        actor_id: uuid.UUID | None = None,
    ) -> OrganizationMembership:
        """Add a user to an organization.

        Args:
            actor_id: the administrator granting access, for the audit record.
                Distinct from ``user_id``, which is who *received* it.

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

        if self._audit is not None:
            await self._audit.record(
                organization_id=organization_id,
                action=AuditAction.MEMBER_ADDED,
                module=USERS_MODULE,
                actor_id=actor_id,
                entity_type="USER",
                entity_id=user_id,
                details={
                    "membership_id": membership.id,
                    "status": status,
                    "is_default": is_default,
                },
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
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        status: MembershipStatus,
        actor_id: uuid.UUID | None = None,
    ) -> OrganizationMembership:
        """Activate or suspend a member.

        Suspension takes effect on the next request: the membership verifier
        reads status on every call, so access is cut immediately rather than
        when the member's token happens to expire.

        That immediacy is exactly why this is audited: someone losing access
        mid-session has no in-app trace of why, and the trail is where the
        answer lives. Both the old and the new status are recorded, because
        "suspended" reads very differently depending on what it replaced.
        """
        membership = await self.get_membership(
            organization_id=organization_id, user_id=user_id
        )
        previous = membership.status
        membership.status = status
        logger.info(
            "membership_status_changed",
            organization_id=str(organization_id),
            user_id=str(user_id),
            status=status.value,
        )

        if self._audit is not None and previous is not status:
            await self._audit.record(
                organization_id=organization_id,
                action=AuditAction.MEMBER_STATUS_CHANGED,
                module=USERS_MODULE,
                actor_id=actor_id,
                entity_type="USER",
                entity_id=user_id,
                details={
                    "membership_id": membership.id,
                    "from": previous,
                    "to": status,
                },
            )
        return membership

    async def is_active_member(
        self, *, organization_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        return await self._repository.has_active_membership(
            organization_id=organization_id, user_id=user_id
        )

    async def active_membership_ids(self, organization_id: uuid.UUID) -> set[uuid.UUID]:
        """Ids of every membership currently granting access to the tenant."""
        memberships = await self._repository.list_memberships_in_organization(
            organization_id, limit=_MEMBERSHIP_SCAN_LIMIT, offset=0
        )
        return {m.id for m in memberships if m.grants_access}


#: Upper bound when scanning memberships for the administrator guard. An
#: organization with more members than this would need a counting query; the
#: guard is written against the same window the admin UI itself pages over.
_MEMBERSHIP_SCAN_LIMIT = 500


async def ensure_administrator_remains(
    *,
    organizations: OrganizationService,
    authorization: AuthorizationService,
    organization_id: uuid.UUID,
    losing_admin_membership_id: uuid.UUID,
) -> None:
    """Refuse a change that would remove the organization's last administrator.

    Called before suspending a member and before revoking a role, with the
    membership that is about to stop being an active administrator. If no
    *other* active membership holds Admin, the change is rejected — otherwise
    an administrator can lock every human, including themselves, out of user
    management and role assignment with a single click, and the only recovery
    is direct database access.

    The two halves come from the modules that own them: which memberships hold
    Admin is an authorization question, which are active is an organizations
    question. Neither module reads the other's tables.
    """
    admin_membership_ids = await authorization.membership_ids_with_role(
        organization_id=organization_id, role_name=ADMIN_ROLE
    )
    if losing_admin_membership_id not in admin_membership_ids:
        # Not an administrator to begin with: nothing to protect.
        return

    active_ids = await organizations.active_membership_ids(organization_id)
    remaining = (admin_membership_ids & active_ids) - {losing_admin_membership_id}
    if not remaining:
        logger.warning(
            "last_administrator_change_blocked",
            organization_id=str(organization_id),
            membership_id=str(losing_admin_membership_id),
        )
        raise LastAdministratorError


__all__ = [
    "USERS_MODULE",
    "LastAdministratorError",
    "OrganizationService",
    "ensure_administrator_remains",
    "slugify",
]
