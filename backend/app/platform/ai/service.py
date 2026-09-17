"""Use cases for the AI gateway — the module's public interface.

Two services, deliberately separate:

:class:`AiPromptService`
    The versioned prompt library. Administrators publish wording; features ask
    for the version in force. Publishing appends, so §12 holds by construction:
    "changing the prompt affects new research, not old".

:class:`AiGatewayService`
    One model turn. Owns provider construction, per-user rate limiting and the
    audit record, so no feature has to remember any of the three.

:class:`AiConnectionService`
    What is known about the connection itself: the cheap status every AI
    screen reads, and the administrator's explicit, real connection test.

None of them knows what a company is. Composing a *research* prompt is the CRM
feature's job — Platform must not import a product
(ARCHITECTURE-BOUNDARIES.md rule 1), and "what is worth researching about a
business" is product vocabulary, not platform vocabulary.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from fastapi import status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AiConfigurationIssue, AiProvider, Settings
from app.core.exceptions import AppError, NotFoundError
from app.platform.ai.models import MARKET_INSIGHTS_PROMPT_KEY, AiPromptVersion
from app.platform.ai.provider import (
    AiAuthenticationError,
    AiConnectionState,
    ConnectionCheck,
    ConnectionCheckProvider,
    ResearchProvider,
    ResearchResult,
    build_provider,
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
#: It says what to research and how to present it. ``{{company_name}}`` and
#: ``{{company_website}}`` are filled per turn by the feature that runs it
#: (Market Insights' ``build_system_prompt``); the stored version keeps the
#: placeholders, so one brief serves every company. An administrator is free to
#: replace it wholesale; the section list below is a starting point, not a
#: contract the code depends on.
#:
#: It asks for a self-contained HTML document rather than Markdown. The report
#: screen, the HTML download and printing all recognise a model-written
#: document and show it as one (``frontend/features/ai/market-insights/
#: html-report.ts``), so nothing downstream assumes Markdown.
#:
#: Editing this text reaches only organizations seeded afterwards. Moving
#: existing organizations still on the untouched default needs a migration
#: carrying both texts, as ``20260903_0100`` and ``20260921_0100`` do.
DEFAULT_MARKET_INSIGHTS_PROMPT = """\
Act as a senior market research analyst, corporate strategy consultant, and B2B account \
intelligence specialist.

Your task is to create a concise, executive-ready **2-3 page Market Research Report** for the \
company provided by the user.

**Company:** {{company_name}}
**Website:** {{company_website}}

## OBJECTIVE

Prepare professional market intelligence that can be used before a CXO / leadership meeting to \
understand the company's:

* Business model and market position
* Financial performance and growth direction
* Leadership and strategic priorities
* Products, customers, geographies, and operations
* Competitive landscape
* Technology and digital maturity
* Compliance, regulatory, ESG, and risk landscape
* Potential opportunities for AI, digital transformation, data, automation, and enterprise \
technology services

Use only credible public sources and clearly distinguish **confirmed facts** from **inferred \
opportunity areas**.

## RESEARCH SOURCES

Prioritize:

* Official company website
* Annual reports
* Investor presentations
* Financial results
* Stock exchange filings
* Regulatory filings
* Official press releases
* Credible business/news publications
* Official leadership profiles / LinkedIn where relevant
* Official subsidiary / group-company websites

Do not make unsupported claims.

If information cannot be verified publicly, write:

**"Not publicly disclosed."**

Every important factual claim should have an appropriate source hyperlink.

---

# 1. COMPANY SNAPSHOT

Cover:

* Brief company overview
* Headquarters
* Year founded
* Industry / sector
* Scale of operations
* Key brands
* Subsidiaries / group companies
* Major manufacturing / operating locations
* Geographic footprint
* Market positioning
* Key business differentiators

---

# 2. LEADERSHIP

Identify publicly available:

* Chairman
* Managing Director
* CEO
* CFO
* CTO / CIO / CDO where applicable
* Other relevant CXO leadership
* Key board members
* Promoter / family-business context where publicly disclosed

Include relevant public leadership statements and strategic priorities where available.

Do not speculate about leadership motives, capability, health, or personal characteristics.

---

# 3. REVENUE, FINANCIALS & GROWTH

Use the latest available financial information.

Include:

* Latest revenue
* EBITDA
* EBITDA margin
* PAT
* PAT margin where available
* Revenue growth
* EBITDA / PAT growth
* 3-5 year financial trend
* Export contribution
* Domestic contribution
* Debt / liquidity indicators where material
* Capacity utilization where available
* Capex
* Capacity expansion
* Acquisitions / investments
* Key financial strengths
* Key publicly disclosed concerns / pressures

