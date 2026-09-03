"""Use cases for the AI gateway — the module's public interface.

Two services, deliberately separate:

:class:`AiPromptService`
    The versioned prompt library. Administrators publish wording; features ask
    for the version in force. Publishing appends, so §12 holds by construction:
    "changing the prompt affects new research, not old".

:class:`AiGatewayService`
    One model turn. Owns provider construction, per-user rate limiting and the
    audit record, so no feature has to remember any of the three.

Neither knows what a company is. Composing a *research* prompt is the CRM
feature's job — Platform must not import a product
(ARCHITECTURE-BOUNDARIES.md rule 1), and "what is worth researching about a
business" is product vocabulary, not platform vocabulary.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import structlog
from fastapi import status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.platform.ai.models import MARKET_INSIGHTS_PROMPT_KEY, AiPromptVersion
from app.platform.ai.provider import (
    AiNotConfiguredError,
    AnthropicResearchProvider,
    GeminiResearchProvider,
    ResearchProvider,
    ResearchResult,
)
from app.platform.ai.repository import AiPromptRepository
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import audit_for_session

logger = structlog.get_logger(__name__)

#: The wording every organization starts from, published as version 1 the
#: first time a feature asks for a prompt that has never been configured.
#:
#: Seeded into a real row rather than used as a floating default, so that a
#: research session can always point at an immutable version. A constant read
#: at request time would change under existing sessions on the next deploy,
#: which is exactly the drift §12 forbids.
#:
#: It says what to research and how to present it, and nothing about which
#: company — the feature supplies that. An administrator is free to replace it
#: wholesale; the section list below is a starting point, not a contract the
#: code depends on.
DEFAULT_MARKET_INSIGHTS_PROMPT = """\
Act as a senior market research analyst, corporate strategy consultant and B2B \
account intelligence specialist. Produce a concise, executive-ready Market \
Research Report on this company — the document a sales or delivery leader reads \
in the ten minutes before a CXO meeting.

Aim at two to three printed pages. Insight-dense, never exhaustive.

# Sourcing

Work only from credible public sources: the company's own website, annual \
reports and investor presentations, stock-exchange filings, published financial \
results, press releases, reputable business press, and leadership profiles \
where they are relevant.

- Hyperlink every important claim inline, as [label](url), to the page it came from.
- Where something is not available publicly, write "Not publicly disclosed" \
rather than estimating it.
- Keep confirmed fact and your own inference visibly apart, and label inference \
as inference.

# Structure

Write the sections below as level-two Markdown headings, in this order. Omit a \
heading rather than filling it with generalities when you have nothing reliable \
to say under it.

## Executive Summary
Five to seven lines: what the company is, how it is performing, where it is \
heading, and the single most useful thing to know before meeting them.

## Key Insights
Four to six bullets, each a strategic signal a seller could act on.

## Company Snapshot
Overview, headquarters, year founded, industry, scale of operations, key \
brands, subsidiaries and group companies, and where it sits in its market. Put \
the factual fields in a table.

## Leadership
Chairman, managing director, CEO and the executives who matter, with promoter \
or board context where it is public, and any stated leadership priorities.

## Revenue, Financials & Growth
Latest revenue, EBITDA, PAT and margins where published; the three-to-five year \
trend as a table; export or international contribution; capex and capacity \
plans; and the financial strengths and concerns behind the numbers.

## Business Units, Products & Markets
Segments, product categories, manufacturing or delivery capability, domestic \
versus international mix, geographies served, and customer types.

## Strategic Priorities
What this company is visibly trying to do — growth, geographic expansion, \
premiumisation and branding, sustainability, modernisation, supply-chain \
efficiency, customer diversification, product innovation, data-led decision \
making. Ground each one in something they have said or done, and cite it.

## Competition
Domestic and global competitors, in a table comparing scale, positioning and \
market focus.

## Compliance, Regulatory & Risk
The regulatory and compliance environment this company operates under, and \
where it is under pressure. Cover whichever apply: listing and disclosure \
obligations, tax and customs regimes, trade policy, tariffs and anti-dumping \
action, labour and factory law, environmental consents and emissions rules, \
product safety and certification, data protection, ESG and supply-chain \
due-diligence reporting, and any live litigation, penalty, audit qualification \
or regulatory notice. For each, state the specific challenge it creates for \
this business rather than restating the rule.

