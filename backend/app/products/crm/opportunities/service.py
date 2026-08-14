"""Opportunity business rules: stage movement, win/loss and pipeline setup.

The rules enforced here:

* a stage must belong to the caller's organization — moving a deal onto another
  tenant's stage is rejected as "not found";
* a closed deal is immutable until explicitly reopened, so won/lost figures
  cannot drift silently;
* closing as lost requires a reason, because loss analysis is worthless
  without one;
* every stage change appends to ``opportunity_stage_history``.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.products.crm.opportunities.models import (
    Opportunity,
    OpportunityStageHistory,
    Pipeline,
    PipelineStage,
)
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService

logger = structlog.get_logger(__name__)

#: Seeded for a new organization; mirrors the stage list the frontend shows.
DEFAULT_PIPELINE_NAME = "Standard Sales Pipeline"
DEFAULT_STAGES: tuple[tuple[str, int, int, bool, bool], ...] = (
    # (name, sort_order, default_probability, is_won, is_lost)
    ("Qualification", 1, 10, False, False),
    ("Discovery", 2, 25, False, False),
    ("Proposal", 3, 50, False, False),
    ("Negotiation", 4, 75, False, False),
    ("Contract Review", 5, 90, False, False),
    ("Closed Won", 6, 100, True, False),
    ("Closed Lost", 7, 0, False, True),
)


class OpportunityClosedError(ConflictError):
    """The deal is already won or lost."""

    code = "opportunity_closed"
    message = "This opportunity is closed. Reopen it before making changes."


class LossReasonRequiredError(ValidationFailedError):
    """Closing as lost without saying why."""

    code = "loss_reason_required"
    message = "A reason is required when marking an opportunity as lost."


class OpportunityService(TenantScopedService[Opportunity]):
    entity_name = "Opportunity"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Opportunity), Opportunity)
        self._session = session

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        stage_id: uuid.UUID | None = None,
        account_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
        is_open: bool | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if search:
            filters.append(func.lower(Opportunity.name).like(f"%{search.strip().lower()}%"))
        if stage_id is not None:
            filters.append(Opportunity.stage_id == stage_id)
        if account_id is not None:
            filters.append(Opportunity.account_id == account_id)
        if owner_id is not None:
            filters.append(Opportunity.owner_id == owner_id)
        if is_open is True:
            filters.append(Opportunity.won_at.is_(None))
            filters.append(Opportunity.lost_at.is_(None))
        elif is_open is False:
            filters.append(
                Opportunity.won_at.is_not(None) | Opportunity.lost_at.is_not(None)
            )
        return filters

    async def list_opportunities(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[Sequence[Opportunity], int]:
        return await self.list(organization_id, params=params, filters=filters)

    # --- Stages ------------------------------------------------------------

    async def get_stage(
        self, stage_id: uuid.UUID, organization_id: uuid.UUID
    ) -> PipelineStage:
        """Fetch a stage inside the organization, or 404.

        Scoping this lookup is what stops a caller moving their deal onto
        another tenant's stage by supplying its id.
        """
        result = await self._session.execute(
            select(PipelineStage).where(
                PipelineStage.id == stage_id,
                PipelineStage.organization_id == organization_id,
                PipelineStage.deleted_at.is_(None),
            )
        )
        stage = result.scalar_one_or_none()
        if stage is None:
            raise NotFoundError("Pipeline stage not found.")
        return stage

    async def list_stages(self, organization_id: uuid.UUID) -> Sequence[PipelineStage]:
        result = await self._session.execute(
            select(PipelineStage)
            .where(
                PipelineStage.organization_id == organization_id,
                PipelineStage.deleted_at.is_(None),
            )
            .order_by(PipelineStage.sort_order)
        )
        return result.scalars().all()

    async def ensure_default_pipeline(
        self, organization_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> Pipeline:
        """Create the standard pipeline and stages if none exist yet.

        Idempotent: an organization that already has a pipeline gets it back
        unchanged, so this is safe to call during provisioning and from tests.
        """
        existing = await self._session.execute(
            select(Pipeline).where(
                Pipeline.organization_id == organization_id, Pipeline.deleted_at.is_(None)
            )
        )
        pipeline = existing.scalars().first()
        if pipeline is not None:
            return pipeline

        pipeline = Pipeline(
            organization_id=organization_id,
            name=DEFAULT_PIPELINE_NAME,
            is_default=True,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(pipeline)
        await self._session.flush()

        for name, order, probability, is_won, is_lost in DEFAULT_STAGES:
            self._session.add(
                PipelineStage(
                    organization_id=organization_id,
                    pipeline_id=pipeline.id,
                    name=name,
                    sort_order=order,
                    default_probability=probability,
                    is_won=is_won,
                    is_lost=is_lost,
                    created_by_id=actor_id,
                    updated_by_id=actor_id,
                )
            )
        await self._session.flush()
        logger.info("default_pipeline_created", organization_id=str(organization_id))
        return pipeline

    # --- Lifecycle ---------------------------------------------------------

    async def change_stage(
        self,
        opportunity: Opportunity,
        *,
        stage_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        note: str | None = None,
        loss_reason: str | None = None,
        win_reason: str | None = None,
    ) -> Opportunity:
        """Move a deal to another stage, recording the movement.

        Reaching a stage flagged ``is_won``/``is_lost`` closes the deal and
        stamps the corresponding timestamp; every move is appended to the stage
        history regardless.

        Raises:
            OpportunityClosedError: the deal is already closed.
            LossReasonRequiredError: moving to a lost stage without a reason.
            NotFoundError: the stage is not in this organization.
        """
        if opportunity.is_closed:
            raise OpportunityClosedError

        stage = await self.get_stage(stage_id, opportunity.organization_id)
        if stage.id == opportunity.stage_id:
            return opportunity

        if stage.is_lost and not (loss_reason or "").strip():
            raise LossReasonRequiredError

        previous_stage_id = opportunity.stage_id
        now = dt.datetime.now(dt.UTC)

        opportunity.stage_id = stage.id
        opportunity.updated_by_id = actor_id
        if stage.default_probability is not None:
            opportunity.win_probability = stage.default_probability
        if stage.is_won:
            opportunity.won_at = now
            opportunity.win_reason = win_reason
        elif stage.is_lost:
            opportunity.lost_at = now
            opportunity.loss_reason = loss_reason

        self._session.add(
            OpportunityStageHistory(
                organization_id=opportunity.organization_id,
                opportunity_id=opportunity.id,
                from_stage_id=previous_stage_id,
                to_stage_id=stage.id,
                changed_by_id=actor_id,
                changed_at=now,
                note=note,
            )
        )
        await self._session.flush()

        logger.info(
            "opportunity_stage_changed",
            opportunity_id=str(opportunity.id),
            organization_id=str(opportunity.organization_id),
            to_stage=stage.name,
            closed=stage.is_won or stage.is_lost,
        )
        return opportunity

    async def reopen(
        self, opportunity: Opportunity, *, stage_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> Opportunity:
        """Return a closed deal to an open stage.

        Raises:
            ValidationFailedError: the deal is not closed, or the target stage
                is itself terminal.
        """
        if not opportunity.is_closed:
            raise ValidationFailedError("This opportunity is not closed.")

        stage = await self.get_stage(stage_id, opportunity.organization_id)
        if stage.is_closed:
            raise ValidationFailedError("Reopen requires an open stage.")

        previous_stage_id = opportunity.stage_id
        now = dt.datetime.now(dt.UTC)

        opportunity.won_at = None
        opportunity.lost_at = None
        opportunity.loss_reason = None
        opportunity.win_reason = None
        opportunity.stage_id = stage.id
        opportunity.win_probability = stage.default_probability
        opportunity.updated_by_id = actor_id

        self._session.add(
            OpportunityStageHistory(
                organization_id=opportunity.organization_id,
                opportunity_id=opportunity.id,
                from_stage_id=previous_stage_id,
                to_stage_id=stage.id,
                changed_by_id=actor_id,
                changed_at=now,
                note="Reopened",
            )
        )
        await self._session.flush()
        logger.info("opportunity_reopened", opportunity_id=str(opportunity.id))
        return opportunity

    async def update_open(
        self,
        opportunity: Opportunity,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, object],
    ) -> Opportunity:
        """Patch a deal, refusing edits to a closed one.

        Raises:
            OpportunityClosedError: the deal is won or lost.
        """
        if opportunity.is_closed:
            raise OpportunityClosedError
        # ``stage_id`` has its own workflow; ignore it here so a PATCH cannot
        # bypass history recording and the win/loss rules.
        values.pop("stage_id", None)
        return await self.update(opportunity, actor_id=actor_id, values=values)

    async def stage_history(
        self, opportunity: Opportunity
    ) -> Sequence[OpportunityStageHistory]:
        result = await self._session.execute(
            select(OpportunityStageHistory)
            .where(
                OpportunityStageHistory.opportunity_id == opportunity.id,
                OpportunityStageHistory.organization_id == opportunity.organization_id,
            )
            .order_by(OpportunityStageHistory.changed_at.desc())
        )
        return result.scalars().all()


__all__ = [
    "DEFAULT_PIPELINE_NAME",
    "DEFAULT_STAGES",
    "LossReasonRequiredError",
    "OpportunityClosedError",
    "OpportunityService",
]
