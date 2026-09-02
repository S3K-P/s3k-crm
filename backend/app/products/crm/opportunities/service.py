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
from typing import Any, NamedTuple, cast

import structlog
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.platform.audit.service import Action as AuditAction
from app.products.crm.common import CrmEntityType
from app.products.crm.opportunities.gating import check_stage_entry
from app.products.crm.opportunities.models import (
    Opportunity,
    OpportunityStageHistory,
    Pipeline,
    PipelineStage,
)
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import Task, TaskStatus

logger = structlog.get_logger(__name__)

#: Seeded for a new organization; mirrors the stage list the frontend shows.
DEFAULT_PIPELINE_NAME = "Standard Sales Pipeline"


class _DefaultStage(NamedTuple):
    """One seeded stage. A tuple was fine at five fields and is not at seven."""

    name: str
    sort_order: int
    default_probability: int
    is_won: bool
    is_lost: bool
    #: Follow-up created on entry, or ``None`` for no automation. Seeded on the
    #: open stages where a deal genuinely goes quiet; the closed ones need no
    #: chasing, and Qualification is where the deal already has the rep's
    #: attention.
    follow_up_task_title: str | None = None
    follow_up_task_days: int | None = None


DEFAULT_STAGES: tuple[_DefaultStage, ...] = (
    _DefaultStage("Qualification", 1, 10, False, False),
    _DefaultStage("Discovery", 2, 25, False, False, "Send proposal", 5),
    _DefaultStage("Proposal", 3, 50, False, False, "Follow up on proposal", 3),
    _DefaultStage("Negotiation", 4, 75, False, False, "Confirm terms", 2),
    _DefaultStage("Contract Review", 5, 90, False, False, "Chase signature", 3),
    _DefaultStage("Closed Won", 6, 100, True, False),
    _DefaultStage("Closed Lost", 7, 0, False, True),
)


class OpportunityClosedError(ConflictError):
    """The deal is already won or lost."""

    code = "opportunity_closed"
    message = "This opportunity is closed. Reopen it before making changes."


class LossReasonRequiredError(ValidationFailedError):
    """Closing as lost without saying why."""

    code = "loss_reason_required"
    message = "A reason is required when marking an opportunity as lost."


class StageRequirementsUnmetError(ValidationFailedError):
    """The deal lacks something the target stage requires.

    The Blueprint idea, sized for S3K (analysis §5.6): gate the change *before*
    it happens rather than reacting to it afterwards. ``details`` names the
    missing fields so the UI can highlight them instead of showing a sentence.
    """

    code = "stage_requirements_unmet"