Always specify the relevant financial year / reporting period.

Do not compare financial periods without stating the period.

---

# 4. BUSINESS UNITS, PRODUCTS & MARKETS

Identify:

* Main business segments
* Product categories
* Manufacturing capabilities
* Production facilities
* Domestic vs export business
* Key geographies
* Customer segments
* Retail customers
* Global brands / institutional customers where publicly disclosed
* Hospitality / institutional business
* B2B / B2C exposure
* E-commerce / D2C presence where applicable

For textile / home textile companies, specifically evaluate areas such as:

* Bed linen
* Fashion bedding
* Utility bedding
* Institutional bedding
* Towels
* Rugs / carpets
* Home décor
* Other textile categories

Only include categories applicable to the target company.

---

# 5. STRATEGIC PRIORITIES

Identify strategic priorities based on verified public evidence.

Evaluate:

* Revenue growth
* Global expansion
* Geographic diversification
* Customer diversification
* Premiumization
* Branded products
* Product innovation
* Manufacturing modernization
* Capacity expansion
* Supply-chain efficiency
* Sustainability / ESG
* Vertical integration
* Margin improvement
* Operational efficiency
* Digital transformation
* Data-led decision making

Clearly label conclusions derived from public evidence.

---

# 6. COMPETITION

Identify relevant:

### Indian competitors

* Listed companies
* Major private companies
* Relevant specialized players

### Global competitors

* International manufacturers
* Exporters
* Home textile companies
* Relevant branded players

For each important competitor provide a concise comparison covering:

* Scale
* Product focus
* Geographic focus
* Customer focus
* Market positioning

Do not rank companies as "best", "worst", or "winner".

---

# 7. RECENT NEWS — LAST 12 MONTHS

Research the latest 12 months from the report date.

Summarize only material developments such as:

* Financial results
* Expansion
* New manufacturing facilities
* Capex
* Acquisitions
* Partnerships
* New customers / contracts where publicly disclosed
* Leadership changes
* ESG initiatives
* Sustainability developments
* Regulatory developments
* Legal matters
* Market events
* Strategic announcements
* Technology initiatives

For every major news item include:

**Date | Event | Business impact | Source**

Clearly distinguish company announcements from third-party reporting.

---

# 8. DIGITAL TRANSFORMATION & TECHNOLOGY

Search specifically for public evidence relating to:

* ERP
* SAP
* Oracle
* Microsoft
* CRM
* Cloud
* Data platforms
* Business intelligence
* Analytics
* AI / ML
* Manufacturing automation
* Industry 4.0
* IoT
* Computer vision
* Supply-chain digitization
* Warehouse automation
* E-commerce
* Digital customer engagement
* Sustainability technology
* Product traceability
* Cybersecurity
* Infrastructure modernization
* Digital workforce / collaboration platforms

For every confirmed initiative provide:

**Technology / Initiative | Purpose | Evidence | Source**

If no direct evidence exists, do not present an assumption as fact.

Instead create:

### Potential Opportunity Areas

and clearly label them as inferred opportunities.

---

# 9. TECHNOLOGY PARTNERS

Identify publicly mentioned:

* Technology vendors
* ERP partners
* Cloud providers
* Consulting firms
* System integrators
* Analytics providers
* AI partners
* Cybersecurity vendors
* Digital transformation partners

If no major technology partners are publicly identifiable, state:

**"No major technology partners found in public domain."**

Do not infer a partner based only on technology usage.

---

# 10. COMPLIANCE & RELATED INFORMATION

Create a dedicated **Compliance & Related Information** section / tile.

Research publicly available information covering relevant compliance and regulatory areas.

Depending on the company's industry and geography, evaluate:

### Regulatory Compliance

* Applicable industry regulations
* Corporate / Companies Act compliance
* Stock exchange / SEBI requirements for listed companies
* Import / export regulations
* Labour regulations
* Factory / occupational safety requirements
* Environmental regulations
* Data protection / privacy requirements
* Industry-specific regulations

### ESG & Sustainability Compliance

* ESG reporting
* BRSR / sustainability reporting
* Environmental permits
* Carbon emissions
* Energy consumption
* Water usage
* Waste management
* Renewable energy
* Supply-chain sustainability
* Product certifications
* Responsible sourcing
* Worker welfare

### Textile / Manufacturing Certifications

Where applicable, check for:

