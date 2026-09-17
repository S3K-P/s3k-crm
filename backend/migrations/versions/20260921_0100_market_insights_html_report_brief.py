"""Roll the Market Insights brief forward to the HTML market research report.

Revision ID: 20260921_0100
Revises: 20260920_0100
Create Date: 2026-09-21 01:00:00.000000

``AiPromptService.ensure_active`` seeds an organization's first version from
``DEFAULT_MARKET_INSIGHTS_PROMPT`` once, so editing that constant changes what a
*new* organization starts from and nothing for one that has already opened
Market Insights. This revision moves the organizations still running a
shipped default onto the new one.

The new brief is the full executive Market Research Report specification: a
two-to-three page, print-friendly, self-contained HTML document with a
dedicated Compliance & Related Information section, CONFIRMED FACT / PUBLICLY
REPORTED / INFERENCE labelling, a source-quality hierarchy, and
``{{company_name}}`` / ``{{company_website}}`` placeholders the feature fills
per turn.

**Only an untouched default is replaced.** The match is on the full text of the
active version, so an organization whose administrator edited the prompt in AI
Settings keeps its wording. Holding a shipped default's exact bytes is the
proof of "never edited"; a version number is not.

**Nothing is rewritten in place.** A new version is appended and the active
flag moves, exactly as publishing from the Settings screen does, so research
already performed still resolves to the version it ran under.

**Tenant by tenant, not set-based — and why that matters.** Row-level security
on ``platform.ai_prompt_versions`` is FORCEd, so a statement run without
``app.current_org_id`` sees no rows at all, even as the table's owner. Only a
superuser or a BYPASSRLS role is exempt. ``20260903_0100`` updated every tenant
in one statement, and under a role like CI's ``s3k_app`` it therefore matched
nothing and moved nobody, without an error. This revision sets the tenant for
each organization in turn, as the application does, so it behaves the same
whichever role runs it (``platform.organizations`` is RLS-exempt, which is what
makes the tenant list readable). Each statement also names the organization
explicitly, because under a superuser the policy does not filter at all.

For the same reason both shipped defaults are recognised, not only the latest:
an organization that ``20260903_0100`` silently passed over is still on the
original ``20260827_0100`` brief, and is just as untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision: str = "20260921_0100"
down_revision: str | None = "20260920_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY = "market_insights"
CHANGE_NOTE = "HTML market research report brief with compliance section"

#: The brief ``20260827_0100`` shipped. Copied verbatim, like both briefs
#: below, rather than imported: ``app.platform.ai.service`` holds only the
#: newest text, and a migration has to carry its own copy of the history it
#: moves.
ORIGINAL_BRIEF = """\
Research this company comprehensively, for a sales and business development \
audience. Prioritise information that would change how a seller approaches \
them.

Cover the areas below that you can support with evidence, as level-two \
Markdown headings, in this order. Omit any heading you have nothing reliable \
to say about rather than filling it with generalities:

## Company Overview
## Industry
## Products & Services
## Market Position
## Business Model
## Key Customers & Markets
## Competitors
## Recent Developments
## Leadership
## Financial & Business Information
## Opportunities
## Risks & Challenges
## Sales Relevance
## Recommended Next Actions

Guidance:
- Lead each section with the conclusion, then the evidence for it.
- Prefer specifics — named customers, dated events, figures — over adjectives.
- Attribute anything time-sensitive, and give the date it was true.
- Where sources disagree, say so and give both readings.
- Mark anything uncertain as uncertain. Never present an inference as a fact, \
and never invent a figure, a customer, a person or an event to fill a gap.
"""

#: The brief ``20260903_0100`` installed and new organizations were then seeded
#: with, until this revision.
PREVIOUS_BRIEF = """\
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

