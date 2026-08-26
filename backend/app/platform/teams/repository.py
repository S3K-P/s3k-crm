"""Data access for the teams module.

Every statement filters on ``organization_id`` explicitly. RLS on
``platform.departments`` and ``platform.teams`` is the backstop, not the plan
(doc 13, defence in depth).

``team_memberships`` has no ``organization_id`` of its own, so it is *always*
reached through a join or subquery on ``teams``. That is not an accident of
convenience: it is the only place the membership's tenant can be established,
and writing it any other way would let a membership be read or created against
a team in another organization.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.platform.teams.models import Department, Team, TeamMembership


class TeamRepository:
    """Tenant-scoped access to departments, teams and their membership."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """The session this repository writes through.

        Exposed so the service can append an audit record on the same
        transaction as the change it describes.
        """
        return self._session

    # --- Departments -------------------------------------------------------

    def _department_query(self, organization_id: uuid.UUID) -> Select[tuple[Department]]:
        return select(Department).where(
            Department.organization_id == organization_id,
            Department.deleted_at.is_(None),
        )

    async def get_department(
        self, department_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Department | None:
        result = await self._session.execute(
            self._department_query(organization_id).where(Department.id == department_id)
        )
        return result.scalar_one_or_none()

    async def list_departments(
        self, organization_id: uuid.UUID, *, params: PageParams
    ) -> tuple[Sequence[Department], int]:
        statement = self._department_query(organization_id)
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(statement.subquery())
                )
            ).scalar_one()
        )
        ordered = statement.order_by(Department.name.asc(), Department.id.asc())
        result = await self._session.execute(
            ordered.limit(params.limit).offset(params.offset)
        )
        return result.scalars().all(), total

    async def department_name_exists(
        self, organization_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None
    ) -> bool:
        statement = self._department_query(organization_id).where(
            func.lower(Department.name) == name.lower()
        )
        if exclude_id is not None:
            statement = statement.where(Department.id != exclude_id)
        result = await self._session.execute(select(statement.exists()))
        return bool(result.scalar_one())

    async def count_teams_in_department(
        self, department_id: uuid.UUID, organization_id: uuid.UUID
    ) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Team)
            .where(
                Team.department_id == department_id,
                Team.organization_id == organization_id,
                Team.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    # --- Teams -------------------------------------------------------------

    def _team_query(self, organization_id: uuid.UUID) -> Select[tuple[Team]]:
        return select(Team).where(
            Team.organization_id == organization_id, Team.deleted_at.is_(None)
        )

    async def get_team(
        self, team_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Team | None:
        result = await self._session.execute(
            self._team_query(organization_id).where(Team.id == team_id)
        )
        return result.scalar_one_or_none()

    async def list_teams(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        department_id: uuid.UUID | None = None,
    ) -> tuple[Sequence[Team], int]:
        statement = self._team_query(organization_id)
        if department_id is not None:
            statement = statement.where(Team.department_id == department_id)

        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(statement.subquery())
                )
            ).scalar_one()
        )
        ordered = statement.order_by(Team.name.asc(), Team.id.asc())
        result = await self._session.execute(
            ordered.limit(params.limit).offset(params.offset)
        )
        return result.scalars().all(), total

    async def team_name_exists(
        self, organization_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None
    ) -> bool:
        statement = self._team_query(organization_id).where(
            func.lower(Team.name) == name.lower()
        )
        if exclude_id is not None:
            statement = statement.where(Team.id != exclude_id)
        result = await self._session.execute(select(statement.exists()))
        return bool(result.scalar_one())

    async def member_counts(
        self, team_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Members per team, in one query.

        Batched rather than resolved per row: a lazy relationship would turn a
        page of twenty teams into twenty-one queries.
        """
        if not team_ids:
            return {}
        result = await self._session.execute(
            select(TeamMembership.team_id, func.count())
            .where(TeamMembership.team_id.in_(team_ids))
            .group_by(TeamMembership.team_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    # --- Membership --------------------------------------------------------

    async def list_members(
        self, team_id: uuid.UUID, organization_id: uuid.UUID, *, params: PageParams
    ) -> tuple[Sequence[TeamMembership], int]:
        """Members of one team, scoped through the team's organization.

        The join to ``teams`` is what establishes the tenant — see the module
        docstring.
        """
        statement = (
            select(TeamMembership)
            .join(Team, Team.id == TeamMembership.team_id)
            .where(
                TeamMembership.team_id == team_id,
                Team.organization_id == organization_id,
                Team.deleted_at.is_(None),
            )
        )
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(statement.subquery())
                )
            ).scalar_one()
        )
        ordered = statement.order_by(
            TeamMembership.joined_at.asc(), TeamMembership.id.asc()
        )
        result = await self._session.execute(
            ordered.limit(params.limit).offset(params.offset)
        )
        return result.scalars().all(), total

    async def get_membership(
        self, team_id: uuid.UUID, user_id: uuid.UUID
    ) -> TeamMembership | None:
        result = await self._session.execute(
            select(TeamMembership).where(
                TeamMembership.team_id == team_id, TeamMembership.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def peer_user_ids(
        self, user_id: uuid.UUID, organization_id: uuid.UUID
    ) -> set[uuid.UUID]:
        """Every user sharing at least one live team with ``user_id``.

        One query, self-joined through ``team_memberships``. Deleted teams are
        excluded, so archiving a team withdraws the visibility its members had
        through it without any other bookkeeping.

        Returns the caller as well when they are on any team; callers union
        this with their own id regardless, so the distinction does not matter
        to them.
        """
        mine = (
            select(TeamMembership.team_id)
            .join(Team, Team.id == TeamMembership.team_id)
            .where(
                TeamMembership.user_id == user_id,
                Team.organization_id == organization_id,
                Team.deleted_at.is_(None),
            )
            .scalar_subquery()
        )
        result = await self._session.execute(
            select(TeamMembership.user_id).where(TeamMembership.team_id.in_(mine)).distinct()
        )
        return set(result.scalars().all())

    # --- Writes ------------------------------------------------------------

    async def add(self, instance: Department | Team | TeamMembership) -> None:
        self._session.add(instance)
        await self._session.flush()

    async def flush(self) -> None:
        await self._session.flush()

    async def soft_delete(self, instance: Department | Team) -> None:
        instance.deleted_at = dt.datetime.now(dt.UTC)
        await self._session.flush()

    async def remove_membership(self, membership: TeamMembership) -> None:
        await self._session.delete(membership)
        await self._session.flush()

    async def remove_all_memberships(self, team_id: uuid.UUID) -> None:
        """Drop every membership of a team being deleted.

        The rows go for real rather than being soft-deleted, because a team
        nobody is on must not keep granting visibility through stale rows —
        the same reasoning as ``TeamMembership`` having no soft delete at all.
        """
        await self._session.execute(
            delete(TeamMembership).where(TeamMembership.team_id == team_id)
        )
        await self._session.flush()


__all__ = ["TeamRepository"]