* OEKO-TEX
* GOTS
* GRS
* Better Cotton
* BCI
* ISO certifications
* WRAP
* SA8000
* SEDEX / SMETA
* FSC
* Other relevant customer / export certifications

Only mention certifications that are publicly verified.

### Compliance Challenges / Risk Areas

Identify **publicly evidenced or structurally relevant challenges**, such as:

* Regulatory complexity across export markets
* ESG data collection
* Supplier compliance
* Product traceability
* Labour compliance
* Environmental reporting
* Audit readiness
* Documentation
* Cross-border regulatory requirements
* Data privacy
* Cybersecurity
* Customer-specific compliance requirements
* Sustainability claims verification

Do NOT claim that the company is non-compliant unless supported by authoritative public evidence.

Use the wording:

**"Potential Compliance Challenge"**

for inferred areas.

For documented regulatory / legal matters, provide:

**Issue | Date | Status | Business relevance | Source**

---

# 11. POTENTIAL AI / DIGITAL OPPORTUNITY AREAS

Based on the company's actual business model, identify **6-8 practical opportunities**.

Prioritize opportunities such as:

1. Demand forecasting
2. Retail / customer analytics
3. AI-led product trend intelligence
4. Supply-chain visibility
5. Production planning optimization
6. Computer-vision quality inspection
7. Predictive maintenance
8. Inventory optimization
9. ESG reporting automation
10. Supplier compliance monitoring
11. Product traceability
12. Knowledge management
13. GenAI sales proposal automation
14. GenAI catalogue / product-description generation
15. Customer-service automation
16. Management dashboards / decision intelligence
17. Compliance document intelligence
18. Contract / policy intelligence

Select only the opportunities that are relevant to the target company's actual operations.

For each opportunity provide:

**Opportunity | Business Problem | AI / Digital Solution | Potential Business Value | Priority \
Rationale**

Do not claim that the company already uses the proposed solution unless publicly verified.

---

# 12. KEY INSIGHTS FOR CXO MEETING

Provide 5-8 concise meeting insights.

Focus on:

* What is changing in the business
* Where growth is coming from
* Major strategic priorities
* Operational pressures
* Technology maturity
* Compliance / ESG considerations
* Data / automation opportunities
* Areas where enterprise technology services may create value

Do not provide an overall company ranking or unsupported recommendation.

---

# 13. EXECUTIVE OPPORTUNITY SUMMARY

Create a compact table:

| Business Area    | Observed Situation | Potential Opportunity | Evidence / Source |
| ---------------- | ------------------ | --------------------- | ----------------- |
| Growth           | ...                | ...                   | ...               |
| Operations       | ...                | ...                   | ...               |
| Supply Chain     | ...                | ...                   | ...               |
| Technology       | ...                | ...                   | ...               |
| Data / Analytics | ...                | ...                   | ...               |
| AI               | ...                | ...                   | ...               |
| Compliance       | ...                | ...                   | ...               |
| ESG              | ...                | ...                   | ...               |

---

# SOURCE QUALITY RULES

Use source hierarchy:

**Tier 1**

* Company website
* Annual reports
* Investor presentations
* Stock exchange filings
* Regulatory filings

**Tier 2**

* Reuters
* Economic Times
* Business Standard
* Mint
* CNBC / CNBC-TV18
* Financial Times
* Other established business publications

**Tier 3**

* LinkedIn / executive profiles
* Industry publications
* Reputable research sources

Avoid:

* SEO content farms
* Unsourced blogs
* Random aggregator websites
* Unverified social media claims

Important claims should preferably be supported by Tier 1 sources.

---

# FACT VS INFERENCE

Every conclusion must fall into one of these categories:

**CONFIRMED FACT**
Directly supported by a credible public source.

**PUBLICLY REPORTED**
Reported by a credible third-party source.

**INFERENCE / POTENTIAL OPPORTUNITY**
Reasonable business opportunity derived from the company's operating model, but not confirmed \
as an existing initiative.

Never present an inference as an existing company initiative.

---

# OUTPUT FORMAT

Generate the final report as a **single polished HTML document**.

Filename:

**<company-name>-market-research.html** (for example, indo-count-market-research.html). The CRM \
applies this name when the report is downloaded.

The HTML must contain embedded CSS and must be self-contained.

Return only the HTML document: start with <!DOCTYPE html> and end with </html>, with no code \
fence and no text before or after it. Use no JavaScript and no external stylesheets, fonts or \
images — the CRM displays the report with scripts disabled.

Design:

