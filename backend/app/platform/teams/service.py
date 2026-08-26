"""Use cases for the teams module — the module's public interface.

Two audiences, and they want very different things.

**Administrators** create departments and teams and move people between them.
Those are ordinary tenant-scoped CRUD operations, audited because they change
who can read whose records.

**The CRM's record-level visibility** wants one question answered:
:meth:`TeamService.peer_user_ids` — *whose records may this user also see?*
That is the whole of B02's contribution to authorization, and it is exposed
here rather than as a table for products to join against, because
ARCHITECTURE-BOUNDARIES.md rule 2 says products consume Platform through
services and rule 6 says a module owns its tables.

**Deleting is guarded, not cascading.** Removing a department with teams under
it is refused rather than silently orphaning or deleting them; removing a team
drops its memberships for real, so nobody keeps visibility through a team that
no longer exists.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import PageParams
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import AuditService, audit_for_session
from app.platform.auth.dependencies import Principal
from app.platform.teams.models import Department, Team, TeamMembership
from app.platform.teams.policies import MODULE
from app.platform.teams.repository import TeamRepository

logger = structlog.get_logger(__name__)

DEPARTMENT_ENTITY = "DEPARTMENT"
TEAM_ENTITY = "TEAM"


class TeamService:
    """Departments, teams, membership — and the peer read the CRM depends on."""

    def __init__(
        self, repository: TeamRepository, *, audit: AuditService | None = None
    ) -> None:
        self._repository = repository
        self._audit = audit or audit_for_session(repository.session)

    # --- The read products consume -----------------------------------------

    async def peer_user_ids(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> set[uuid.UUID]:
        """Users sharing at least one live team with ``user_id``.

        The single entry point for the team dimension of record-level
        visibility. Returns an empty set for somebody on no team, which is
        what makes ``VIEW_TEAM`` degrade to owner-only rather than to
        organization-wide — the safe direction.
        """
        return await self._repository.peer_user_ids(user_id, organization_id)

    # --- Departments -------------------------------------------------------

    async def list_departments(
        self, principal: Principal, *, params: PageParams
    ) -> tuple[Sequence[Department], int]:
        return await self._repository.list_departments(
            principal.organization_id, params=params
        )

    async def get_department(
        self, department_id: uuid.UUID, principal: Principal
    ) -> Department:
        department = await self._repository.get_department(
            department_id, principal.organization_id
        )
        if department is None:
            raise NotFoundError("Department not found.")
        return department

    async def create_department(self, principal: Principal, *, name: str) -> Department:
        name = name.strip()
        if await self._repository.department_name_exists(
            principal.organization_id, name
        ):
            raise ConflictError("A department with that name already exists.")

        department = Department(
            organization_id=principal.organization_id,
            name=name,
            created_by_id=principal.user_id,
            updated_by_id=principal.user_id,
        )
        await self._repository.add(department)
        await self._record(
            principal,
            AuditAction.DEPARTMENT_CREATED,
            DEPARTMENT_ENTITY,
            department.id,
            department.name,
        )
        return department

    async def update_department(
        self, department_id: uuid.UUID, principal: Principal, *, name: str
    ) -> Department:
        department = await self.get_department(department_id, principal)
        name = name.strip()
        if await self._repository.department_name_exists(
            principal.organization_id, name, exclude_id=department.id
        ):
            raise ConflictError("A department with that name already exists.")

        previous = department.name
        department.name = name
        department.updated_by_id = principal.user_id
        await self._repository.flush()
        await self._record(
            principal,
            AuditAction.DEPARTMENT_UPDATED,
            DEPARTMENT_ENTITY,
            department.id,
            department.name,
            details={"previous_name": previous},
        )
        return department

    async def delete_department(
        self, department_id: uuid.UUID, principal: Principal
    ) -> None:
        """Archive a department that has no teams under it.

        Refused while teams remain rather than cascading: the foreign key is
        ``RESTRICT`` for the same reason, and silently detaching or deleting a
        team would change who can see what as a side effect of tidying the org
        chart.
        """
        department = await self.get_department(department_id, principal)
        remaining = await self._repository.count_teams_in_department(
            department.id, principal.organization_id
        )
        if remaining:
            raise ConflictError(
                "That department still has teams. Move or delete them first.",
                details={"team_count": remaining},
            )

        department.updated_by_id = principal.user_id
        await self._repository.soft_delete(department)
        await self._record(
            principal,
            AuditAction.DEPARTMENT_DELETED,
            DEPARTMENT_ENTITY,
            department.id,
            department.name,
        )

    # --- Teams -------------------------------------------------------------

    async def list_teams(
        self,
        principal: Principal,
        *,
        params: PageParams,
        department_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Team], int, dict[uuid.UUID, int]]:
        teams, total = await self._repository.list_teams(
            principal.organization_id, params=params, department_id=department_id
        )
        counts = await self._repository.member_counts([team.id for team in teams])
        return teams, total, counts

    async def get_team(self, team_id: uuid.UUID, principal: Principal) -> Team:
        team = await self._repository.get_team(team_id, principal.organization_id)
        if team is None:
            raise NotFoundError("Team not found.")
        return team

    async def get_team_with_count(
        self, team_id: uuid.UUID, principal: Principal
    ) -> tuple[Team, int]:
        """One team and how many people are on it."""
        team = await self.get_team(team_id, principal)
        counts = await self._repository.member_counts([team.id])
        return team, counts.get(team.id, 0)

    async def create_team(
        self,
        principal: Principal,
        *,
        name: str,
        department_id: uuid.UUID | None = None,
    ) -> Team:
        name = name.strip()
        if await self._repository.team_name_exists(principal.organization_id, name):
            raise ConflictError("A team with that name already exists.")
        await self._require_department_in_org(department_id, principal)

        team = Team(
            organization_id=principal.organization_id,
            name=name,
            department_id=department_id,
            created_by_id=principal.user_id,
            updated_by_id=principal.user_id,
        )
        await self._repository.add(team)
        await self._record(
            principal,
            AuditAction.TEAM_CREATED,
            TEAM_ENTITY,
            team.id,
            team.name,
            details={"department_id": department_id},
        )
        return team

    async def update_team(
        self,
        team_id: uuid.UUID,
        principal: Principal,
        *,
        name: str | None = None,
        department_id: uuid.UUID | None = None,
        change_department: bool = False,
    ) -> Team:
        """Rename a team and/or move it between departments.

        ``change_department`` distinguishes "leave the department alone" from
        "detach it", which a bare ``None`` cannot express.
        """
        team = await self.get_team(team_id, principal)
        details: dict[str, object] = {}

        if name is not None:
            name = name.strip()
            if await self._repository.team_name_exists(
                principal.organization_id, name, exclude_id=team.id
            ):
                raise ConflictError("A team with that name already exists.")
            details["previous_name"] = team.name
            team.name = name

        if change_department:
            await self._require_department_in_org(department_id, principal)
            details["previous_department_id"] = team.department_id
            details["department_id"] = department_id
            team.department_id = department_id

        team.updated_by_id = principal.user_id
        await self._repository.flush()
        await self._record(
            principal, AuditAction.TEAM_UPDATED, TEAM_ENTITY, team.id, team.name, details
        )
        return team

    async def delete_team(self, team_id: uuid.UUID, principal: Principal) -> None:
        """Archive a team and drop its membership.

        The memberships go for real. A soft-deleted membership on an archived
        team would be a row the visibility predicate has to remember to
        exclude, and forgetting once would leave people reading each other's
        records through a team that no longer exists.
        """
        team = await self.get_team(team_id, principal)
        members = await self._repository.member_counts([team.id])
        await self._repository.remove_all_memberships(team.id)

        team.updated_by_id = principal.user_id
        await self._repository.soft_delete(team)
        await self._record(
            principal,
            AuditAction.TEAM_DELETED,
            TEAM_ENTITY,
            team.id,
            team.name,
            details={"members_removed": members.get(team.id, 0)},
        )

    # --- Membership --------------------------------------------------------

    async def list_members(
        self, team_id: uuid.UUID, principal: Principal, *, params: PageParams
    ) -> tuple[Sequence[TeamMembership], int]:
        await self.get_team(team_id, principal)
        return await self._repository.list_members(
            team_id, principal.organization_id, params=params
        )

    async def add_member(
        self, team_id: uuid.UUID, principal: Principal, *, user_id: uuid.UUID
    ) -> TeamMembership:
        """Put a user on a team, widening what both can see.

        Idempotent: adding somebody already on the team returns the existing
        membership rather than conflicting, so a double-submitted form does
        not surface as an error.
        """
        team = await self.get_team(team_id, principal)

        existing = await self._repository.get_membership(team.id, user_id)
        if existing is not None:
            return existing

        membership = TeamMembership(
            team_id=team.id, user_id=user_id, created_by_id=principal.user_id
        )
        await self._repository.add(membership)
        await self._record(
            principal,
            AuditAction.TEAM_MEMBER_ADDED,
            TEAM_ENTITY,
            team.id,
            team.name,
            details={"member_user_id": user_id},
        )
        logger.info(
            "team_member_added",
            team_id=str(team.id),
            member_user_id=str(user_id),
            organization_id=str(principal.organization_id),
        )
        return membership

    async def remove_member(
        self, team_id: uuid.UUID, principal: Principal, *, user_id: uuid.UUID
    ) -> None:
        team = await self.get_team(team_id, principal)
        membership = await self._repository.get_membership(team.id, user_id)
        if membership is None:
            raise NotFoundError("That user is not on this team.")

        await self._repository.remove_membership(membership)
        await self._record(
            principal,
            AuditAction.TEAM_MEMBER_REMOVED,
            TEAM_ENTITY,
            team.id,
            team.name,
            details={"member_user_id": user_id},
        )
        logger.info(
            "team_member_removed",
            team_id=str(team.id),
            member_user_id=str(user_id),
            organization_id=str(principal.organization_id),
        )

    # --- Internals ---------------------------------------------------------

    async def _require_department_in_org(
        self, department_id: uuid.UUID | None, principal: Principal
    ) -> None:
        """Reject a department id belonging to another tenant, or to nothing.

        Without this the foreign key would still hold — departments and teams
        share a database — so a crafted id could attach a team to another
        organization's department. The repository read is organization-scoped,
        which is what makes that impossible.
        """
        if department_id is None:
            return
        if await self._repository.get_department(
            department_id, principal.organization_id
        ) is None:
            raise NotFoundError("Department not found.")

    async def _record(
        self,
        principal: Principal,
        action: AuditAction,
        entity_type: str,
        entity_id: uuid.UUID,
        entity_label: str,
        details: dict[str, object] | None = None,
    ) -> None:
        await self._audit.record(
            organization_id=principal.organization_id,
            action=action,
            module=MODULE,
            actor_id=principal.user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label,
            details=details or {},
        )


def teams_for_session(session: AsyncSession) -> TeamService:
    """Build a :class:`TeamService` bound to an existing session."""
    return TeamService(TeamRepository(session))


__all__ = ["TeamService", "teams_for_session"]