## Recent News — Last 12 Months
Dated items only: results, expansion, acquisitions and partnerships, leadership \
changes, ESG initiatives, and legal, regulatory or market events.

## Digital Transformation & Technology Initiatives
Anything publicly stated about ERP, cloud, analytics, supply-chain \
digitisation, automation, AI or ML, e-commerce, traceability platforms, \
cybersecurity or infrastructure modernisation. Where nothing is on the record, \
say so plainly and mark what follows "Potential Opportunity Areas" — never as \
confirmed initiatives.

## Technology Partners
Named technology, consulting, platform or implementation partners. If none are \
on the public record, write "No major technology partners found in the public \
domain."

## Potential AI / Digital Opportunity Areas
Six to eight practical opportunities fitted to how this company actually \
operates — demand forecasting, customer and retail analytics, trend \
intelligence, supply-chain visibility, production planning, computer-vision \
quality inspection, ESG reporting automation, sales and operations knowledge \
management, generative-AI proposal and catalogue work, and the like. For each: \
the opportunity, the business problem it solves, and why it fits this company. \
This whole section is inference — say so at the top of it.

## Sources
Every source used, as a list of linked titles with publisher and date.

# Style

- Lead with the conclusion, then the evidence for it.
- Prefer named customers, dated events and figures to adjectives.
- Bullets and tables over prose. No paragraph longer than four lines.
- Tables are GitHub-style Markdown pipe tables, header row included.
- Attribute anything time-sensitive and give the date it was true.
- Where sources disagree, give both readings and say which is which.
- Never invent a figure, a customer, a person, an event or a URL to fill a gap.
"""


class AiRateLimitedError(AppError):
    """The caller has started too many research turns in the last hour."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "ai_rate_limited"
    message = "You have run a lot of AI research recently. Please try again later."


