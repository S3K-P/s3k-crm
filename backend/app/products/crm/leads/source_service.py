"""Lead source business rules (plan P2-W10-BE-02).

Lead sources live in the ``leads`` module rather than a module of their own:
``LeadSource`` is declared in ``leads/models.py`` because it exists only to
classify leads, and ARCHITECTURE-BOUNDARIES.md rule 2 forbids another module
reaching into this one's models. They keep their own service and router so the
``lead_sources`` permission module maps to a real API surface.

The one rule beyond CRUD is that a name is unique within an organization —
enforced by ``uq_lead_sources_organization_id_name`` in the database and
checked here first so the caller gets a 409 with a useful message rather than
an integrity error.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.products.crm.leads.models import Lead, LeadSource, LeadSourceStatus
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService


class DuplicateLeadSourceError(ConflictError):
    """A lead source with that name already exists in this organization."""

    code = "duplicate_lead_source"
    message = "A lead source with that name already exists."


class LeadSourceInUseError(ConflictError):
    """The lead source is still referenced by leads."""

    code = "lead_source_in_use"
    message = (
        "This lead source is still assigned to leads. Deactivate it instead of removing it."
    )


class LeadSourceService(TenantScopedService[LeadSource]):
    entity_name = "Lead source"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, LeadSource), LeadSource)
        self._session = session

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        status: LeadSourceStatus | None = None,
        category: str | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(LeadSource.name).like(term),
                    func.lower(func.coalesce(LeadSource.category, "")).like(term),
                )
            )
        if status is not None:
            filters.append(LeadSource.status == status)
        if category:
            filters.append(LeadSource.category == category)
        return filters

    async def list_sources(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[LeadSource], int]:
        return await self.list(organization_id, params=params, filters=filters)

    async def lead_counts(self, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """How many live leads each source has produced, keyed by source id.

        One grouped query for the whole page: the list screen shows this
        against every row, and asking per row would be a classic N+1.
        """
        result = await self._session.execute(
            select(Lead.lead_source_id, func.count())
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.lead_source_id.is_not(None),
            )
            .group_by(Lead.lead_source_id)
        )
        return {row[0]: int(row[1]) for row in result.all() if row[0] is not None}

    # --- Commands ----------------------------------------------------------

    async def create_source(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> LeadSource:
        """Create a lead source, refusing a name already in use.

        Unlike accounts and contacts this blocks rather than warns: the unique
        constraint means a duplicate cannot be written anyway, so offering an
        override would be a lie.
        """
        name = str(values.get("name", "")).strip()
        if await self._name_exists(organization_id, name):
            raise DuplicateLeadSourceError
        return await self.create(
            organization_id=organization_id, actor_id=actor_id, values=values
        )

    async def update_source(
        self,
        source: LeadSource,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> LeadSource:
        """Patch a lead source, re-checking uniqueness on a rename."""
        new_name = values.get("name")
        if (
            new_name
            and str(new_name).strip().lower() != source.name.lower()
            and await self._name_exists(source.organization_id, str(new_name).strip())
        ):
            raise DuplicateLeadSourceError
        return await self.update(source, actor_id=actor_id, values=values)

    async def archive_source(
        self, source: LeadSource, *, actor_id: uuid.UUID | None
    ) -> LeadSource:
        """Archive a source once no live lead still points at it.

        Removing one that is in use would leave those leads reporting a source
        the API no longer returns, quietly corrupting source attribution.
        """
        if await self._lead_count(source) > 0:
            raise LeadSourceInUseError
        return await self.soft_delete(source, actor_id=actor_id)

    # --- Internals ---------------------------------------------------------

    async def _name_exists(self, organization_id: uuid.UUID, name: str) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(LeadSource)
            .where(
                LeadSource.organization_id == organization_id,
                LeadSource.deleted_at.is_(None),
                func.lower(LeadSource.name) == name.lower(),
            )
        )
        return int(result.scalar_one()) > 0

    async def _lead_count(self, source: LeadSource) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.organization_id == source.organization_id,
                Lead.lead_source_id == source.id,
                Lead.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())


__all__ = ["DuplicateLeadSourceError", "LeadSourceInUseError", "LeadSourceService"]