#: Must stay byte-identical to ``DEFAULT_MARKET_INSIGHTS_PROMPT`` as of this
#: revision, so that a tenant moved here and a tenant seeded fresh afterwards
#: run the same brief.
NEW_BRIEF = """\
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

#: The briefs as ``AiPromptService.publish`` stores them — ``prompt.strip()``.
#: Normalised in Python, not with one-argument ``btrim`` in SQL, which strips
#: spaces only and would leave the trailing newline (see ``20260903_0100``).
ORIGINAL_PROMPT = ORIGINAL_BRIEF.strip()
PREVIOUS_PROMPT = PREVIOUS_BRIEF.strip()
NEW_PROMPT = NEW_BRIEF.strip()

TENANTS = sa.text("SELECT id::text FROM platform.organizations ORDER BY id")
CURRENT_TENANT = sa.text("SELECT current_setting('app.current_org_id', true)")
#: Transaction-local, exactly like the application's own tenant context.
SET_TENANT = sa.text("SELECT set_config('app.current_org_id', :org, true)")

DEACTIVATE_UNTOUCHED = sa.text(
    """
    UPDATE platform.ai_prompt_versions
       SET is_active = false,
           updated_at = now()
     WHERE organization_id = CAST(:org AS uuid)
       AND key = :key
       AND is_active
       AND prompt IN (:original, :previous)
    RETURNING id
    """
)

#: Every parameter in the select list is cast. ``:key`` appears there and in the
#: ``WHERE``, and asyncpg refuses a parameter whose type it deduces two ways.
APPEND = sa.text(
    """
    INSERT INTO platform.ai_prompt_versions
           (organization_id, key, version, prompt, change_note, is_active)
    SELECT CAST(:org AS uuid), CAST(:key AS varchar), MAX(version) + 1,
           CAST(:brief AS text), CAST(:note AS varchar), true
      FROM platform.ai_prompt_versions
     WHERE organization_id = CAST(:org AS uuid)
       AND key = :key
    """
)

REMOVE_APPENDED = sa.text(
    """
    DELETE FROM platform.ai_prompt_versions
     WHERE organization_id = CAST(:org AS uuid)
       AND key = :key
       AND is_active
       AND change_note = :note
       AND prompt = :brief
    RETURNING id
    """
)

REACTIVATE_NEWEST = sa.text(
    """
    UPDATE platform.ai_prompt_versions
       SET is_active = true,
           updated_at = now()
     WHERE id = (SELECT id
                   FROM platform.ai_prompt_versions
                  WHERE organization_id = CAST(:org AS uuid)
                    AND key = :key
                  ORDER BY version DESC
                  LIMIT 1)
    """
)


def _for_each_tenant(step: Callable[[Connection, str], None]) -> None:
    """Run ``step`` once per organization, with that tenant's context set.

    The context in force beforehand is put back afterwards, so later
    revisions in the same transaction see what they would have seen anyway.
    Not in a ``finally``: after a failed statement the transaction is aborted
    and a restoring statement would raise over the real error, while the
    rollback discards the transaction-local setting regardless.
    """
    connection = op.get_bind()
    previous = connection.execute(CURRENT_TENANT).scalar() or ""
    for org in connection.execute(TENANTS).scalars().all():
        connection.execute(SET_TENANT, {"org": org})
        step(connection, org)
    connection.execute(SET_TENANT, {"org": previous})


def _roll_forward(connection: Connection, org: str) -> None:
    # Deactivate first, then append: the partial unique index
    # ``uq_ai_prompt_versions_active`` allows one active row per
    # (organization, key), and two statements fix the order.
    deactivated = connection.execute(
        DEACTIVATE_UNTOUCHED,
        {"org": org, "key": KEY, "original": ORIGINAL_PROMPT, "previous": PREVIOUS_PROMPT},
    ).first()
    if deactivated is not None:
        connection.execute(
            APPEND, {"org": org, "key": KEY, "brief": NEW_PROMPT, "note": CHANGE_NOTE}
        )


def _roll_back(connection: Connection, org: str) -> None:
    removed = connection.execute(
        REMOVE_APPENDED, {"org": org, "key": KEY, "note": CHANGE_NOTE, "brief": NEW_PROMPT}
    ).first()
    if removed is not None:
        connection.execute(REACTIVATE_NEWEST, {"org": org, "key": KEY})


def upgrade() -> None:
    _for_each_tenant(_roll_forward)


def downgrade() -> None:
    """Remove the version this added and reactivate the one it replaced.

    Deleting rather than appending is defensible only because the row removed
    is one this migration created: ``upgrade`` is the sole writer of a version
    carrying ``CHANGE_NOTE`` with this exact text. The newest surviving version
    is the one ``upgrade`` deactivated. Versions an administrator published,
    and organizations whose active brief is anything else, are left alone.
    """
    _for_each_tenant(_roll_back)
