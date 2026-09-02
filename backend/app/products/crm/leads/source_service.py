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

import structlog
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.products.crm.leads.models import Lead, LeadSource, LeadSourceStatus
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService

logger = structlog.get_logger(__name__)

#: Starter sources seeded at provisioning so attribution works on day one.
#: Broad enough to cover the common channels without pretending to know a
#: particular tenant's marketing mix — they are ordinary rows, renameable
#: and deletable like any other.
DEFAULT_LEAD_SOURCES: tuple[tuple[str, str], ...] = (
    # (name, category)
    ("Website", "Inbound"),
    ("Referral", "Inbound"),
    ("Email Campaign", "Outbound"),
    ("Cold Outreach", "Outbound"),
    ("Event", "Marketing"),
    ("Partner", "Channel"),
)


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

    # --- Provisioning ------------------------------------------------------

    async def ensure_default_sources(
        self, organization_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> Sequence[LeadSource]:
        """Seed the starter lead sources, skipping any that already exist.

        Attribution is the reason lead sources are an entity in S3K rather than
        a picklist (analysis §4.6): cost-per-lead and source ROI are only
        answerable because a source is a row that can carry its own data. None
        of that works if the first lead form shows an empty dropdown, which
        teaches people to leave the field blank — and a blank source is a lead
        that can never be attributed to anything.

        **Idempotent per source, not per organization.** Checking "does this
        organization have any sources" and bailing out would mean an
        organization that deleted one of them never gets it back, and a later
        addition to the defaults would never reach an existing tenant. Each
        name is checked on its own instead.

        Matching is case-insensitive and ignores archived rows, mirroring
        ``_name_exists`` and the partial unique index behind it — otherwise the
        pre-check passes, the INSERT collides, and provisioning fails with a
        500 on its second run.

        Returns:
            The sources this call created, which is empty on a repeat run.
        """
        existing = await self._session.execute(
            select(func.lower(LeadSource.name)).where(
                LeadSource.organization_id == organization_id,
                LeadSource.deleted_at.is_(None),
            )
        )
        present = {str(name) for name in existing.scalars().all()}

        created: list[LeadSource] = []
        for name, category in DEFAULT_LEAD_SOURCES:
            if name.lower() in present:
                continue
            source = LeadSource(
                organization_id=organization_id,
                name=name,
                category=category,
                status=LeadSourceStatus.ACTIVE,
                created_by_id=actor_id,
                updated_by_id=actor_id,
            )
            self._session.add(source)
            created.append(source)

        if created:
            await self._session.flush()
            logger.info(
                "default_lead_sources_created",
                organization_id=str(organization_id),
                count=len(created),
            )
        return created

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


__all__ = [
    "DEFAULT_LEAD_SOURCES",
    "DuplicateLeadSourceError",
    "LeadSourceInUseError",
    "LeadSourceService",
]
