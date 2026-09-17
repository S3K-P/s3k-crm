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
from typing import Any

import structlog
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import provisioning_scope
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationFailedError
from app.platform.audit.service import Action as AuditAction
from app.platform.auth.dependencies import Principal
from app.products.crm.blueprints.enforcement import BlueprintGuard
from app.products.crm.blueprints.models import BlueprintField
from app.products.crm.common import CrmEntityType
from app.products.crm.opportunities.models import (
    Opportunity,
    OpportunityStageHistory,
    Pipeline,
    PipelineStage,
)
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.record_notifications import OPPORTUNITY_WON, notify_record_event
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.schemas import BulkOperationFailure, BulkOperationResult
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.shared.timeline import (
    TimelineEntry,
    activity_entries,
    deal_created_entries,
    email_entries,
    merge_timeline_entries,
    note_entries,
    stage_changed_entries,
    task_entries,
)
from app.products.crm.shared.visibility import RecordVisibility

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
    #: Opts this entity into tenant-defined fields (Phase E). Declaring it
    #: is the whole wiring: the base class validates and merges
    #: ``custom_fields`` on every create and update from here on.
    crm_entity_type = CrmEntityType.OPPORTUNITY

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
        primary_contact_id: uuid.UUID | None = None,
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
        if primary_contact_id is not None:
            filters.append(Opportunity.primary_contact_id == primary_contact_id)
        if owner_id is not None:
            filters.append(Opportunity.owner_id == owner_id)
        if is_open is True:
            filters.append(Opportunity.won_at.is_(None))
            filters.append(Opportunity.lost_at.is_(None))
        elif is_open is False:
            filters.append(Opportunity.won_at.is_not(None) | Opportunity.lost_at.is_not(None))
        return filters

    async def list_opportunities(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
        visibility: RecordVisibility | None = None,
        sort_column: ColumnElement[Any] | None = None,
    ) -> tuple[Sequence[Opportunity], int]:
        return await self.list(
            organization_id,
            params=params,
            filters=filters,
            visibility=visibility,
            sort_column=sort_column,
        )

    # --- Stages ------------------------------------------------------------

    async def get_stage(self, stage_id: uuid.UUID, organization_id: uuid.UUID) -> PipelineStage:
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

        Runs inside :func:`provisioning_scope` because the first call happens
        in the transaction that creates the organization, before that
        organization can have a request context of its own -- and ``pipelines``
        and ``pipeline_stages`` are both RLS-FORCEd, so the INSERT is refused
        under any role that does not bypass policies. Called later from an
        ordinary request the scope is a no-op: the setting already names this
        organization, and it is restored either way.
        """
        async with provisioning_scope(self._session, organization_id):
            existing = await self._session.execute(
                select(Pipeline).where(
                    Pipeline.organization_id == organization_id,
                    Pipeline.deleted_at.is_(None),
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
        principal: Principal | None = None,
    ) -> Opportunity:
        """Move a deal to another stage, recording the movement.

        Reaching a stage flagged ``is_won``/``is_lost`` closes the deal and
        stamps the corresponding timestamp; every move is appended to the stage
        history regardless.

        ``principal`` is optional so an internal caller with no request behind
        it can still move a deal. It is used only for a blueprint transition's
        ``required_permission``; the field and note requirements hold however
        the change arrived.

        Raises:
            OpportunityClosedError: the deal is already closed.
            LossReasonRequiredError: moving to a lost stage without a reason.
            NotFoundError: the stage is not in this organization.
            BlueprintTransitionBlockedError: the move is legal but the
                organization's own process refuses it, or its requirements are
                not yet met.
        """
        if opportunity.is_closed:
            raise OpportunityClosedError

        stage = await self.get_stage(stage_id, opportunity.organization_id)
        if stage.id == opportunity.stage_id:
            return opportunity

        if stage.is_lost and not (loss_reason or "").strip():
            raise LossReasonRequiredError

        # For the workflow event's ``STAGE_CHANGED`` trigger, which matches by
        # stage *name* (human-configured) rather than id — see
        # ``workflows.conditions.rule_matches_trigger``. Stages have no delete
        # endpoint today, so this should always resolve; caught defensively
        # rather than letting a data-integrity edge case block a stage move.
        try:
            previous_stage_name: str | None = (
                await self.get_stage(opportunity.stage_id, opportunity.organization_id)
            ).name
        except NotFoundError:
            previous_stage_name = None

        previous_stage_id = opportunity.stage_id

        # The tenant's own process, applied *after* the built-in rules above
        # (Phase G). The order is the guarantee: a blueprint narrows what the
        # product allows and never widens it, so it cannot configure away the
        # closed-deal check or the loss-reason requirement.
        #
        # `note` is what a `require_note` transition is satisfied by, and it is
        # the same note already recorded in the stage history — so a process
        # demanding an explanation gets one that is actually kept.
        await BlueprintGuard(self._session).check(
            organization_id=opportunity.organization_id,
            field=BlueprintField.OPPORTUNITY_STAGE,
            record=opportunity,
            from_state=str(previous_stage_id),
            to_state=str(stage.id),
            principal=principal,
            note=note or loss_reason or win_reason,
        )

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

        # ``opportunity_stage_history`` already records the movement for the
        # deal's own timeline. This is the parallel entry in the *security*
        # trail, where it sits beside who made the change, from where, and
        # under which request — and where it cannot be edited afterwards.
        await self.audit.record(
            organization_id=opportunity.organization_id,
            action=AuditAction.OPPORTUNITY_STAGE_CHANGED,
            module=self.audit_module,
            actor_id=actor_id,
            entity_type=self.audit_entity_type,
            entity_id=opportunity.id,
            entity_label=self.audit_label(opportunity),
            details={
                "from_stage_id": previous_stage_id,
                "to_stage_id": stage.id,
                "to_stage": stage.name,
                "won": stage.is_won,
                "lost": stage.is_lost,
                "loss_reason": loss_reason,
                "win_reason": win_reason,
            },
        )
        if stage.is_won:
            # P4-W27-BE-03: the owner hears the deal closed, unless they closed it.
            value = (
                f" worth {opportunity.currency} {opportunity.deal_value:,.2f}"
                if opportunity.deal_value is not None
                else ""
            )
            await notify_record_event(
                self._session,
                organization_id=opportunity.organization_id,
                recipient_id=opportunity.owner_id,
                actor_id=actor_id,
                kind=OPPORTUNITY_WON,
                title=f"Opportunity won: {opportunity.name}",
                message=f'Your opportunity "{opportunity.name}"{value} has been won.',
                entity_type="opportunity",
                entity_id=opportunity.id,
                record_path=f"/opportunities/{opportunity.id}",
            )
        self._enqueue_record_event(
            opportunity,
            organization_id=opportunity.organization_id,
            trigger="stage_changed",
            changed_fields={
                "stage_id": {"before": str(previous_stage_id), "after": str(stage.id)},
                "stage_name": {"before": previous_stage_name, "after": stage.name},
            },
        )
        return opportunity

    async def bulk_change_stage(
        self,
        ids: Sequence[uuid.UUID],
        organization_id: uuid.UUID,
        *,
        stage_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        note: str | None,
        loss_reason: str | None,
        win_reason: str | None,
        principal: Principal | None,
        visibility: RecordVisibility | None = None,
    ) -> BulkOperationResult:
        """Move many deals to the same stage at once (Checkpoint 4).

        Each id runs through the identical :meth:`change_stage` a single drag
        on the Kanban board calls — closed-deal refusal, the missing-reason
        check, blueprint validation, stage history — independently. A deal
        already closed, or one the organization's blueprint refuses this move
        for, is reported as a per-id failure; the rest of the batch is
        unaffected.
        """
        succeeded: list[uuid.UUID] = []
        failed: list[BulkOperationFailure] = []
        for opportunity_id in ids:
            try:
                opportunity = await self.get_or_404(
                    opportunity_id, organization_id, visibility=visibility
                )
                await self.change_stage(
                    opportunity,
                    stage_id=stage_id,
                    actor_id=actor_id,
                    note=note,
                    loss_reason=loss_reason,
                    win_reason=win_reason,
                    principal=principal,
                )
                succeeded.append(opportunity_id)
            except AppError as exc:
                failed.append(BulkOperationFailure(id=opportunity_id, reason=exc.message))
        return BulkOperationResult(succeeded=succeeded, failed=failed)

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

        # Reopening erases a won/lost outcome and the reason recorded with it,
        # which is precisely the kind of change to closed-period numbers that
        # an audit trail exists to make visible.
        await self.audit.record(
            organization_id=opportunity.organization_id,
            action=AuditAction.OPPORTUNITY_REOPENED,
            module=self.audit_module,
            actor_id=actor_id,
            entity_type=self.audit_entity_type,
            entity_id=opportunity.id,
            entity_label=self.audit_label(opportunity),
            details={"from_stage_id": previous_stage_id, "to_stage_id": stage.id},
        )
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

    async def _bulk_update_one(
        self, entity: Opportunity, *, actor_id: uuid.UUID | None, values: dict[str, object]
    ) -> Opportunity:
        """Route bulk updates (Checkpoint 4) through the same closed-deal rule."""
        return await self.update_open(entity, actor_id=actor_id, values=values)

    async def timeline(
        self, opportunity: Opportunity, principal: Principal, *, limit: int = 50
    ) -> list[TimelineEntry]:
        """Every event this caller may see against this deal, newest first.

        Its own creation and its own stage moves are included alongside
        activities, tasks, sent email and notes — the same merged shape
        Account and Contact expose — by reusing ``deal_created_entries`` and
        ``stage_changed_entries`` with a filter that matches only this
        opportunity, rather than a hand-written duplicate of either query.
        """
        organization_id = opportunity.organization_id
        # This is the opportunity's own record: the caller already holds
        # ``opportunities.VIEW`` on it (the route depends on it), so the
        # unrestricted visibility is correct here and is not widened for any
        # other opportunity — the filter matches exactly one id.
        unrestricted = RecordVisibility.unrestricted()
        tasks_visibility = RecordVisibility.for_module(principal, "tasks")
        self_filter = Opportunity.id == opportunity.id

        activities = await activity_entries(
            self._session,
            organization_id=organization_id,
            entity_type=CrmEntityType.OPPORTUNITY,
            entity_id=opportunity.id,
        )
        created = await deal_created_entries(
            self._session,
            organization_id=organization_id,
            opportunity_filter=self_filter,
            visibility=unrestricted,
        )
        stage_changes = await stage_changed_entries(
            self._session,
            organization_id=organization_id,
            opportunity_filter=self_filter,
            visibility=unrestricted,
        )
        tasks = await task_entries(
            self._session,
            organization_id=organization_id,
            entity_type=CrmEntityType.OPPORTUNITY,
            entity_id=opportunity.id,
            visibility=tasks_visibility,
        )
        emails = await email_entries(
            self._session,
            organization_id=organization_id,
            entity_type=CrmEntityType.OPPORTUNITY,
            entity_id=opportunity.id,
            viewer_id=principal.user_id,
        )
        notes = await note_entries(
            self._session,
            organization_id=organization_id,
            entity_type=CrmEntityType.OPPORTUNITY,
            entity_id=opportunity.id,
            viewer_id=principal.user_id,
        )
        return merge_timeline_entries(
            activities, created, stage_changes, tasks, emails, notes, limit=limit
        )

    async def stage_history(self, opportunity: Opportunity) -> Sequence[OpportunityStageHistory]:
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
