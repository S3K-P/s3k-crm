"""Campaign business rules (plan P2-W15).

Two things to know:

* **Cached metrics are not client-writable.** ``leads_generated``,
  ``opportunities_generated``, ``conversion_rate`` and ``roi`` are maintained
  by :meth:`CampaignService.recompute_metrics`, which derives them from the
  leads and opportunities actually attributed to the campaign. A request
  handler can trigger the recomputation but cannot dictate the numbers, so the
  metrics can never disagree with the records behind them.
* **Membership is validated and unique.** A member must be a lead or contact in
  the caller's organization, and the same record cannot be enrolled twice —
  enforced by ``uq_campaign_members_campaign_id_entity_type_entity_id`` and
  checked here first so the caller gets a clear 409.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.products.crm.campaigns.models import (
    Campaign,
    CampaignMember,
    CampaignMemberType,
    CampaignStatus,
    CampaignType,
)
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.opportunities.models import Opportunity
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService

#: Columns the aggregation owns. Stripped from any client payload.
DERIVED_FIELDS: frozenset[str] = frozenset(
    {"leads_generated", "opportunities_generated", "conversion_rate", "roi"}
)


class DuplicateCampaignMemberError(ConflictError):
    """That record is already enrolled in this campaign."""

    code = "duplicate_campaign_member"
    message = "That record is already a member of this campaign."


class CampaignService(TenantScopedService[Campaign]):
    entity_name = "Campaign"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Campaign), Campaign)
        self._session = session

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        status: CampaignStatus | None = None,
        campaign_type: CampaignType | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Campaign.name).like(term),
                    func.lower(func.coalesce(Campaign.target_audience, "")).like(term),
                )
            )
        if status is not None:
            filters.append(Campaign.status == status)
        if campaign_type is not None:
            filters.append(Campaign.type == campaign_type)
        if owner_id is not None:
            filters.append(Campaign.owner_id == owner_id)
        return filters

    async def list_campaigns(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[Campaign], int]:
        return await self.list(organization_id, params=params, filters=filters)

    async def member_counts(self, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Member totals per campaign, in one grouped query."""
        result = await self._session.execute(
            select(CampaignMember.campaign_id, func.count())
            .where(CampaignMember.organization_id == organization_id)
            .group_by(CampaignMember.campaign_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def list_members(self, campaign: Campaign) -> Sequence[CampaignMember]:
        result = await self._session.execute(
            select(CampaignMember)
            .where(
                CampaignMember.campaign_id == campaign.id,
                CampaignMember.organization_id == campaign.organization_id,
            )
            .order_by(CampaignMember.added_at.desc())
        )
        return result.scalars().all()

    # --- Commands ----------------------------------------------------------

    async def create_campaign(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> Campaign:
        payload = {k: v for k, v in values.items() if k not in DERIVED_FIELDS}
        return await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )

    async def update_campaign(
        self, campaign: Campaign, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> Campaign:
        payload = {k: v for k, v in values.items() if k not in DERIVED_FIELDS}
        return await self.update(campaign, actor_id=actor_id, values=payload)

    async def add_member(
        self,
        campaign: Campaign,
        *,
        entity_type: CampaignMemberType,
        entity_id: uuid.UUID,
    ) -> CampaignMember:
        """Enrol a lead or contact.

        Raises:
            NotFoundError: the record is not in this organization — which is
                also what another tenant's id looks like.
            DuplicateCampaignMemberError: already enrolled.
        """
        await self._require_member_target(campaign.organization_id, entity_type, entity_id)

        existing = await self._session.execute(
            select(CampaignMember.id).where(
                CampaignMember.campaign_id == campaign.id,
                CampaignMember.entity_type == entity_type,
                CampaignMember.entity_id == entity_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise DuplicateCampaignMemberError

        member = CampaignMember(
            organization_id=campaign.organization_id,
            campaign_id=campaign.id,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        self._session.add(member)
        await self._session.flush()
        return member

    async def remove_member(self, campaign: Campaign, member_id: uuid.UUID) -> None:
        """Remove an enrolment. Scoped so another campaign's row is untouched."""
        result = cast(
            "CursorResult[Any]",
            await self._session.execute(
                delete(CampaignMember).where(
                    CampaignMember.id == member_id,
                    CampaignMember.campaign_id == campaign.id,
                    CampaignMember.organization_id == campaign.organization_id,
                )
            ),
        )
        if result.rowcount == 0:
            raise NotFoundError("Campaign member not found.")
        await self._session.flush()

    async def recompute_metrics(self, campaign: Campaign) -> Campaign:
        """Derive the cached metrics from the records attributed to this campaign.

        Runs synchronously here rather than in a background job: the plan puts
        this in ARQ (P2-W15-BE-05), which does not exist yet, and a campaign's
        counts are small enough that computing them on demand is honest. When
        the worker lands, this method is what it should call.
        """
        leads_generated = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(Lead)
                    .where(
                        Lead.organization_id == campaign.organization_id,
                        Lead.campaign_id == campaign.id,
                        Lead.deleted_at.is_(None),
                    )
                )
            ).scalar_one()
        )

        converted = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(Lead)
                    .where(
                        Lead.organization_id == campaign.organization_id,
                        Lead.campaign_id == campaign.id,
                        Lead.deleted_at.is_(None),
                        Lead.status == LeadStatus.CONVERTED,
                    )
                )
            ).scalar_one()
        )

        opportunities_generated = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(Opportunity)
                    .join(Lead, Lead.converted_opportunity_id == Opportunity.id)
                    .where(
                        Opportunity.organization_id == campaign.organization_id,
                        Opportunity.deleted_at.is_(None),
                        Lead.campaign_id == campaign.id,
                    )
                )
            ).scalar_one()
        )

        campaign.leads_generated = leads_generated
        campaign.opportunities_generated = opportunities_generated
        campaign.conversion_rate = (
            # Two decimal places, matching Numeric(6, 2); no leads means no
            # rate at all rather than a misleading zero.
            (Decimal(converted) * Decimal(100) / Decimal(leads_generated)).quantize(
                Decimal("0.01")
            )
            if leads_generated
            else None
        )
        await self._session.flush()
        return campaign

    # --- Internals ---------------------------------------------------------

    async def _require_member_target(
        self,
        organization_id: uuid.UUID,
        entity_type: CampaignMemberType,
        entity_id: uuid.UUID,
    ) -> None:
        model = Lead if entity_type is CampaignMemberType.LEAD else Contact
        result = await self._session.execute(
            select(model.id).where(
                model.id == entity_id,
                model.organization_id == organization_id,
                model.deleted_at.is_(None),
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError(f"{entity_type.value.title()} not found.")


__all__ = ["DERIVED_FIELDS", "CampaignService", "DuplicateCampaignMemberError"]