class PromptEmptyError(AppError):
    """A prompt cannot be published empty."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "prompt_empty"
    message = "The prompt cannot be empty."


class AiPromptService:
    """The versioned prompt library (§11, §12)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = AiPromptRepository(session)

    async def ensure_active(
        self,
        *,
        organization_id: uuid.UUID,
        key: str,
        default: str,
        actor_id: uuid.UUID | None = None,
    ) -> AiPromptVersion:
        """The version in force for ``key``, publishing the default if none is.

        Seeding on first use rather than in a migration is deliberate: a
        migration that inserted a row per organization would need re-running
        for every tenant created afterwards, and the default would still have
        to live in code for the new-tenant path. One mechanism, used by
        everyone, is easier to reason about — and it means the Settings screen
        opens on a real, editable version rather than on an empty state.
        """
        active = await self._repository.get_active(organization_id, key)
        if active is not None:
            return active
        return await self.publish(
            organization_id=organization_id,
            key=key,
            prompt=default,
            actor_id=actor_id,
            change_note="Initial default",
        )

    async def publish(
        self,
        *,
        organization_id: uuid.UUID,
        key: str,
        prompt: str,
        actor_id: uuid.UUID | None,
        change_note: str | None = None,
    ) -> AiPromptVersion:
        """Append a new version and make it the active one.

        Existing versions are untouched, so research already performed keeps
        resolving to the wording it ran under.
        """
        text = prompt.strip()
        if not text:
            raise PromptEmptyError

        number = await self._repository.next_version_number(organization_id, key)
        await self._repository.deactivate_all(organization_id, key)
        version = await self._repository.add(
            AiPromptVersion(
                organization_id=organization_id,
                key=key,
                version=number,
                prompt=text,
                change_note=(change_note or None),
                is_active=True,
                created_by_id=actor_id,
            )
        )

        await audit_for_session(self._session).record(
            organization_id=organization_id,
            action=AuditAction.UPDATED,
            module="ai",
            entity_type="AI_PROMPT_VERSION",
            entity_id=version.id,
            entity_label=f"{key} v{number}",
            actor_id=actor_id,
            # The prompt body itself is not copied into the trail: it is free
            # text an administrator wrote, the same reason CRM note bodies are
            # summarised rather than stored (see TenantScopedService).
            details={"key": key, "version": number, "length": len(text)},
        )
        logger.info("ai_prompt_published", key=key, version=number)
        return version

    async def list_versions(
        self, organization_id: uuid.UUID, key: str
    ) -> Sequence[AiPromptVersion]:
        return await self._repository.list_versions(organization_id, key)

    async def find_version(
        self, version_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AiPromptVersion | None:
        """One version by id, or ``None``.

        The public way for a feature to resolve a *pinned* version, so nothing
        outside this module has to reach into the repository. Returns ``None``
        rather than raising because a missing pin is a recoverable state — a
        session that predates pinning still has to answer follow-ups.
        """
        return await self._repository.get(version_id, organization_id)

    async def get_or_404(
        self, version_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AiPromptVersion:
        version = await self.find_version(version_id, organization_id)
        if version is None:
            raise NotFoundError("Prompt version not found.")
        return version

    async def market_insights_prompt(
        self, organization_id: uuid.UUID, *, actor_id: uuid.UUID | None = None
    ) -> AiPromptVersion:
        """The prompt Market Insights research runs under right now."""
        return await self.ensure_active(
            organization_id=organization_id,
            key=MARKET_INSIGHTS_PROMPT_KEY,
            default=DEFAULT_MARKET_INSIGHTS_PROMPT,
            actor_id=actor_id,
        )


class AiGatewayService:
    """Runs one model turn on behalf of a product feature."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        redis: Redis | None = None,
        provider: ResearchProvider | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._redis = redis
        #: Injectable so tests exercise the service without a network call.
        #: Built lazily otherwise, because constructing it asserts a key exists
        #: and most requests through this session never call a model.
        self._provider = provider

    @property
    def configured(self) -> bool:
        return self._settings.ai_configured

    def _require_provider(self) -> ResearchProvider:
        """The provider ``ai_provider`` selects, built on first use.

        The only place in the codebase that names a vendor. Both constructors
        re-check the credential, so a misconfigured deployment fails here with
        ``ai_not_configured`` rather than at the model call.
        """
        if self._provider is None:
            if not self._settings.ai_configured:
                raise AiNotConfiguredError
            if self._settings.ai_provider == "gemini":
                self._provider = GeminiResearchProvider(self._settings)
            else:
                self._provider = AnthropicResearchProvider(self._settings)
        return self._provider

    async def enforce_rate_limit(self, *, user_id: uuid.UUID) -> None:
        """Cap research turns per user per hour.

        Fails **open** when Redis is unreachable. The limit protects spend and
        latency; it is not an authorization control, and taking the feature
        offline because a cache is down would be the worse failure. Every
        authorization decision on this path is made in PostgreSQL.
        """
        if self._redis is None:
            return
        limit = self._settings.ai_rate_limit_per_hour
        key = f"ai:rate:{user_id}"
        try:
            used = await self._redis.incr(key)
            if used == 1:
                await self._redis.expire(key, 3600)
        except Exception:
            logger.warning("ai_rate_limit_unavailable", exc_info=True)
            return
        if used > limit:
            logger.info("ai_rate_limited", user_id=str(user_id), used=used)
            raise AiRateLimitedError

    async def run_turn(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        system: str,
        messages: Sequence[dict[str, Any]],
        feature: str,
        web_search: bool = True,
    ) -> ResearchResult:
        """Call the model and record that it was called.

        The audit entry names the feature, the model and how much was spent —
        never the prompt or the answer. Both are free text a user wrote or a
        model produced, and the audit trail is read by administrators who have
        no business seeing the contents of somebody's research session.
        """
        provider = self._require_provider()
        result = await provider.run(system=system, messages=messages, web_search=web_search)

        await audit_for_session(self._session).record(
            organization_id=organization_id,
            action="AI_TURN_COMPLETED",
            module="ai",
            entity_type="AI_TURN",
            actor_id=actor_id,
            details={
                "feature": feature,
                "model": result.model,
                "searches": result.search_count,
                "sources": len(result.sources),
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "truncated": result.truncated,
            },
        )
        return result


__all__ = [
    "DEFAULT_MARKET_INSIGHTS_PROMPT",
    "AiGatewayService",
    "AiPromptService",
    "AiRateLimitedError",
    "PromptEmptyError",
]
