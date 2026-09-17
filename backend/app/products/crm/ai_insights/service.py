"""Checkpoint 7 business rules — the module's public interface.

Every AI-generated feature here follows one shape:

1. Resolve the CRM record(s) the caller asked about through that record's own
   service and its own ``get_or_404(..., visibility=...)`` — so an id from
   another tenant, or one the caller may not see, is a 404 before any AI
   context is even built (§17).
2. Build permission-filtered CRM context (``context.py``).
3. Call the gateway for a structured answer (``structured.py``), validated
   against a Pydantic schema (§20) before this module ever looks at it.
4. Persist the result as an :class:`AiGeneration` row — the cache Step 15
   asks for (a page load reads the latest row; only "Generate"/"Refresh"
   calls the model) and the history Step 16 asks for.

Mutating features (meeting-to-CRM, and any action a user later triggers from
a recommendation) never write directly: they call the exact same entity
service a human editing the record would — ``TaskService.create_task``,
``NoteService.create_note``, ``OpportunityService.update_open`` — so
Blueprint rules, permissions and validation apply identically (§5, §9, §17).

Natural-language queries never reach SQL through this module at all: a
question is translated to a :class:`CustomReportDefinition`, the *existing*
structured shape the report builder already validates and executes
(``reports.custom.CustomReportEngine``) — this module never executes a query
itself (§10, §20).
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.platform.ai.service import AiGatewayService
from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.models import Account
from app.products.crm.accounts.service import AccountService
from app.products.crm.activities.models import Activity
from app.products.crm.ai_insights import insights as insights_queries
from app.products.crm.ai_insights import (
    nba_collect,
    nba_predictive,
    nba_rules,
    prioritization,
)
from app.products.crm.ai_insights.context import (
    CrmContext,
    build_account_context,
    build_lead_context,
    build_opportunity_context,
)
from app.products.crm.ai_insights.models import (
    AiFeature,
    AiFeedbackRating,
    AiGeneration,
    AiGenerationStatus,
    NbaActionLog,
    NbaActionOutcome,
    NbaRule,
)
from app.products.crm.ai_insights.nba_catalog import (
    ACTIONS,
    ActionCategory,
    CopilotKind,
    RecordKind,
)
from app.products.crm.ai_insights.nba_signals import SIGNALS
from app.products.crm.ai_insights.prompts import (
    ACCOUNT_INTELLIGENCE_ROLE,
    ACCOUNT_INTELLIGENCE_TASK,
    ACCOUNT_SUMMARY_ROLE,
    ACCOUNT_SUMMARY_TASK,
    EMAIL_DRAFT_ROLE,
    LEAD_SUMMARY_TASK,
    MEETING_EXTRACTION_ROLE,
    MEETING_EXTRACTION_TASK,
    NBA_COPILOT_ROLE,
    NEXT_BEST_ACTION_ROLE,
    NEXT_BEST_ACTION_TASK,
    NL_QUERY_ROLE,
    OPPORTUNITY_SUMMARY_TASK,
    PRIORITY_EXPLANATION_ROLE,
    build_prompt,
    email_draft_task,
    nba_copilot_task,
    nl_query_task,
    priority_explanation_task,
)
from app.products.crm.ai_insights.repository import (
    AiGenerationRepository,
    NbaActionLogRepository,
    NbaRuleRepository,
)
from app.products.crm.ai_insights.schemas import (
    AccountIntelligenceOutput,
    AiGenerationResponse,
    CopilotCallScriptOutput,
    CopilotEmailOutput,
    CopilotMeetingOutput,
    CopilotMessageOutput,
    CopilotProposalOutput,
    EmailDraftOutput,
    EmailDraftRequest,
    InsightItem,
    InsightsDigest,
    MeetingActionItem,
    MeetingAppliedItem,
    MeetingExtractionOutput,
    NbaActionLogCreate,
    NbaActionLogResponse,
    NbaActionResponse,
    NbaBuiltinOverride,
    NbaCatalogAction,
    NbaCatalogResponse,
    NbaCatalogSignal,
    NbaCondition,
    NbaCopilotRequest,
    NbaRuleCreate,
    NbaRuleResponse,
    NbaRuleUpdate,
    NbaSignalEvidence,
    NextBestActionOutput,
    NlQueryTranslation,
    PriorityExplanationOutput,
    PriorityRecordFacts,
    PriorityScoreResponse,
    RecordSummaryOutput,
)
from app.products.crm.ai_insights.schemas import (
    PriorityReason as PriorityReasonSchema,
)
from app.products.crm.ai_insights.structured import run_structured
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.contacts.service import ContactService
from app.products.crm.layouts.evaluate import OPERATORS as CONDITION_OPERATORS
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.leads.service import LeadService
from app.products.crm.notes.models import NoteVisibility
from app.products.crm.notes.service import NoteService
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.opportunities.service import OpportunityClosedError, OpportunityService
from app.products.crm.reports.custom import CustomReportEngine
from app.products.crm.reports.fields import FIELDS, MODULE_FOR_ENTITY, ReportEntity
from app.products.crm.reports.schemas import ReportResult
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.shared.visibility import RecordVisibility
from app.products.crm.tasks.models import Task
from app.products.crm.tasks.service import CLOSED_STATUSES, TaskService

MAX_PRIORITY_CANDIDATES = 200


class AiInsightsService:
    """Checkpoint 7's AI features, built on the AI gateway and real CRM data."""

    def __init__(self, session: AsyncSession, *, gateway: AiGatewayService) -> None:
        self._session = session
        self._gateway = gateway
        self._generations = AiGenerationRepository(session)
        self._accounts = AccountService(session)
        self._opportunities = OpportunityService(session)
        self._leads = LeadService(session)
        self._contacts = ContactService(session)
        self._tasks = TaskService(session)
        self._notes = NoteService(session)
        self._nba_rule_rows = NbaRuleRepository(session)
        self._nba_rule_service = NbaRuleService(session)
        self._nba_logs = NbaActionLogRepository(session)

    # --- Record resolution ---------------------------------------------

    async def resolve_account(self, principal: Principal, account_id: uuid.UUID) -> Account:
        return await self._accounts.get_or_404(
            account_id,
            principal.organization_id,
            visibility=RecordVisibility.for_module(principal, "accounts"),
        )

    async def resolve_opportunity(
        self, principal: Principal, opportunity_id: uuid.UUID
    ) -> Opportunity:
        return await self._opportunities.get_or_404(
            opportunity_id,
            principal.organization_id,
            visibility=RecordVisibility.for_module(principal, "opportunities"),
        )

    async def resolve_lead(self, principal: Principal, lead_id: uuid.UUID) -> Lead:
        return await self._leads.get_or_404(
            lead_id,
            principal.organization_id,
            visibility=RecordVisibility.for_module(principal, "leads"),
        )

    async def resolve_contact(self, principal: Principal, contact_id: uuid.UUID) -> Contact:
        return await self._contacts.get_or_404(
            contact_id,
            principal.organization_id,
            visibility=RecordVisibility.for_module(principal, "contacts"),
        )

    # --- Generation history / cache --------------------------------------

    async def latest(
        self,
        principal: Principal,
        *,
        entity_type: CrmEntityType,
        entity_id: uuid.UUID,
        feature: AiFeature,
    ) -> AiGeneration | None:
        """The cached result a record's AI panel shows without calling the
        model (§15) — ``None`` means "never generated", not "empty".
        """
        return await self._generations.latest_for(
            principal.organization_id,
            entity_type=entity_type.value,
            entity_id=entity_id,
            feature=feature,
        )

    async def history(
        self, principal: Principal, *, entity_type: CrmEntityType, entity_id: uuid.UUID
    ) -> Sequence[AiGeneration]:
        return await self._generations.history_for(
            principal.organization_id, entity_type=entity_type.value, entity_id=entity_id
        )

    async def get_generation_or_404(
        self, principal: Principal, generation_id: uuid.UUID
    ) -> AiGeneration:
        generation = await self._generations.get(generation_id, principal.organization_id)
        if generation is None:
            raise NotFoundError("AI result not found.")
        return generation

    async def submit_feedback(
        self,
        principal: Principal,
        generation: AiGeneration,
        *,
        rating: AiFeedbackRating,
        comment: str | None,
    ) -> AiGeneration:
        generation.feedback_rating = rating
        generation.feedback_comment = comment
        generation.feedback_by_id = principal.user_id
        generation.feedback_at = dt.datetime.now(dt.UTC)
        await self._generations.flush()
        return generation

    # --- Core: run one structured feature call ---------------------------

    async def _generate(
        self,
        principal: Principal,
        *,
        feature: AiFeature,
        entity_type: CrmEntityType | None,
        entity_id: uuid.UUID | None,
        system: str,
        user_message: str,
        schema: type[Any],
        used_crm_context: bool,
    ) -> tuple[AiGeneration, Any]:
        parsed, result = await run_structured(
            self._gateway,
            schema,
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            feature=f"ai_insights.{feature.value.lower()}",
        )
        generation = await self._generations.add(
            AiGeneration(
                organization_id=principal.organization_id,
                feature=feature,
                entity_type=entity_type.value if entity_type else None,
                entity_id=entity_id,
                status=AiGenerationStatus.READY,
                model=result.model or None,
                content=parsed.model_dump(mode="json"),
                used_crm_context=used_crm_context,
                created_by_id=principal.user_id,
            )
        )
        return generation, parsed

    # --- Summaries & Account Intelligence ---------------------------------

    async def account_summary(self, principal: Principal, account: Account) -> AiGeneration:
        context = await build_account_context(self._session, account=account, principal=principal)
        system = build_prompt(
            role=ACCOUNT_SUMMARY_ROLE,
            task=ACCOUNT_SUMMARY_TASK,
            crm_context=context.text,
            schema=RecordSummaryOutput,
        )
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.ACCOUNT_SUMMARY,
            entity_type=CrmEntityType.ACCOUNT,
            entity_id=account.id,
            system=system,
            user_message=f"Summarize the account {account.name}.",
            schema=RecordSummaryOutput,
            used_crm_context=not context.is_empty,
        )
        return generation

    async def account_intelligence(self, principal: Principal, account: Account) -> AiGeneration:
        context = await build_account_context(self._session, account=account, principal=principal)
        system = build_prompt(
            role=ACCOUNT_INTELLIGENCE_ROLE,
            task=ACCOUNT_INTELLIGENCE_TASK,
            crm_context=context.text,
            schema=AccountIntelligenceOutput,
        )
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.ACCOUNT_INTELLIGENCE,
            entity_type=CrmEntityType.ACCOUNT,
            entity_id=account.id,
            system=system,
            user_message=f"Produce account intelligence for {account.name}.",
            schema=AccountIntelligenceOutput,
            used_crm_context=not context.is_empty,
        )
        return generation

    async def opportunity_summary(
        self, principal: Principal, opportunity: Opportunity
    ) -> AiGeneration:
        context = await build_opportunity_context(
            self._session, opportunity=opportunity, principal=principal
        )
        system = build_prompt(
            role=ACCOUNT_SUMMARY_ROLE,
            task=OPPORTUNITY_SUMMARY_TASK,
            crm_context=context.text,
            schema=RecordSummaryOutput,
        )
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.OPPORTUNITY_SUMMARY,
            entity_type=CrmEntityType.OPPORTUNITY,
            entity_id=opportunity.id,
            system=system,
            user_message=f"Summarize the deal {opportunity.name}.",
            schema=RecordSummaryOutput,
            used_crm_context=not context.is_empty,
        )
        return generation

    async def lead_summary(self, principal: Principal, lead: Lead) -> AiGeneration:
        context = await build_lead_context(self._session, lead=lead, principal=principal)
        system = build_prompt(
            role=ACCOUNT_SUMMARY_ROLE,
            task=LEAD_SUMMARY_TASK,
            crm_context=context.text,
            schema=RecordSummaryOutput,
        )
        name = f"{lead.first_name} {lead.last_name}".strip()
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.LEAD_SUMMARY,
            entity_type=CrmEntityType.LEAD,
            entity_id=lead.id,
            system=system,
            user_message=f"Summarize the lead {name}.",
            schema=RecordSummaryOutput,
            used_crm_context=not context.is_empty,
        )
        return generation

    # --- Next Best Action --------------------------------------------------

    async def next_best_action_for_opportunity(
        self, principal: Principal, opportunity: Opportunity
    ) -> AiGeneration:
        context = await build_opportunity_context(
            self._session, opportunity=opportunity, principal=principal
        )
        return await self._next_best_action(
            principal,
            entity_type=CrmEntityType.OPPORTUNITY,
            entity_id=opportunity.id,
            subject=f"the deal {opportunity.name}",
            context=context,
        )

    async def next_best_action_for_lead(self, principal: Principal, lead: Lead) -> AiGeneration:
        context = await build_lead_context(self._session, lead=lead, principal=principal)
        name = f"{lead.first_name} {lead.last_name}".strip()
        return await self._next_best_action(
            principal,
            entity_type=CrmEntityType.LEAD,
            entity_id=lead.id,
            subject=f"the lead {name}",
            context=context,
        )

    async def _next_best_action(
        self,
        principal: Principal,
        *,
        entity_type: CrmEntityType,
        entity_id: uuid.UUID,
        subject: str,
        context: CrmContext,
    ) -> AiGeneration:
        system = build_prompt(
            role=NEXT_BEST_ACTION_ROLE,
            task=NEXT_BEST_ACTION_TASK,
            crm_context=context.text,
            schema=NextBestActionOutput,
        )
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.NEXT_BEST_ACTION,
            entity_type=entity_type,
            entity_id=entity_id,
            system=system,
            user_message=f"Recommend the next best action for {subject}.",
            schema=NextBestActionOutput,
            used_crm_context=not context.is_empty,
        )
        return generation

    # --- AI email assistant -------------------------------------------------

    async def draft_email(self, principal: Principal, request: EmailDraftRequest) -> AiGeneration:
        entity_type: CrmEntityType
        entity_id: uuid.UUID
        context: CrmContext

        if request.contact_id is not None:
            contact = await self.resolve_contact(principal, request.contact_id)
            entity_type, entity_id = CrmEntityType.CONTACT, contact.id
            context = await self._contact_context(contact, principal)
        elif request.account_id is not None:
            account = await self.resolve_account(principal, request.account_id)
            entity_type, entity_id = CrmEntityType.ACCOUNT, account.id
            context = await build_account_context(
                self._session, account=account, principal=principal
            )
        elif request.opportunity_id is not None:
            opportunity = await self.resolve_opportunity(principal, request.opportunity_id)
            entity_type, entity_id = CrmEntityType.OPPORTUNITY, opportunity.id
            context = await build_opportunity_context(
                self._session, opportunity=opportunity, principal=principal
            )
        else:
            assert request.lead_id is not None  # noqa: S101 - schema enforces exactly one
            lead = await self.resolve_lead(principal, request.lead_id)
            entity_type, entity_id = CrmEntityType.LEAD, lead.id
            context = await build_lead_context(self._session, lead=lead, principal=principal)

        system = build_prompt(
            role=EMAIL_DRAFT_ROLE,
            task=email_draft_task(
                tone=request.tone, has_previous_draft=bool(request.previous_draft)
            ),
            crm_context=context.text,
            schema=EmailDraftOutput,
            user_text=(
                "Instruction, and previous draft if any",
                request.instruction
                + (
                    f"\n\n--- Previous draft ---\n{request.previous_draft}"
                    if request.previous_draft
                    else ""
                ),
            ),
        )
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.EMAIL_DRAFT,
            entity_type=entity_type,
            entity_id=entity_id,
            system=system,
            user_message="Draft the email described in the instruction.",
            schema=EmailDraftOutput,
            used_crm_context=not context.is_empty,
        )
        return generation

    async def _contact_context(self, contact: Contact, principal: Principal) -> CrmContext:
        lines = [
            "## Contact record",
            "",
            f"- Name: {contact.first_name} {contact.last_name}".strip(),
        ]
        if contact.job_title:
            lines.append(f"- Job title: {contact.job_title}")
        if contact.department:
            lines.append(f"- Department: {contact.department}")
        sections = ["contacts"]
        if contact.account_id is not None and principal.has_permission(
            "accounts", PermissionAction.VIEW
        ):
            account = await self._accounts.get_or_404(
                contact.account_id,
                principal.organization_id,
                visibility=RecordVisibility.for_module(principal, "accounts"),
            )
            account_context = await build_account_context(
                self._session, account=account, principal=principal
            )
            lines += ["", account_context.text]
            sections.extend(account_context.sections)
        return CrmContext(text="\n".join(lines).strip(), sections=tuple(sections))

    # --- Meeting-to-CRM ------------------------------------------------

    async def extract_meeting(
        self,
        principal: Principal,
        *,
        text: str,
        account: Account | None,
        opportunity: Opportunity | None,
    ) -> AiGeneration:
        context_text = ""
        entity_type: CrmEntityType | None = None
        entity_id: uuid.UUID | None = None
        if opportunity is not None:
            context = await build_opportunity_context(
                self._session, opportunity=opportunity, principal=principal
            )
            context_text = context.text
            entity_type, entity_id = CrmEntityType.OPPORTUNITY, opportunity.id
        elif account is not None:
            context = await build_account_context(
                self._session, account=account, principal=principal
            )
            context_text = context.text
            entity_type, entity_id = CrmEntityType.ACCOUNT, account.id

        system = build_prompt(
            role=MEETING_EXTRACTION_ROLE,
            task=MEETING_EXTRACTION_TASK,
            crm_context=context_text or None,
            schema=MeetingExtractionOutput,
            user_text=("Meeting notes / transcript", text),
        )
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.MEETING_EXTRACTION,
            entity_type=entity_type,
            entity_id=entity_id,
            system=system,
            user_message="Extract the structured meeting summary described above.",
            schema=MeetingExtractionOutput,
            used_crm_context=bool(context_text),
        )
        return generation

    async def apply_meeting_actions(
        self, principal: Principal, generation: AiGeneration, indexes: list[int]
    ) -> list[MeetingAppliedItem]:
        """Create the confirmed extraction items as real CRM records (§9).

        Every mutation goes through that entity's own service — the same
        create path a human using the Tasks/Notes screen would use, so
        permissions, validation and audit apply identically. An item that
        fails (e.g. an unparsable amount, a closed deal) is reported as
        ``FAILED`` for that one item; the others still apply.
        """
        # `applied_indexes` (written below) is bookkeeping this module adds to
        # the same JSONB column the schema itself is validated against; with
        # `MeetingExtractionOutput`'s `extra="forbid"`, re-validating the raw
        # column on a second call would fail on that very key. Validate only
        # the fields the schema actually declares.
        content = MeetingExtractionOutput.model_validate(
            {k: v for k, v in generation.content.items() if k != "applied_indexes"}
        )
        entity_type = CrmEntityType(generation.entity_type) if generation.entity_type else None
        entity_id = generation.entity_id

        results: list[MeetingAppliedItem] = []
        raw_applied = generation.content.get("applied_indexes")
        applied_so_far: list[int] = list(raw_applied) if isinstance(raw_applied, list) else []
        for index in indexes:
            if index < 0 or index >= len(content.follow_up_actions):
                results.append(
                    MeetingAppliedItem(
                        index=index,
                        kind="UNKNOWN",
                        description="",
                        outcome="FAILED",
                        reason="No such extracted item.",
                    )
                )
                continue
            if index in applied_so_far:
                item = content.follow_up_actions[index]
                results.append(
                    MeetingAppliedItem(
                        index=index,
                        kind=item.kind,
                        description=item.description,
                        outcome="SKIPPED",
                        reason="Already applied.",
                    )
                )
                continue
            item = content.follow_up_actions[index]
            outcome = await self._apply_one_meeting_action(
                principal, item, entity_type=entity_type, entity_id=entity_id
            )
            results.append(outcome)
            if outcome.outcome == "CREATED":
                applied_so_far.append(index)

        generation.content = {**generation.content, "applied_indexes": applied_so_far}
        await self._generations.flush()
        return results

    async def _apply_one_meeting_action(
        self,
        principal: Principal,
        item: MeetingActionItem,
        *,
        entity_type: CrmEntityType | None,
        entity_id: uuid.UUID | None,
    ) -> MeetingAppliedItem:
        # `TaskService.create_task`/`NoteService.create_note`/
        # `OpportunityService.update_open` are plain CRUD methods with no
        # permission check of their own — in this codebase that check is the
        # router's `require_permission` dependency, which nothing between here
        # and those calls provides. Without this, any caller holding only
        # `ai_insights.CREATE` could create tasks/notes or edit a deal's value
        # through meeting extraction regardless of their `tasks`/`notes`/
        # `opportunities` permissions — checked here instead, module by
        # module, the same permission each entity's own create/edit endpoint
        # requires.
        action_by_kind: dict[str, tuple[str, PermissionAction]] = {
            "TASK": ("tasks", PermissionAction.CREATE),
            "NOTE": ("notes", PermissionAction.CREATE),
            "OPPORTUNITY_AMOUNT": ("opportunities", PermissionAction.EDIT),
        }
        required = action_by_kind.get(item.kind)
        if required is not None and not principal.has_permission(*required):
            return MeetingAppliedItem(
                index=-1,
                kind=item.kind,
                description=item.description,
                outcome="FAILED",
                reason="You do not have permission to create this.",
            )

        if item.kind == "TASK":
            if entity_type is None or entity_id is None:
                task = await self._tasks.create_task(
                    organization_id=principal.organization_id,
                    actor_id=principal.user_id,
                    values={
                        "title": item.description[:255],
                        "owner_id": principal.user_id,
                        "assigned_to_id": principal.user_id,
                    },
                )
            else:
                task = await self._tasks.create_task(
                    organization_id=principal.organization_id,
                    actor_id=principal.user_id,
                    values={
                        "title": item.description[:255],
                        "owner_id": principal.user_id,
                        "assigned_to_id": principal.user_id,
                        "related_entity_type": entity_type,
                        "related_entity_id": entity_id,
                    },
                )
            return MeetingAppliedItem(
                index=-1,
                kind=item.kind,
                description=item.description,
                outcome="CREATED",
                entity_type="TASK",
                entity_id=task.id,
            )

        if item.kind == "NOTE":
            values: dict[str, Any] = {
                "content": item.description,
                "visibility": NoteVisibility.ORGANIZATION,
            }
            if entity_type is not None and entity_id is not None:
                values["related_entity_type"] = entity_type
                values["related_entity_id"] = entity_id
            note = await self._notes.create_note(
                organization_id=principal.organization_id, actor_id=principal.user_id, values=values
            )
            return MeetingAppliedItem(
                index=-1,
                kind=item.kind,
                description=item.description,
                outcome="CREATED",
                entity_type="NOTE",
                entity_id=note.id,
            )

        if item.kind == "OPPORTUNITY_AMOUNT":
            if entity_type is not CrmEntityType.OPPORTUNITY or entity_id is None:
                return MeetingAppliedItem(
                    index=-1,
                    kind=item.kind,
                    description=item.description,
                    outcome="FAILED",
                    reason="This extraction is not linked to a deal.",
                )
            amount = _parse_amount(item.amount)
            if amount is None:
                return MeetingAppliedItem(
                    index=-1,
                    kind=item.kind,
                    description=item.description,
                    outcome="FAILED",
                    reason="Could not parse an amount from the extracted text.",
                )
            opportunity = await self.resolve_opportunity(principal, entity_id)
            try:
                await self._opportunities.update_open(
                    opportunity, actor_id=principal.user_id, values={"deal_value": amount}
                )
            except OpportunityClosedError:
                return MeetingAppliedItem(
                    index=-1,
                    kind=item.kind,
                    description=item.description,
                    outcome="FAILED",
                    reason="This deal is already closed.",
                )
            return MeetingAppliedItem(
                index=-1,
                kind=item.kind,
                description=item.description,
                outcome="CREATED",
                entity_type="OPPORTUNITY",
                entity_id=opportunity.id,
            )

        # `item.kind` is `Literal["TASK", "NOTE", "OPPORTUNITY_AMOUNT"]`; the
        # three branches above are exhaustive (mypy confirms it — a trailing
        # "unsupported kind" fallback here was dead code and has been removed).
        raise AssertionError

    # --- Natural-language CRM ------------------------------------------

    async def run_nl_query(
        self, principal: Principal, question: str
    ) -> tuple[AiGeneration, NlQueryTranslation, ReportResult | None]:
        entities_hint = _entities_hint(principal)
        system = build_prompt(
            role=NL_QUERY_ROLE,
            task=nl_query_task(entities_hint=entities_hint),
            crm_context=None,
            schema=NlQueryTranslation,
            user_text=("Question", question),
        )
        generation, translation = await self._generate(
            principal,
            feature=AiFeature.NL_QUERY,
            entity_type=None,
            entity_id=None,
            system=system,
            user_message="Translate the question above.",
            schema=NlQueryTranslation,
            used_crm_context=False,
        )

        result: ReportResult | None = None
        if translation.understood and translation.definition is not None:
            module = _module_for_entity(translation.definition.entity)
            if not principal.has_permission(module, PermissionAction.VIEW):
                # The translation is kept for transparency, but nothing is
                # executed: the same authorization CustomReportEngine.run
                # would refuse is enforced here too, so a caller cannot use
                # the AI path to learn whether they *would* be allowed to run
                # a report they may not run directly (§17).
                translation = NlQueryTranslation(
                    understood=False,
                    definition=None,
                    clarification="You do not have permission to view that data.",
                )
            else:
                engine = CustomReportEngine(self._session)
                result = await engine.run(translation.definition, principal)

        generation.content = {
            **generation.content,
            "executed": result is not None,
            "row_count": len(result.rows) if result is not None else None,
        }
        await self._generations.flush()
        return generation, translation, result

    # --- Prioritization (rules; AI only narrates) ------------------------

    async def prioritize_opportunities(
        self, principal: Principal, *, limit: int = 25
    ) -> list[PriorityScoreResponse]:
        if not principal.has_permission("opportunities", PermissionAction.VIEW):
            return []
        visibility = RecordVisibility.for_module(principal, "opportunities")
        statement = (
            select(Opportunity, PipelineStage.name)
            .join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
            .where(
                Opportunity.organization_id == principal.organization_id,
                Opportunity.deleted_at.is_(None),
                Opportunity.won_at.is_(None),
                Opportunity.lost_at.is_(None),
            )
            .order_by(Opportunity.updated_at.desc())
            .limit(MAX_PRIORITY_CANDIDATES)
        )
        predicate = visibility.filter_for(Opportunity)
        if predicate is not None:
            statement = statement.where(predicate)
        rows = (await self._session.execute(statement)).all()
        opportunities = [row[0] for row in rows]
        stage_names = {row[0].id: row[1] for row in rows}

        last_activity = await self._last_activity_by_entity(
            principal.organization_id, CrmEntityType.OPPORTUNITY, [o.id for o in opportunities]
        )
        overdue = await self._overdue_task_counts(
            principal.organization_id, CrmEntityType.OPPORTUNITY, [o.id for o in opportunities]
        )

        scored = []
        today = dt.datetime.now(dt.UTC).date()
        for opportunity in opportunities:
            last = last_activity.get(opportunity.id)
            days_since = (dt.datetime.now(dt.UTC) - last).days if last else None
            score = prioritization.score_opportunity(
                opportunity_id=opportunity.id,
                deal_value=opportunity.deal_value,
                currency=opportunity.currency,
                win_probability=opportunity.win_probability,
                expected_close_date=opportunity.expected_close_date,
                stage_name=stage_names[opportunity.id],
                is_won=False,
                is_lost=False,
                days_since_last_activity=days_since,
                overdue_task_count=overdue.get(opportunity.id, 0),
                today=today,
            )
            if score is not None:
                scored.append(score)
        scored.sort(key=lambda s: s.score, reverse=True)
        by_id = {opportunity.id: opportunity for opportunity in opportunities}
        return await self._opportunity_responses(
            principal, scored[:limit], by_id, stage_names, last_activity, overdue
        )

    async def _opportunity_responses(
        self,
        principal: Principal,
        top: Sequence[prioritization.PriorityScore],
        by_id: dict[uuid.UUID, Opportunity],
        stage_names: dict[uuid.UUID, str],
        last_activity: dict[uuid.UUID, dt.datetime],
        overdue: dict[uuid.UUID, int],
    ) -> list[PriorityScoreResponse]:
        """Facts and Next Best Actions for an already-ranked page of deals.

        Computed for the ranked page only — never the whole candidate set, and
        never an input to the score.
        """
        top_ids = [s.entity_id for s in top]
        if not top_ids:
            return []
        account_names = await self._visible_account_names(
            principal, {by_id[entity_id].account_id for entity_id in top_ids}
        )
        open_tasks = await self._open_task_counts(
            principal.organization_id, CrmEntityType.OPPORTUNITY, top_ids
        )
        recommendations = await self._generations.latest_for_many(
            principal.organization_id,
            entity_type=CrmEntityType.OPPORTUNITY.value,
            entity_ids=top_ids,
            feature=AiFeature.NEXT_BEST_ACTION,
        )

        now = dt.datetime.now(dt.UTC)
        signals, open_deals = await nba_collect.opportunity_signals(
            self._session,
            principal,
            [by_id[entity_id] for entity_id in top_ids],
            open_tasks=open_tasks,
            overdue=overdue,
            now=now,
        )
        history = await nba_collect.closed_deal_history(self._session, principal, now=now)
        rules = await self._effective_nba_rules(principal.organization_id)
        logs = await nba_collect.recent_action_logs(
            self._session,
            principal.organization_id,
            CrmEntityType.OPPORTUNITY.value,
            top_ids,
            now=now,
        )

        responses = []
        for s in top:
            opportunity = by_id[s.entity_id]
            snapshot = signals.get(opportunity.id, {})
            deal = open_deals.get(opportunity.id)
            predicted: list[nba_rules.RecommendedAction] = []
            if deal is not None:
                similar = nba_predictive.similar_win_rate(deal.band, history)
                snapshot["similar_deal_win_rate"] = similar[0] if similar else None
                predicted = nba_predictive.predict(
                    band=deal.band,
                    done=deal.done,
                    past_proposal=deal.past_proposal,
                    history=history,
                )
            facts = PriorityRecordFacts(
                account_id=opportunity.account_id,
                account_name=account_names.get(opportunity.account_id),
                stage_name=stage_names[opportunity.id],
                deal_value=opportunity.deal_value,
                currency=opportunity.currency,
                win_probability=opportunity.win_probability,
                expected_close_date=opportunity.expected_close_date,
                last_activity_at=last_activity.get(opportunity.id),
                open_task_count=open_tasks.get(opportunity.id, 0),
                overdue_task_count=overdue.get(opportunity.id, 0),
            )
            responses.append(
                _to_priority_response(
                    s,
                    opportunity.name,
                    facts=facts,
                    latest_recommendation=recommendations.get(opportunity.id),
                    actions=_engine_actions(
                        RecordKind.OPPORTUNITY,
                        snapshot,
                        rules,
                        predicted,
                        logs.get(opportunity.id, {}),
                        now,
                    ),
                    signals=_public_signals(snapshot),
                )
            )
        return responses

    async def prioritize_leads(
        self, principal: Principal, *, limit: int = 25
    ) -> list[PriorityScoreResponse]:
        if not principal.has_permission("leads", PermissionAction.VIEW):
            return []
        visibility = RecordVisibility.for_module(principal, "leads")
        statement = (
            select(Lead)
            .where(
                Lead.organization_id == principal.organization_id,
                Lead.deleted_at.is_(None),
                Lead.status.not_in((LeadStatus.CONVERTED, LeadStatus.LOST, LeadStatus.UNQUALIFIED)),
            )
            .order_by(Lead.created_at.desc())
            .limit(MAX_PRIORITY_CANDIDATES)
        )
        predicate = visibility.filter_for(Lead)
        if predicate is not None:
            statement = statement.where(predicate)
        leads = (await self._session.execute(statement)).scalars().all()

        last_activity = await self._last_activity_by_entity(
            principal.organization_id, CrmEntityType.LEAD, [lead.id for lead in leads]
        )
        overdue = await self._overdue_task_counts(
            principal.organization_id, CrmEntityType.LEAD, [lead.id for lead in leads]
        )
        open_tasks = await self._open_task_flags(
            principal.organization_id, CrmEntityType.LEAD, [lead.id for lead in leads]
        )

        now = dt.datetime.now(dt.UTC)
        scored = []
        for lead in leads:
            last = last_activity.get(lead.id)
            days_since = (now - last).days if last else None
            score = prioritization.score_lead(
                lead_id=lead.id,
                status=lead.status.value,
                crm_priority=lead.priority.value if lead.priority else None,
                expected_deal_size=lead.expected_deal_size,
                days_since_created=(now - lead.created_at).days,
                days_since_last_activity=days_since,
                has_open_tasks=open_tasks.get(lead.id, False),
                overdue_task_count=overdue.get(lead.id, 0),
            )
            if score is not None:
                scored.append(score)
        scored.sort(key=lambda s: s.score, reverse=True)
        by_id = {lead.id: lead for lead in leads}
        return await self._lead_responses(principal, scored[:limit], by_id, last_activity, overdue)

    async def _lead_responses(
        self,
        principal: Principal,
        top: Sequence[prioritization.PriorityScore],
        by_id: dict[uuid.UUID, Lead],
        last_activity: dict[uuid.UUID, dt.datetime],
        overdue: dict[uuid.UUID, int],
    ) -> list[PriorityScoreResponse]:
        top_ids = [s.entity_id for s in top]
        if not top_ids:
            return []
        open_task_counts = await self._open_task_counts(
            principal.organization_id, CrmEntityType.LEAD, top_ids
        )
        recommendations = await self._generations.latest_for_many(
            principal.organization_id,
            entity_type=CrmEntityType.LEAD.value,
            entity_ids=top_ids,
            feature=AiFeature.NEXT_BEST_ACTION,
        )
        now = dt.datetime.now(dt.UTC)
        signals = await nba_collect.lead_signals(
            self._session,
            principal,
            [by_id[entity_id] for entity_id in top_ids],
            open_tasks=open_task_counts,
            overdue=overdue,
            now=now,
        )
        rules = await self._effective_nba_rules(principal.organization_id)
        logs = await nba_collect.recent_action_logs(
            self._session, principal.organization_id, CrmEntityType.LEAD.value, top_ids, now=now
        )

        responses = []
        for s in top:
            lead = by_id[s.entity_id]
            snapshot = signals.get(lead.id, {})
            facts = PriorityRecordFacts(
                company=lead.company,
                email=lead.email,
                phone=lead.phone,
                status=lead.status.value,
                expected_deal_size=lead.expected_deal_size,
                last_activity_at=last_activity.get(lead.id),
                open_task_count=open_task_counts.get(lead.id, 0),
                overdue_task_count=overdue.get(lead.id, 0),
            )
            responses.append(
                _to_priority_response(
                    s,
                    f"{lead.first_name} {lead.last_name}".strip() or lead.company or "Lead",
                    facts=facts,
                    latest_recommendation=recommendations.get(lead.id),
                    actions=_engine_actions(
                        RecordKind.LEAD, snapshot, rules, [], logs.get(lead.id, {}), now
                    ),
                    signals=_public_signals(snapshot),
                )
            )
        return responses

    # --- Next Best Action: one record ------------------------------------

    async def nba_for_opportunity(
        self, principal: Principal, opportunity_id: uuid.UUID
    ) -> PriorityScoreResponse | None:
        """The queue entry for one deal — ``None`` once it is closed."""
        opportunity = await self.resolve_opportunity(principal, opportunity_id)
        score = await self.score_opportunity(principal, opportunity_id)
        if score is None:
            return None
        stage_name = (
            await self._session.execute(
                select(PipelineStage.name).where(PipelineStage.id == opportunity.stage_id)
            )
        ).scalar_one_or_none()
        ids = [opportunity.id]
        last_activity = await self._last_activity_by_entity(
            principal.organization_id, CrmEntityType.OPPORTUNITY, ids
        )
        overdue = await self._overdue_task_counts(
            principal.organization_id, CrmEntityType.OPPORTUNITY, ids
        )
        responses = await self._opportunity_responses(
            principal,
            [score],
            {opportunity.id: opportunity},
            {opportunity.id: stage_name or ""},
            last_activity,
            overdue,
        )
        return responses[0] if responses else None

    async def nba_for_lead(
        self, principal: Principal, lead_id: uuid.UUID
    ) -> PriorityScoreResponse | None:
        """The queue entry for one lead — ``None`` once it is inactive."""
        lead = await self.resolve_lead(principal, lead_id)
        score = await self.score_lead(principal, lead_id)
        if score is None:
            return None
        ids = [lead.id]
        last_activity = await self._last_activity_by_entity(
            principal.organization_id, CrmEntityType.LEAD, ids
        )
        overdue = await self._overdue_task_counts(
            principal.organization_id, CrmEntityType.LEAD, ids
        )
        responses = await self._lead_responses(
            principal, [score], {lead.id: lead}, last_activity, overdue
        )
        return responses[0] if responses else None

    # --- Next Best Action: rules ------------------------------------------

    async def _effective_nba_rules(self, organization_id: uuid.UUID) -> list[nba_rules.RuleDef]:
        rows = await self._nba_rule_rows.all_live(organization_id)
        overrides: dict[str, dict[str, Any]] = {}
        custom: list[nba_rules.RuleDef] = []
        for row in rows:
            if row.builtin_key is not None:
                overrides[row.builtin_key] = {
                    "is_active": row.is_active,
                    "priority": row.priority,
                    "conditions": row.conditions,
                    "logic": row.condition_logic,
                    "cooldown_days": row.cooldown_days,
                }
            else:
                custom.append(_custom_rule_def(row))
        return nba_rules.effective_rules(overrides, custom)

    @staticmethod
    def nba_catalog() -> NbaCatalogResponse:
        return NbaCatalogResponse(
            categories=[category.value for category in ActionCategory],
            actions=[
                NbaCatalogAction(
                    code=action.code,
                    category=action.category.value,
                    label=action.label,
                    execution=action.execution.value,
                    copilot=action.copilot.value if action.copilot else None,
                    applies_to=sorted(kind.value for kind in action.applies_to),
                )
                for action in ACTIONS.values()
            ],
            signals=[
                NbaCatalogSignal(
                    key=signal.key,
                    label=signal.label,
                    kind=signal.kind,
                    applies_to=sorted(kind.value for kind in signal.applies_to),
                    source=signal.source,
                )
                for signal in SIGNALS.values()
            ],
            operators=sorted(CONDITION_OPERATORS),
        )

    async def list_nba_rules(self, principal: Principal) -> list[NbaRuleResponse]:
        rows = await self._nba_rule_rows.all_live(principal.organization_id)
        overrides = {row.builtin_key: row for row in rows if row.builtin_key is not None}
        responses = [
            _builtin_rule_response(rule, overrides.get(key))
            for key, rule in nba_rules.BUILTIN_RULES.items()
        ]
        responses.extend(_custom_rule_response(row) for row in rows if row.builtin_key is None)
        return responses

    async def create_nba_rule(
        self, principal: Principal, payload: NbaRuleCreate
    ) -> NbaRuleResponse:
        conditions = [condition.model_dump() for condition in payload.conditions]
        _validate_rule(
            payload.applies_to, payload.logic, conditions, payload.action_code, payload.priority
        )
        if await self._nba_rule_rows.name_taken(principal.organization_id, payload.name):
            raise ConflictError("A rule with this name already exists.")
        existing = [
            row
            for row in await self._nba_rule_rows.all_live(principal.organization_id)
            if row.builtin_key is None
        ]
        row = await self._nba_rule_service.create(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            values={
                "name": payload.name,
                "description": payload.description,
                "applies_to": payload.applies_to,
                "condition_logic": payload.logic,
                "conditions": conditions,
                "action_code": payload.action_code,
                "priority": payload.priority,
                "reason": payload.reason,
                "timing": payload.timing,
                "due_in_hours": payload.due_in_hours,
                "cooldown_days": payload.cooldown_days,
                "is_active": payload.is_active,
                "position": len(existing),
            },
        )
        return _custom_rule_response(row)

    async def _custom_rule_or_404(self, principal: Principal, rule_id: uuid.UUID) -> NbaRule:
        row = await self._nba_rule_rows.get(rule_id, principal.organization_id)
        if row is None or row.builtin_key is not None:
            raise NotFoundError("Rule not found.")
        return row

    async def update_nba_rule(
        self, principal: Principal, rule_id: uuid.UUID, payload: NbaRuleUpdate
    ) -> NbaRuleResponse:
        row = await self._custom_rule_or_404(principal, rule_id)
        changes = payload.model_dump(exclude_unset=True)
        applies_to = changes.get("applies_to", row.applies_to)
        logic = changes.get("logic", row.condition_logic)
        conditions = changes.get("conditions", row.conditions)
        action_code = changes.get("action_code", row.action_code)
        priority = changes.get("priority", row.priority)
        _validate_rule(applies_to, logic, conditions, action_code, priority)
        if "name" in changes and await self._nba_rule_rows.name_taken(
            principal.organization_id, changes["name"], exclude_id=row.id
        ):
            raise ConflictError("A rule with this name already exists.")
        values = {key: value for key, value in changes.items() if key not in {"logic"}}
        if "logic" in changes:
            values["condition_logic"] = changes["logic"]
        updated = await self._nba_rule_service.update(
            row, actor_id=principal.user_id, values=values
        )
        return _custom_rule_response(updated)

    async def delete_nba_rule(self, principal: Principal, rule_id: uuid.UUID) -> None:
        row = await self._custom_rule_or_404(principal, rule_id)
        await self._nba_rule_service.soft_delete(row, actor_id=principal.user_id)

    async def override_builtin_rule(
        self, principal: Principal, key: str, payload: NbaBuiltinOverride
    ) -> NbaRuleResponse:
        rule = nba_rules.BUILTIN_RULES.get(key)
        if rule is None:
            raise NotFoundError("Rule not found.")
        changes = payload.model_dump(exclude_unset=True)
        conditions = changes.get("conditions")
        if conditions is not None:
            _validate_rule(
                _applies_to_value(rule.applies_to),
                changes.get("logic", rule.logic),
                conditions,
                rule.action_code,
                changes.get("priority", rule.priority),
            )
        row = await self._nba_rule_rows.builtin_override(principal.organization_id, key)
        values: dict[str, Any] = {}
        if "is_active" in changes:
            values["is_active"] = changes["is_active"]
        if "priority" in changes:
            values["priority"] = changes["priority"]
        if "logic" in changes:
            values["condition_logic"] = changes["logic"]
        if conditions is not None:
            values["conditions"] = conditions
        if "cooldown_days" in changes:
            values["cooldown_days"] = changes["cooldown_days"]
        if row is None:
            row = await self._nba_rule_service.create(
                organization_id=principal.organization_id,
                actor_id=principal.user_id,
                values={
                    "builtin_key": key,
                    "name": rule.name,
                    "applies_to": _applies_to_value(rule.applies_to),
                    "condition_logic": rule.logic,
                    "conditions": [],
                    "action_code": rule.action_code,
                    "priority": rule.priority,
                    "reason": "",
                    "cooldown_days": rule.cooldown_days,
                    "is_active": rule.is_active,
                    "position": rule.position,
                    **values,
                },
            )
        elif values:
            row = await self._nba_rule_service.update(
                row, actor_id=principal.user_id, values=values
            )
        return _builtin_rule_response(rule, row)

    async def reset_builtin_rule(self, principal: Principal, key: str) -> None:
        if key not in nba_rules.BUILTIN_RULES:
            raise NotFoundError("Rule not found.")
        row = await self._nba_rule_rows.builtin_override(principal.organization_id, key)
        if row is not None:
            await self._nba_rule_service.soft_delete(row, actor_id=principal.user_id)

    # --- Next Best Action: acting on a recommendation ---------------------

    async def _resolve_nba_record(
        self, principal: Principal, entity_type: str, entity_id: uuid.UUID
    ) -> Opportunity | Lead:
        if entity_type == "OPPORTUNITY":
            return await self.resolve_opportunity(principal, entity_id)
        return await self.resolve_lead(principal, entity_id)

    async def log_nba_action(
        self, principal: Principal, payload: NbaActionLogCreate
    ) -> NbaActionLogResponse:
        """Record that a rep executed or dismissed an action on a record they can see."""
        await self._resolve_nba_record(principal, payload.entity_type, payload.entity_id)
        action = ACTIONS.get(payload.action_code)
        if action is None or RecordKind(payload.entity_type) not in action.applies_to:
            raise ValidationFailedError("That action does not apply to this record.")
        log = await self._nba_logs.add(
            NbaActionLog(
                organization_id=principal.organization_id,
                entity_type=payload.entity_type,
                entity_id=payload.entity_id,
                action_code=payload.action_code,
                outcome=NbaActionOutcome(payload.outcome),
                rule_keys=list(payload.rule_keys),
                generation_id=payload.generation_id,
                note=payload.note,
                actor_id=principal.user_id,
            )
        )
        return NbaActionLogResponse.model_validate(log)

    async def nba_copilot(self, principal: Principal, payload: NbaCopilotRequest) -> AiGeneration:
        """Level 3: draft what an action needs, for the rep to review and approve.

        Nothing is sent, scheduled or written to the record here — the draft is
        stored as an ``NBA_COPILOT`` generation and returned. Approval happens
        in the CRM's own compose/schedule/task flows, under their permissions.
        """
        record = await self._resolve_nba_record(principal, payload.entity_type, payload.entity_id)
        kind = RecordKind(payload.entity_type)
        action = ACTIONS.get(payload.action_code)
        if action is None or kind not in action.applies_to:
            raise ValidationFailedError("That action does not apply to this record.")
        copilot_kind = payload.kind or (action.copilot.value if action.copilot else None)
        if copilot_kind is None:
            raise ValidationFailedError("The Copilot has no draft for this action.")
        schema = _COPILOT_SCHEMAS[copilot_kind]

        if isinstance(record, Opportunity):
            context = await build_opportunity_context(
                self._session, opportunity=record, principal=principal
            )
            current = await self.nba_for_opportunity(principal, record.id)
            subject = f"the deal {record.name}"
        else:
            context = await build_lead_context(self._session, lead=record, principal=principal)
            current = await self.nba_for_lead(principal, record.id)
            subject = f"the lead {record.first_name} {record.last_name}".strip()
        reasons: list[str] = []
        if current is not None:
            match = next((a for a in current.actions if a.action_code == action.code), None)
            reasons = list(match.reasons) if match else []

        system = build_prompt(
            role=NBA_COPILOT_ROLE,
            task=nba_copilot_task(kind=copilot_kind, action_label=action.label, reasons=reasons),
            crm_context=context.text,
            schema=schema,
            user_text=("Rep instruction", payload.instruction) if payload.instruction else None,
        )
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.NBA_COPILOT,
            entity_type=CrmEntityType(payload.entity_type),
            entity_id=record.id,
            system=system,
            user_message=f"Prepare the draft to {action.label.lower()} for {subject}.",
            schema=schema,
            used_crm_context=not context.is_empty,
        )
        generation.content = {
            "kind": copilot_kind,
            "action_code": action.code,
            **generation.content,
        }
        await self._generations.flush()
        return generation

    # --- Single-record scoring, for the "explain" action -------------------

    async def score_opportunity(
        self, principal: Principal, opportunity_id: uuid.UUID
    ) -> prioritization.PriorityScore | None:
        """Score one opportunity the caller can see. ``None`` if it is closed."""
        opportunity = await self.resolve_opportunity(principal, opportunity_id)
        if opportunity.won_at is not None or opportunity.lost_at is not None:
            return None
        stage_name = (
            await self._session.execute(
                select(PipelineStage.name).where(PipelineStage.id == opportunity.stage_id)
            )
        ).scalar_one_or_none()
        last_activity = await self._last_activity_by_entity(
            principal.organization_id, CrmEntityType.OPPORTUNITY, [opportunity.id]
        )
        overdue = await self._overdue_task_counts(
            principal.organization_id, CrmEntityType.OPPORTUNITY, [opportunity.id]
        )
        last = last_activity.get(opportunity.id)
        days_since = (dt.datetime.now(dt.UTC) - last).days if last else None
        return prioritization.score_opportunity(
            opportunity_id=opportunity.id,
            deal_value=opportunity.deal_value,
            currency=opportunity.currency,
            win_probability=opportunity.win_probability,
            expected_close_date=opportunity.expected_close_date,
            stage_name=stage_name or "",
            is_won=False,
            is_lost=False,
            days_since_last_activity=days_since,
            overdue_task_count=overdue.get(opportunity.id, 0),
        )

    async def score_lead(
        self, principal: Principal, lead_id: uuid.UUID
    ) -> prioritization.PriorityScore | None:
        """Score one lead the caller can see. ``None`` if it is inactive."""
        lead = await self.resolve_lead(principal, lead_id)
        if lead.status in (LeadStatus.CONVERTED, LeadStatus.LOST, LeadStatus.UNQUALIFIED):
            return None
        now = dt.datetime.now(dt.UTC)
        last_activity = await self._last_activity_by_entity(
            principal.organization_id, CrmEntityType.LEAD, [lead.id]
        )
        overdue = await self._overdue_task_counts(
            principal.organization_id, CrmEntityType.LEAD, [lead.id]
        )
        open_tasks = await self._open_task_flags(
            principal.organization_id, CrmEntityType.LEAD, [lead.id]
        )
        last = last_activity.get(lead.id)
        days_since = (now - last).days if last else None
        return prioritization.score_lead(
            lead_id=lead.id,
            status=lead.status.value,
            crm_priority=lead.priority.value if lead.priority else None,
            expected_deal_size=lead.expected_deal_size,
            days_since_created=(now - lead.created_at).days,
            days_since_last_activity=days_since,
            has_open_tasks=open_tasks.get(lead.id, False),
            overdue_task_count=overdue.get(lead.id, 0),
        )

    async def explain_priority(
        self, principal: Principal, *, score: prioritization.PriorityScore, subject: str
    ) -> AiGeneration:
        reasons_text = "\n".join(f"- {r.label}: {r.detail}" for r in score.reasons)
        system = build_prompt(
            role=PRIORITY_EXPLANATION_ROLE,
            task=priority_explanation_task(level=score.level, reasons_text=reasons_text),
            crm_context=None,
            schema=PriorityExplanationOutput,
        )
        entity_type = CrmEntityType(score.entity_type)
        generation, _ = await self._generate(
            principal,
            feature=AiFeature.PRIORITIZATION_EXPLANATION,
            entity_type=entity_type,
            entity_id=score.entity_id,
            system=system,
            user_message=f"Explain the priority for {subject}.",
            schema=PriorityExplanationOutput,
            used_crm_context=False,
        )
        return generation

    # --- Insights digest (rules only) ------------------------------------

    async def insights_digest(self, principal: Principal) -> InsightsDigest:
        deals_at_risk = await insights_queries.deals_at_risk(self._session, principal=principal)
        stale = await insights_queries.stale_opportunities(self._session, principal=principal)
        neglected = await insights_queries.neglected_leads(self._session, principal=principal)
        accounts = await insights_queries.accounts_needing_attention(
            self._session, principal=principal
        )
        overdue = await insights_queries.overdue_tasks(self._session, principal=principal)
        return InsightsDigest(
            generated_at=dt.datetime.now(dt.UTC),
            deals_at_risk=[_to_insight_item(i) for i in deals_at_risk],
            stale_opportunities=[_to_insight_item(i) for i in stale],
            neglected_leads=[_to_insight_item(i) for i in neglected],
            accounts_needing_attention=[_to_insight_item(i) for i in accounts],
            overdue_tasks=[_to_insight_item(i) for i in overdue],
        )

    # --- Batched signal queries for prioritization ------------------------
    #
    # Each excludes archived (soft-deleted) rows. A reason must be a fact the
    # caller could check by opening the record, and archived tasks and
    # activities are gone from the record's own timeline — so an archived
    # overdue task is not "overdue work", and an archived call is not "last
    # contact".

    async def _last_activity_by_entity(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType, entity_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dt.datetime]:
        if not entity_ids:
            return {}
        statement = (
            select(
                Activity.related_entity_id,
                func.max(
                    func.coalesce(Activity.completed_at, Activity.due_date, Activity.created_at)
                ),
            )
            .where(
                Activity.organization_id == organization_id,
                Activity.deleted_at.is_(None),
                Activity.related_entity_type == entity_type,
                Activity.related_entity_id.in_(entity_ids),
            )
            .group_by(Activity.related_entity_id)
        )
        rows = (await self._session.execute(statement)).all()
        return {row[0]: row[1] for row in rows if row[1] is not None}

    async def _overdue_task_counts(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType, entity_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        if not entity_ids:
            return {}
        statement = (
            select(Task.related_entity_id, func.count())
            .where(
                Task.organization_id == organization_id,
                Task.deleted_at.is_(None),
                Task.related_entity_type == entity_type,
                Task.related_entity_id.in_(entity_ids),
                Task.status.not_in(tuple(CLOSED_STATUSES)),
                Task.due_date.is_not(None),
                Task.due_date < dt.datetime.now(dt.UTC),
            )
            .group_by(Task.related_entity_id)
        )
        rows = (await self._session.execute(statement)).all()
        return {row[0]: int(row[1]) for row in rows}

    async def _open_task_flags(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType, entity_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, bool]:
        if not entity_ids:
            return {}
        statement = (
            select(Task.related_entity_id)
            .where(
                Task.organization_id == organization_id,
                Task.deleted_at.is_(None),
                Task.related_entity_type == entity_type,
                Task.related_entity_id.in_(entity_ids),
                Task.status.not_in(tuple(CLOSED_STATUSES)),
            )
            .distinct()
        )
        rows = (await self._session.execute(statement)).scalars().all()
        return dict.fromkeys((entity_id for entity_id in rows if entity_id is not None), True)

    async def _open_task_counts(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType, entity_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, int]:
        """Open tasks per record — the same "open" ``_open_task_flags`` scores
        on, counted, so the queue's follow-up state agrees with its reasons.
        Archived tasks are gone from the record, so they are not counted.
        """
        if not entity_ids:
            return {}
        statement = (
            select(Task.related_entity_id, func.count())
            .where(
                Task.organization_id == organization_id,
                Task.deleted_at.is_(None),
                Task.related_entity_type == entity_type,
                Task.related_entity_id.in_(entity_ids),
                Task.status.not_in(tuple(CLOSED_STATUSES)),
            )
            .group_by(Task.related_entity_id)
        )
        rows = (await self._session.execute(statement)).all()
        return {row[0]: int(row[1]) for row in rows}

    async def _visible_account_names(
        self, principal: Principal, account_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """Names of the accounts the caller may see, by id.

        Seeing a deal does not grant seeing its account, so the account's own
        permission and record visibility decide — the same rule
        ``GET /crm/accounts/{id}`` applies. An account missing here renders as
        no name, never as a leaked one.
        """
        if not account_ids or not principal.has_permission("accounts", PermissionAction.VIEW):
            return {}
        statement = select(Account.id, Account.name).where(
            Account.organization_id == principal.organization_id,
            Account.deleted_at.is_(None),
            Account.id.in_(account_ids),
        )
        predicate = RecordVisibility.for_module(principal, "accounts").filter_for(Account)
        if predicate is not None:
            statement = statement.where(predicate)
        rows = (await self._session.execute(statement)).all()
        return {row[0]: row[1] for row in rows}


def _parse_amount(raw: str | None) -> Decimal | None:
    if not raw:
        return None
    cleaned = raw.strip().replace(",", "")
    for prefix in ("₹", "$", "€", "£"):
        cleaned = cleaned.removeprefix(prefix)
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value <= 0:
        return None
    return value


def _entities_hint(principal: Principal) -> str:
    lines: list[str] = []
    for entity in ReportEntity:
        module = _module_for_entity(entity)
        if not principal.has_permission(module, PermissionAction.VIEW):
            continue
        keys = ", ".join(sorted(FIELDS[entity]))
        lines.append(f"- {entity.value}: {keys}")
    return "\n".join(lines) if lines else "(no readable entities)"


def _module_for_entity(entity: ReportEntity) -> str:
    return MODULE_FOR_ENTITY[entity]


def _to_priority_response(
    score: prioritization.PriorityScore,
    entity_label: str,
    *,
    facts: PriorityRecordFacts,
    latest_recommendation: AiGeneration | None,
    actions: list[NbaActionResponse] | None = None,
    signals: dict[str, Any] | None = None,
) -> PriorityScoreResponse:
    return PriorityScoreResponse(
        entity_type=score.entity_type,
        entity_id=score.entity_id,
        entity_label=entity_label,
        level=score.level,
        score=score.score,
        reasons=[PriorityReasonSchema(label=r.label, detail=r.detail) for r in score.reasons],
        facts=facts,
        latest_recommendation=(
            AiGenerationResponse.model_validate(latest_recommendation)
            if latest_recommendation is not None
            else None
        ),
        actions=actions or [],
        signals=signals or {},
    )


# ---------------------------------------------------------------------------
# Next Best Action engine helpers
# ---------------------------------------------------------------------------

#: A dismissed action stays hidden at least this long, whatever its cooldown.
DISMISS_COOLDOWN_DAYS = 7

_COPILOT_SCHEMAS: dict[str, type[Any]] = {
    CopilotKind.EMAIL.value: CopilotEmailOutput,
    CopilotKind.MESSAGE.value: CopilotMessageOutput,
    CopilotKind.MEETING_AGENDA.value: CopilotMeetingOutput,
    CopilotKind.CALL_SCRIPT.value: CopilotCallScriptOutput,
    CopilotKind.PROPOSAL.value: CopilotProposalOutput,
}


class NbaRuleService(TenantScopedService[NbaRule]):
    """Audited create/update/archive for ``crm.nba_rules``."""

    entity_name = "NBA rule"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(NbaRuleRepository(session), NbaRule)


def _engine_actions(
    kind: RecordKind,
    snapshot: dict[str, Any],
    rules: Sequence[nba_rules.RuleDef],
    predicted: Sequence[nba_rules.RecommendedAction],
    logs: dict[str, tuple[str, dt.datetime]],
    now: dt.datetime,
) -> list[NbaActionResponse]:
    """Run the engine and drop what a rep already executed or dismissed recently."""
    responses: list[NbaActionResponse] = []
    for action in nba_rules.evaluate(kind, snapshot, rules, extra=predicted):
        logged = logs.get(action.action_code)
        if logged is not None:
            outcome, at = logged
            cooldown = (
                max(action.cooldown_days, DISMISS_COOLDOWN_DAYS)
                if outcome == NbaActionOutcome.DISMISSED.value
                else action.cooldown_days
            )
            if cooldown > 0 and at >= now - dt.timedelta(days=cooldown):
                continue
        responses.append(
            NbaActionResponse(
                action_code=action.action_code,
                category=action.category,
                label=action.label,
                execution=action.execution,
                copilot=action.copilot,
                priority=action.priority,
                level=action.level,
                reasons=list(action.reasons),
                rule_keys=list(action.rule_keys),
                signals=[
                    NbaSignalEvidence(key=item.key, label=item.label, value=item.value)
                    for item in action.signals
                ],
                timing=action.timing,
                due_at=(
                    now + dt.timedelta(hours=action.due_in_hours)
                    if action.due_in_hours is not None
                    else None
                ),
                confidence=action.confidence,
            )
        )
    return responses


def _public_signals(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Catalog signals only — never custom-field copies or free text."""
    return {
        key: value
        for key, value in snapshot.items()
        if key in SIGNALS and key != "recent_interaction_text"
    }


def _kinds(applies_to: str) -> frozenset[RecordKind]:
    if applies_to == "BOTH":
        return frozenset({RecordKind.OPPORTUNITY, RecordKind.LEAD})
    return frozenset({RecordKind(applies_to)})


def _applies_to_value(kinds: frozenset[RecordKind]) -> str:
    return "BOTH" if len(kinds) > 1 else next(iter(kinds)).value


def _validate_rule(
    applies_to: str,
    logic: str,
    conditions: Sequence[dict[str, Any]],
    action_code: str,
    priority: str,
) -> None:
    try:
        nba_rules.validate_rule(
            applies_to=_kinds(applies_to),
            logic=logic,
            conditions=conditions,
            action_code=action_code,
            priority=priority,
        )
    except nba_rules.RuleValidationError as error:
        raise ValidationFailedError(str(error)) from error


def _custom_rule_def(row: NbaRule) -> nba_rules.RuleDef:
    return nba_rules.RuleDef(
        key=f"custom.{row.id}",
        name=row.name,
        applies_to=_kinds(row.applies_to),
        conditions=tuple(row.conditions),
        action_code=row.action_code,
        priority=row.priority,
        reason=row.reason,
        logic=row.condition_logic,
        timing=row.timing,
        due_in_hours=row.due_in_hours,
        cooldown_days=row.cooldown_days,
        is_active=row.is_active,
        source="CUSTOM",
        rule_id=row.id,
        position=row.position,
    )


def _rule_action(action_code: str) -> tuple[str, str]:
    action = ACTIONS.get(action_code)
    return (action.label, action.category.value) if action else (action_code, "")


def _builtin_rule_response(rule: nba_rules.RuleDef, override: NbaRule | None) -> NbaRuleResponse:
    conditions: list[Any] = (
        list(override.conditions)
        if override and override.conditions
        else [dict(condition) for condition in rule.conditions]
    )
    label, category = _rule_action(rule.action_code)
    return NbaRuleResponse(
        key=rule.key,
        id=override.id if override else None,
        source="BUILTIN",
        name=rule.name,
        description=None,
        applies_to=_applies_to_value(rule.applies_to),
        logic=(override.condition_logic if override else rule.logic),
        conditions=[NbaCondition.model_validate(dict(condition)) for condition in conditions],
        action_code=rule.action_code,
        action_label=label,
        category=category,
        priority=(override.priority if override else rule.priority),
        reason=rule.reason,
        timing=rule.timing,
        due_in_hours=rule.due_in_hours,
        cooldown_days=override.cooldown_days if override else rule.cooldown_days,
        is_active=override.is_active if override else rule.is_active,
        is_overridden=override is not None,
    )


def _custom_rule_response(row: NbaRule) -> NbaRuleResponse:
    label, category = _rule_action(row.action_code)
    return NbaRuleResponse(
        key=f"custom.{row.id}",
        id=row.id,
        source="CUSTOM",
        name=row.name,
        description=row.description,
        applies_to=row.applies_to,
        logic=row.condition_logic,
        conditions=[NbaCondition.model_validate(dict(condition)) for condition in row.conditions],
        action_code=row.action_code,
        action_label=label,
        category=category,
        priority=row.priority,
        reason=row.reason,
        timing=row.timing,
        due_in_hours=row.due_in_hours,
        cooldown_days=row.cooldown_days,
        is_active=row.is_active,
        is_overridden=False,
    )


def _to_insight_item(row: insights_queries.InsightRow) -> InsightItem:
    return InsightItem(
        kind=row.kind,
        severity=row.severity,
        title=row.title,
        detail=row.detail,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        entity_label=row.entity_label,
    )


__all__ = ["AiInsightsService"]