class CloseDateRequiredError(ValidationFailedError):
    """Clearing the close date of a live deal."""

    code = "close_date_required"
    message = "An opportunity must keep an expected close date."


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
        visibility: RecordVisibility | None = None,
    ) -> tuple[Sequence[Opportunity], int]:
        return await self.list(
            organization_id, params=params, filters=filters, visibility=visibility
        )

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

        for default in DEFAULT_STAGES:
            self._session.add(
                PipelineStage(
                    organization_id=organization_id,
                    pipeline_id=pipeline.id,
                    name=default.name,
                    sort_order=default.sort_order,
                    default_probability=default.default_probability,
                    is_won=default.is_won,
                    is_lost=default.is_lost,
                    follow_up_task_title=default.follow_up_task_title,
                    follow_up_task_days=default.follow_up_task_days,
                    created_by_id=actor_id,
                    updated_by_id=actor_id,
                )
            )
        await self._session.flush()
        logger.info("default_pipeline_created", organization_id=str(organization_id))
        return pipeline

    # --- Creation ----------------------------------------------------------

    async def create_opportunity(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
        stage: PipelineStage | None = None,
    ) -> Opportunity:
        """Create a deal with the derivations its stage implies.

        Three things happen here that generic ``create`` cannot do, and that
        previously only happened when a deal *moved* between stages — so a deal
        created directly into a stage was inconsistent with an identical deal
        that arrived there by transition:

        * **Probability comes from the stage.** ``PipelineStage`` already
          carries ``default_probability``; making the caller retype it invites
          a number that disagrees with every other deal in that column. An
          explicitly supplied value still wins, because a rep who knows this
          particular deal is a long shot is better informed than the default.
        * **A terminal opening stage closes the deal.** Creating straight into
          "Closed Won" (importing historical deals does exactly this) must
          stamp ``won_at``/``lost_at``, or the row reads as open forever and
          inflates the pipeline.
        * **The opening stage is recorded in history.** Creation previously
          wrote no ``opportunity_stage_history`` row at all, so a deal's first
          stage had no entry and time-in-first-stage was uncomputable.

        ``stage`` may be passed by a caller that has already fetched and
        organization-checked it, to avoid a second round trip.
        """
        payload = dict(values)
        resolved = (
            stage
            if stage is not None
            else await self.get_stage(cast("uuid.UUID", payload.get("stage_id")), organization_id)
        )
        # Take the stage from the resolved row rather than from the payload, so
        # the id written can never be one that was not organization-checked.
        payload["stage_id"] = resolved.id

        if payload.get("win_probability") is None and resolved.default_probability is not None:
            payload["win_probability"] = resolved.default_probability

        now = dt.datetime.now(dt.UTC)
        if resolved.is_lost:
            if not str(payload.get("loss_reason") or "").strip():
                raise LossReasonRequiredError
            payload["lost_at"] = now
        elif resolved.is_won:
            payload["won_at"] = now

        opportunity = await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )

        self._session.add(
            OpportunityStageHistory(
                organization_id=organization_id,
                opportunity_id=opportunity.id,
                from_stage_id=None,
                to_stage_id=resolved.id,
                changed_by_id=actor_id,
                changed_at=now,
                note="Created",
            )
        )
        await self._session.flush()

        await self._create_stage_follow_up(opportunity, resolved, actor_id=actor_id)
        return opportunity

    # --- Stage automation --------------------------------------------------

    async def _create_stage_follow_up(
        self,
        opportunity: Opportunity,
        stage: PipelineStage,
        *,
        actor_id: uuid.UUID | None,
    ) -> Task | None:
        """Create the stage's configured follow-up task, if it has one.

        Declarative rather than a workflow engine: the stage row names a title
        and a due-date offset, and entering the stage creates that task. There
        is no condition language and no action registry to learn — the analysis
        (§4.4) rules a Zoho-style designer out of scope, and a nullable column
        expresses "chase this in three days" exactly.

        **Duplicate protection.** A deal can revisit a stage — a rep moves it
        forward, discovers a problem, moves it back, moves it forward again —
        and each entry would otherwise mint another identical task. An *open*
        task with the same title on the same opportunity means the previous one
        is still outstanding, so a second adds nothing but noise. A completed
        one does not block a new task, because the follow-up genuinely is due
        again.

        The task belongs to the deal's owner rather than to whoever moved the
        stage: a manager advancing a rep's deal is not volunteering to do the
        chasing. ``organization_id`` comes from the opportunity, so the task
        cannot land in another tenant.
        """
        title = (stage.follow_up_task_title or "").strip()
        if not title:
            return None

        already_open = await self._session.execute(
            select(Task.id)
            .where(
                Task.organization_id == opportunity.organization_id,
                Task.deleted_at.is_(None),
                Task.related_entity_type == CrmEntityType.OPPORTUNITY,
                Task.related_entity_id == opportunity.id,
                Task.title == title,
                Task.status.notin_((TaskStatus.COMPLETED, TaskStatus.CANCELLED)),
            )
            .limit(1)
        )
        if already_open.scalar_one_or_none() is not None:
            return None

        due_date: dt.datetime | None = None
        if stage.follow_up_task_days is not None:
            due_date = dt.datetime.now(dt.UTC) + dt.timedelta(days=stage.follow_up_task_days)

        task = Task(
            organization_id=opportunity.organization_id,
            title=title,
            description=f"Automatic follow-up for stage “{stage.name}”.",
            owner_id=opportunity.owner_id,
            assigned_to_id=opportunity.owner_id,
            due_date=due_date,
            related_entity_type=CrmEntityType.OPPORTUNITY,
            related_entity_id=opportunity.id,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(task)
        await self._session.flush()
        logger.info(
            "stage_follow_up_task_created",
            opportunity_id=str(opportunity.id),
            stage=stage.name,
            task_id=str(task.id),
        )
        return task

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

        # Declarative gating: a deal must carry what the stage needs before it
        # may enter. Checked here rather than in the router so every path — the
        # API, a bulk stage move, a future automation — is gated by the same
        # rule.
        requirement = check_stage_entry(opportunity, stage)
        if not requirement.is_satisfied:
            raise StageRequirementsUnmetError(
                requirement.message(stage.name),
                details={"stage": stage.name, "missing": list(requirement.fields)},
            )

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

        await self._create_stage_follow_up(opportunity, stage, actor_id=actor_id)

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
            CloseDateRequiredError: the patch clears the close date.
        """
        if opportunity.is_closed:
            raise OpportunityClosedError
        # ``stage_id`` has its own workflow; ignore it here so a PATCH cannot
        # bypass history recording and the win/loss rules.
        values.pop("stage_id", None)
        # The column is NOT NULL, so an explicit ``"expected_close_date": null``
        # would otherwise surface as an IntegrityError — a 500 for what is a
        # perfectly ordinary bad request. ``exclude_unset`` means the key is
        # only present when the client actually sent it, so this cannot fire
        # on a patch that simply leaves the date alone.
        if "expected_close_date" in values and values["expected_close_date"] is None:
            raise CloseDateRequiredError
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
    "CloseDateRequiredError",
    "LossReasonRequiredError",
    "OpportunityClosedError",
    "OpportunityService",
    "StageRequirementsUnmetError",
]
