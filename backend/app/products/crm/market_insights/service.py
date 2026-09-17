"""Market Insights business rules — the module's public interface.

What happens when someone researches a company:

1. The prompt version in force is resolved and later **pinned to the session**.
   This is the whole of §12: a subsequent edit publishes a new version and
   cannot reach backwards into research already performed.
2. CRM context is built, permission-filtered per module, if the subject is an
   account the caller can read (§7).
3. The gateway runs the turn.
4. **Only then** is anything written: the session, the request and report as
   two messages, and one row per source the search tool actually returned.

Step 4 is deliberately last. ``get_db_session`` rolls the whole request
transaction back on an exception, so the intuitive shape — insert a
``RESEARCHING`` row, call the model, update it to ``READY`` or ``FAILED`` —
would roll the failure row back along with the failure, and History would show
nothing at all. A failed attempt is instead written through an independent
session (:meth:`MarketInsightService._record_failed_start`), the same technique
``AuditService.record_out_of_band`` uses and for the same reason (§15).

One consequence worth naming: because a row appears only after a turn ends,
there is no persisted "in progress" state and no way for a session to be found
mid-flight. Progress is a client-side concern for the life of the request.

Follow-up questions replay the stored conversation, so the model keeps the
subject without the user restating it (§6).

Everything inherits :class:`~app.products.crm.shared.service.TenantScopedService`,
which means creates, updates and deletes are audited in the same transaction
as the change, with no per-endpoint audit call to forget.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

import structlog
from fastapi import status
from sqlalchemy import ColumnElement, func, or_, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import apply_tenant_context
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.tenant import TenantContext
from app.platform.ai.provider import ResearchResult
from app.platform.ai.service import AiGatewayService, AiPromptService
from app.platform.auth.dependencies import Principal
from app.products.crm.accounts.models import Account
from app.products.crm.accounts.service import AccountService
from app.products.crm.market_insights.context import CrmContext, build_crm_context
from app.products.crm.market_insights.models import (
    MarketInsightMessage,
    MarketInsightSession,
    MarketInsightSource,
    MessageRole,
    ResearchStatus,
)
from app.products.crm.market_insights.prompts import (
    build_system_prompt,
    default_title,
    opening_request,
)
from app.products.crm.market_insights.repository import (
    MarketInsightConversationRepository,
)
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.shared.visibility import RecordVisibility

logger = structlog.get_logger(__name__)

#: How many earlier turns are replayed to the model on a follow-up. The
#: opening report is always included (it is the research), plus the most
#: recent exchanges. Old middle turns are dropped rather than summarised: a
#: summary of a summary is where a report starts drifting from its sources.
MAX_REPLAYED_TURNS = 12

class SessionAlreadyLinkedError(ConflictError):
    """The session is already associated with a CRM account."""

    code = "session_already_linked"
    message = "This research is already linked to a CRM account."


class ResearchNotReadyError(AppError):
    """A follow-up was asked before the opening report completed."""

    status_code = status.HTTP_409_CONFLICT
    code = "research_not_ready"
    message = "The initial research has not finished yet."


class MarketInsightService(TenantScopedService[MarketInsightSession]):
    """Research sessions, their conversations and their evidence."""

    entity_name = "Market research"

    def __init__(
        self,
        session: AsyncSession,
        *,
        gateway: AiGatewayService,
        prompts: AiPromptService,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        super().__init__(
            TenantScopedRepository(session, MarketInsightSession), MarketInsightSession
        )
        self._session = session
        self._conversation = MarketInsightConversationRepository(session)
        self._gateway = gateway
        self._prompts = prompts
        self._accounts = AccountService(session)
        #: Used only to record a *failed* turn, which by definition happens on
        #: a path that is about to raise and take the request transaction with
        #: it. Same technique as ``AuditService.record_out_of_band``.
        self._session_factory = session_factory

    def audit_label(self, entity: MarketInsightSession) -> str | None:
        """Name the company, not the (renameable) title.

        ``_LABEL_ATTRIBUTES`` would pick ``title`` first. The company is the
        stable identity of the session and the useful thing to read in a trail
        months later.
        """
        return entity.company_name

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        account_id: uuid.UUID | None = None,
        status_filter: ResearchStatus | None = None,
    ) -> list[ColumnElement[bool]]:
        """Translate History's query parameters into SQL predicates (§10)."""
        filters: list[ColumnElement[bool]] = []
        if search:
            term = f"%{search.strip().lower()}%"
            # Matched against both, because a user searches history by whatever
            # they remember — the company or what they renamed the session to.
            filters.append(
                or_(
                    func.lower(MarketInsightSession.company_name).like(term),
                    func.lower(MarketInsightSession.title).like(term),
                )
            )
        if account_id is not None:
            filters.append(MarketInsightSession.account_id == account_id)
        if status_filter is not None:
            filters.append(MarketInsightSession.status == status_filter)
        return filters

    async def list_sessions(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
        visibility: RecordVisibility | None = None,
    ) -> tuple[Sequence[MarketInsightSession], int]:
        return await self.list(
            organization_id, params=params, filters=filters, visibility=visibility
        )

    async def messages(self, session: MarketInsightSession) -> Sequence[MarketInsightMessage]:
        return await self._conversation.messages(session.id, session.organization_id)

    async def sources(self, session: MarketInsightSession) -> Sequence[MarketInsightSource]:
        return await self._conversation.sources(session.id, session.organization_id)

    # --- Commands ----------------------------------------------------------

    async def start_research(
        self,
        *,
        principal: Principal,
        company_name: str,
        account_id: uuid.UUID | None,
    ) -> MarketInsightSession:
        """Create a session and produce its opening Market Intelligence Report.

        Args:
            principal: the caller, carrying the resolved permission snapshot.
            company_name: the subject as typed.
            account_id: the CRM account, when the user picked one. Resolved
                through ``AccountService`` so an id from another tenant — or
                one the caller may not see — is a 404, not a context leak.

        Raises:
            NotFoundError: ``account_id`` names no account the caller can read.
            AiNotConfiguredError: no provider credential is configured.
            AiRateLimitedError: the caller has run too much research this hour.
        """
        await self._gateway.enforce_rate_limit(user_id=principal.user_id)
        account = await self._resolve_account(principal, account_id)

        # Pinned before the model runs, so the version recorded is the one the
        # research actually used even if an administrator publishes mid-flight.
        prompt = await self._prompts.market_insights_prompt(
            principal.organization_id, actor_id=principal.user_id
        )

        context = await self._context_for(account, principal)
        used_crm_context = context is not None and not context.is_empty
        system = build_system_prompt(
            configured_prompt=prompt.prompt,
            company_name=company_name,
            is_crm_account=account is not None,
            crm_context=context.text if used_crm_context and context else None,
        )
        request = opening_request(company_name)

        # The model runs *before* anything is written.
        #
        # The obvious shape — insert a RESEARCHING row, call the model, update
        # it — cannot work here: ``get_db_session`` rolls the whole request
        # transaction back on an exception, so the row describing the failure
        # would be rolled back along with the failure. Deferring the write and
        # recording a failure out-of-band is what makes a failed attempt
        # actually survive into History (§15).
        try:
            result = await self._gateway.run_turn(
                organization_id=principal.organization_id,
                actor_id=principal.user_id,
                system=system,
                messages=[{"role": "user", "content": request}],
                feature="market_insights",
            )
        except AppError as error:
            await self._record_failed_start(
                principal=principal,
                company_name=company_name,
                account_id=account.id if account else None,
                prompt_version_id=prompt.id,
                prompt_version=prompt.version,
                used_crm_context=used_crm_context,
                error_code=error.code,
            )
            raise

        now = dt.datetime.now(dt.UTC)
        session = await self.create(
            organization_id=principal.organization_id,
            actor_id=principal.user_id,
            values={
                "company_name": company_name,
                "title": default_title(company_name),
                "account_id": account.id if account else None,
                "owner_id": principal.user_id,
                "status": ResearchStatus.READY,
                "prompt_version_id": prompt.id,
                "prompt_version": prompt.version,
                "used_crm_context": used_crm_context,
                "model": result.model or None,
                "last_activity_at": now,
            },
        )

        # The request is stored as a turn of its own so History shows what was
        # asked, and so a follow-up replays a conversation that starts with a
        # user turn like any other.
        await self._append_message(
            session,
            role=MessageRole.USER,
            content=request,
            actor_id=principal.user_id,
        )
        message = await self._append_message(
            session,
            role=MessageRole.ASSISTANT,
            content=result.text,
            actor_id=principal.user_id,
            truncated=result.truncated,
            search_count=result.search_count,
        )
        await self._store_sources(session, message=message, result=result)
        return session

    async def ask(
        self,
        *,
        session: MarketInsightSession,
        principal: Principal,
        question: str,
    ) -> MarketInsightSession:
        """Answer a follow-up question inside an existing session (§6).

        The whole conversation is replayed, so the model keeps the company in
        context and the user never restates it.

        Raises:
            ResearchNotReadyError: the opening report never completed, so
                there is nothing to follow up on.
            AiRateLimitedError: the caller has run too much research this hour.
        """
        await self._gateway.enforce_rate_limit(user_id=principal.user_id)
        history = await self._conversation.messages(session.id, session.organization_id)
        if not any(message.role is MessageRole.ASSISTANT for message in history):
            raise ResearchNotReadyError

        account = await self._resolve_account(principal, session.account_id)
        prompt = await self._pinned_prompt(session, principal)
        context = await self._context_for(account, principal)
        system = build_system_prompt(
            configured_prompt=prompt,
            company_name=session.company_name,
            is_crm_account=session.account_id is not None,
            crm_context=None if context is None or context.is_empty else context.text,
            follow_up=True,
        )

        turns = _replay(history)
        turns.append({"role": "user", "content": question})

        try:
            result = await self._gateway.run_turn(
                organization_id=session.organization_id,
                actor_id=principal.user_id,
                system=system,
                messages=turns,
                feature="market_insights",
            )
        except AppError as error:
            # The question rolls back with the transaction, but the session's
            # failure state is written independently so the user sees why
            # nothing came back and can retry (§15).
            await self._mark_failed(session, error_code=error.code)
            raise

        await self._append_message(
            session, role=MessageRole.USER, content=question, actor_id=principal.user_id
        )
        message = await self._append_message(
            session,
            role=MessageRole.ASSISTANT,
            content=result.text,
            actor_id=principal.user_id,
            truncated=result.truncated,
            search_count=result.search_count,
        )
        await self._store_sources(session, message=message, result=result)

        session.status = ResearchStatus.READY
        session.error_code = None
        session.model = result.model or session.model
        session.last_activity_at = dt.datetime.now(dt.UTC)
        await self._repository.flush()
        return session

    async def rename(
        self, session: MarketInsightSession, *, title: str, actor_id: uuid.UUID | None
    ) -> MarketInsightSession:
        """Retitle a session (§10). The company it concerns is immutable."""
        return await self.update(session, actor_id=actor_id, values={"title": title})

    async def archive(
        self, session: MarketInsightSession, *, actor_id: uuid.UUID | None
    ) -> MarketInsightSession:
        """Archive a session, following the application's soft-delete convention."""
        return await self.soft_delete(session, actor_id=actor_id)

    async def link_account(
        self,
        session: MarketInsightSession,
        *,
        principal: Principal,
        account_id: uuid.UUID,
    ) -> MarketInsightSession:
        """Associate research with a CRM account, preserving it (§8).

        Called after "Add to CRM" has created the account through the normal
        account flow — including its duplicate-name warning. This method does
        not create anything: keeping creation in ``AccountService`` is what
        stops Market Insights becoming a second, laxer way to make accounts.

        Raises:
            SessionAlreadyLinkedError: the session already names an account.
            NotFoundError: the account is not one the caller can read.
        """
        if session.account_id is not None:
            raise SessionAlreadyLinkedError
        account = await self._resolve_account(principal, account_id)
        if account is None:  # pragma: no cover - id is required by the schema
            raise NotFoundError("Account not found.")
        return await self.update(
            session, actor_id=principal.user_id, values={"account_id": account.id}
        )

    # --- Internals ---------------------------------------------------------

    async def _resolve_account(
        self, principal: Principal, account_id: uuid.UUID | None
    ) -> Account | None:
        """Fetch an account the caller may read, or ``None`` when unlinked.

        Routed through ``AccountService.get_or_404`` with the caller's own
        record visibility, so Market Insights can never widen access to an
        account the accounts screen would hide.
        """
        if account_id is None:
            return None
        return await self._accounts.get_or_404(
            account_id,
            principal.organization_id,
            visibility=RecordVisibility.for_module(principal, "accounts"),
        )

    async def _context_for(
        self, account: Account | None, principal: Principal
    ) -> CrmContext | None:
        if account is None:
            return None
        return await build_crm_context(self._session, account=account, principal=principal)

    async def _pinned_prompt(
        self, session: MarketInsightSession, principal: Principal
    ) -> str:
        """The wording this session runs under — the pinned version (§12).

        Falls back to whatever is active only when the pinned row cannot be
        found, which means it predates pinning or was purged. Continuing under
        current wording beats refusing to answer a follow-up.
        """
        if session.prompt_version_id is not None:
            version = await self._prompts.find_version(
                session.prompt_version_id, session.organization_id
            )
            if version is not None:
                return version.prompt
            logger.info("market_insights_prompt_version_missing", session_id=str(session.id))
        active = await self._prompts.market_insights_prompt(
            session.organization_id, actor_id=principal.user_id
        )
        return active.prompt

    async def _record_failed_start(
        self,
        *,
        principal: Principal,
        company_name: str,
        account_id: uuid.UUID | None,
        prompt_version_id: uuid.UUID,
        prompt_version: int,
        used_crm_context: bool,
        error_code: str,
    ) -> None:
        """Write a ``FAILED`` session through an independent transaction.

        The caller is about to re-raise, which rolls the request transaction
        back. Without this the attempt would vanish and History would suggest
        the user never tried — the specific silence §15 asks to avoid.

        Never raises. A bookkeeping failure here must not replace the provider
        error the caller is about to receive; it is logged instead.
        """
        if self._session_factory is None:
            logger.warning(
                "market_insights_failure_not_recorded",
                reason="no independent session factory was supplied",
            )
            return

        now = dt.datetime.now(dt.UTC)
        try:
            async with self._session_factory() as independent:
                # The independent session carries no tenant context of its own,
                # and RLS matches zero rows without one — the insert would be
                # refused by the table's WITH CHECK clause.
                await apply_tenant_context(
                    independent, TenantContext(organization_id=principal.organization_id)
                )
                independent.add(
                    MarketInsightSession(
                        organization_id=principal.organization_id,
                        company_name=company_name,
                        title=default_title(company_name),
                        account_id=account_id,
                        owner_id=principal.user_id,
                        status=ResearchStatus.FAILED,
                        error_code=error_code,
                        prompt_version_id=prompt_version_id,
                        prompt_version=prompt_version,
                        used_crm_context=used_crm_context,
                        last_activity_at=now,
                        created_by_id=principal.user_id,
                        updated_by_id=principal.user_id,
                    )
                )
                await independent.commit()
        except Exception as error:
            logger.error(
                "market_insights_failure_write_failed",
                company=company_name,
                error=str(error),
            )

    async def _mark_failed(
        self, session: MarketInsightSession, *, error_code: str
    ) -> None:
        """Flag an existing session as failed, outside the request transaction.

        Same reasoning as :meth:`_record_failed_start`: the row already exists
        and is committed, but the *update* would be rolled back with the
        request. Never raises.
        """
        if self._session_factory is None:
            logger.warning(
                "market_insights_failure_not_recorded",
                reason="no independent session factory was supplied",
            )
            return

        try:
            async with self._session_factory() as independent:
                await apply_tenant_context(
                    independent, TenantContext(organization_id=session.organization_id)
                )
                await independent.execute(
                    update(MarketInsightSession)
                    .where(
                        MarketInsightSession.id == session.id,
                        MarketInsightSession.organization_id == session.organization_id,
                    )
                    .values(
                        status=ResearchStatus.FAILED,
                        error_code=error_code,
                        last_activity_at=dt.datetime.now(dt.UTC),
                    )
                )
                await independent.commit()
        except Exception as error:
            logger.error(
                "market_insights_failure_write_failed",
                session_id=str(session.id),
                error=str(error),
            )

    async def _append_message(
        self,
        session: MarketInsightSession,
        *,
        role: MessageRole,
        content: str,
        actor_id: uuid.UUID | None,
        truncated: bool = False,
        search_count: int = 0,
    ) -> MarketInsightMessage:
        sequence = await self._conversation.next_sequence(
            session.id, session.organization_id
        )
        message = MarketInsightMessage(
            organization_id=session.organization_id,
            session_id=session.id,
            sequence=sequence,
            role=role,
            content=content,
            truncated=truncated,
            search_count=search_count,
            author_id=actor_id,
        )
        self._conversation.add(message)
        await self._conversation.flush()
        return message

    async def _store_sources(
        self,
        session: MarketInsightSession,
        *,
        message: MarketInsightMessage,
        result: ResearchResult,
    ) -> None:
        """Persist the pages this turn actually retrieved.

        Deduplicated against the session's existing URLs: a follow-up commonly
        re-reads a page the opening report already cited, and storing it again
        would grow the evidence panel without adding evidence.
        """
        if not result.sources:
            return
        seen = await self._conversation.known_urls(session.id, session.organization_id)
        position = 0
        for source in result.sources:
            if source.url in seen:
                continue
            seen.add(source.url)
            self._conversation.add(
                MarketInsightSource(
                    organization_id=session.organization_id,
                    session_id=session.id,
                    message_id=message.id,
                    title=source.title[:512],
                    url=source.url[:2048],
                    page_age=source.page_age,
                    cited=source.cited,
                    position=position,
                    retrieved_at=result.performed_at,
                )
            )
            position += 1
        await self._conversation.flush()


def _replay(history: Sequence[MarketInsightMessage]) -> list[dict[str, Any]]:
    """Turn stored messages into Messages API turns.

    The opening report is always kept — it *is* the research, and dropping it
    would leave a follow-up answering from nothing. Beyond that the most recent
    turns are kept, oldest middle turns dropped.
    """
    turns = [
        {
            "role": "user" if message.role is MessageRole.USER else "assistant",
            "content": message.content,
        }
        for message in history
    ]
    if len(turns) <= MAX_REPLAYED_TURNS:
        return turns
    return turns[:2] + turns[-(MAX_REPLAYED_TURNS - 2) :]


__all__ = [
    "MAX_REPLAYED_TURNS",
    "MarketInsightService",
    "ResearchNotReadyError",
    "SessionAlreadyLinkedError",
]