* Premium enterprise consulting style
* White background
* Navy / dark-blue headings
* Subtle grey section cards
* One professional accent color
* Compact typography
* Executive Summary box
* Key Insight tiles
* Compliance & Related Information tile
* Tables for financials / competition / opportunities
* Clearly visible source hyperlinks
* Responsive layout
* Print-friendly CSS
* Maximum **2-3 printed pages**
* No unnecessary long paragraphs

Recommended structure:

1. Header
2. Executive Summary
3. Key Insights
4. Company Snapshot
5. Leadership
6. Financials & Growth
7. Business & Markets
8. Strategic Priorities
9. Competition
10. Recent News
11. Technology / Digital Maturity
12. **Compliance & Related Information**
13. AI / Digital Opportunity Areas
14. CXO Meeting Insights
15. Source Links

Use compact cards and tables to fit the report into 2-3 printed pages.

Include:

```html
@media print {
  @page {
    size: A4;
    margin: 10mm;
  }
}
```

Ensure hyperlinks remain clickable in the HTML.

---

# FINAL VALIDATION

Before generating the HTML:

1. Browse the web and verify the latest available information as of today's date.
2. Verify company name, website, leadership, financial figures, and dates.
3. Check the previous 12 months for material news.
4. Search specifically for technology initiatives.
5. Search specifically for compliance / regulatory / ESG information.
6. Separate confirmed facts from inferred opportunities.
7. Remove unsupported claims.
8. Ensure every major factual claim has a source.
9. Ensure source links are clickable.
10. Ensure the report remains concise enough for 2-3 A4 printed pages.
11. Ensure **Compliance & Related Information** appears as a distinct section/tile.
12. Return the completed HTML document only after validation.
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
            self._provider = build_provider(self._settings)
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
        try:
            result = await provider.run(system=system, messages=messages, web_search=web_search)
        except AiAuthenticationError:
            # A real call just proved the key is refused. Recorded so the status
            # every AI screen reads says so, instead of "configured" until an
            # administrator happens to run the connection test.
            await record_connection_verdict(
                self._redis,
                self._settings,
                ConnectionCheck(
                    state=AiConnectionState.AUTHENTICATION_ERROR,
                    error_code="credential_rejected",
                ),
                source="feature_call",
            )
            raise
        # A completed turn is the strongest evidence of a working connection
        # there is — a model answered a real request.
        await record_connection_verdict(
            self._redis,
            self._settings,
            ConnectionCheck(state=AiConnectionState.AVAILABLE, model=result.model or None),
            source="feature_call",
        )

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


# ---------------------------------------------------------------------------
# Connection status and the connection test
# ---------------------------------------------------------------------------

#: How long a verdict from a real call stands before the status falls back to
#: plain ``CONFIGURED``. Long enough that every screen a person opens after a
#: test agrees with it; short enough that "available" cannot outlive a key
#: revoked this morning by more than a quarter of an hour.
CONNECTION_VERDICT_TTL_SECONDS = 15 * 60

CheckSource = Literal["health_check", "feature_call"]


def credential_fingerprint(settings: Settings) -> str:
    """A short, non-reversible tag for the selected credential.

    Part of the verdict's cache key, so replacing the key — the usual fix for
    ``AUTHENTICATION_ERROR`` — makes the old verdict unreachable at once rather
    than after its TTL. A truncated SHA-256 of a random API key reveals nothing
    usable, and it is never logged or returned; it only names a Redis key.
    """
    key = settings.ai_credential
    raw = key.get_secret_value().strip() if key is not None else ""
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _verdict_key(settings: Settings) -> str:
    return (
        f"ai:connection:{settings.ai_provider}:{settings.ai_active_model}:"
        f"{credential_fingerprint(settings)}"
    )


async def record_connection_verdict(
    redis: Redis | None,
    settings: Settings,
    check: ConnectionCheck,
    *,
    source: CheckSource,
) -> None:
    """Remember what a real call found, for every replica's status endpoint.

    Kept in Redis rather than in process memory because a deployment runs more
    than one API process, and an administrator's test on one must be what the
    next request — served by another — reports. Fails open: losing a verdict
    only means the status says ``CONFIGURED`` again, which is true.
    """
    if redis is None or not settings.ai_configured:
        return
    payload = {
        "state": check.state.value,
        "model": check.model,
        "latency_ms": check.latency_ms,
        "error_code": check.error_code,
        "checked_at": check.checked_at.isoformat(),
        "source": source,
    }
    try:
        await redis.set(
            _verdict_key(settings), json.dumps(payload), ex=CONNECTION_VERDICT_TTL_SECONDS
        )
    except Exception:
        logger.warning("ai_connection_verdict_unavailable", operation="write", exc_info=True)


@dataclass(frozen=True, slots=True)
class ConnectionStatus:
    """Everything the status endpoint reports. Holds no credential."""

    configured: bool
    provider: AiProvider
    model: str
    state: AiConnectionState
    issue: AiConfigurationIssue | None = None
    checked_at: dt.datetime | None = None
    check_source: CheckSource | None = None
    latency_ms: int | None = None
    error_code: str | None = None


class AiConnectionService:
    """The AI connection's status, and the administrator's real test of it."""

    def __init__(
        self,
        *,
        settings: Settings,
        redis: Redis | None,
        session: AsyncSession | None = None,
        provider: ConnectionCheckProvider | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis
        self._session = session
        #: Injectable so tests exercise the check without a network call.
        self._provider = provider

    async def status(self) -> ConnectionStatus:
        """What is known right now, without calling a model.

        Cheap by design — every AI screen reads it on load. ``AVAILABLE`` and
        the error states appear only when a real call produced them within the
        verdict TTL; otherwise a configured deployment reports ``CONFIGURED``,
        which claims a key exists and nothing more.
        """
        settings = self._settings
        base = ConnectionStatus(
            configured=settings.ai_configured,
            provider=settings.ai_provider,
            model=settings.ai_active_model,
            state=AiConnectionState.NOT_CONFIGURED,
            issue=settings.ai_configuration_issue,
        )
        if not settings.ai_configured:
            return base

        verdict = await self._read_verdict()
        if verdict is None:
            return ConnectionStatus(
                configured=True,
                provider=base.provider,
                model=base.model,
                state=AiConnectionState.CONFIGURED,
            )
        return verdict

    async def check(
        self, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None
    ) -> ConnectionCheck:
        """Send one minimal real request to the configured provider and model.

        Never answers ``AVAILABLE`` without a model's response behind it. An
        unconfigured deployment is reported as such without any network call —
        there is nothing to send and no key to send it with.
        """
        settings = self._settings
        if not settings.ai_configured:
            check = ConnectionCheck(
                state=AiConnectionState.NOT_CONFIGURED,
                error_code=settings.ai_configuration_issue,
            )
        else:
            provider = self._provider if self._provider is not None else build_provider(settings)
            check = await provider.check(timeout_seconds=settings.ai_health_check_timeout_seconds)
            await record_connection_verdict(self._redis, settings, check, source="health_check")

        log = logger.info if check.state is AiConnectionState.AVAILABLE else logger.warning
        log(
            "ai_connection_checked",
            provider=settings.ai_provider,
            model=settings.ai_active_model,
            state=check.state.value,
            latency_ms=check.latency_ms,
            error_code=check.error_code,
        )

        if self._session is not None:
            await audit_for_session(self._session).record(
                organization_id=organization_id,
                action="AI_CONNECTION_CHECKED",
                module="ai",
                entity_type="AI_CONNECTION",
                actor_id=actor_id,
                details={
                    "provider": settings.ai_provider,
                    "model": settings.ai_active_model,
                    "state": check.state.value,
                    "latency_ms": check.latency_ms,
                    "error_code": check.error_code,
                },
            )
        return check

    async def _read_verdict(self) -> ConnectionStatus | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(_verdict_key(self._settings))
        except Exception:
            logger.warning("ai_connection_verdict_unavailable", operation="read", exc_info=True)
            return None
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            source: CheckSource = (
                "health_check" if data.get("source") == "health_check" else "feature_call"
            )
            return ConnectionStatus(
                configured=True,
                provider=self._settings.ai_provider,
                model=self._settings.ai_active_model,
                state=AiConnectionState(data["state"]),
                checked_at=dt.datetime.fromisoformat(data["checked_at"]),
                check_source=source,
                latency_ms=data.get("latency_ms"),
                error_code=data.get("error_code"),
            )
        except (ValueError, KeyError, TypeError):
            # A malformed entry is no evidence at all; fall back to CONFIGURED.
            logger.warning("ai_connection_verdict_malformed")
            return None


__all__ = [
    "CONNECTION_VERDICT_TTL_SECONDS",
    "DEFAULT_MARKET_INSIGHTS_PROMPT",
    "AiConnectionService",
    "AiGatewayService",
    "AiPromptService",
    "AiRateLimitedError",
    "ConnectionStatus",
    "PromptEmptyError",
    "credential_fingerprint",
    "record_connection_verdict",
]
