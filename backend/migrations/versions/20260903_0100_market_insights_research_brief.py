"""Roll the Market Insights brief forward to the executive research report.

Revision ID: 20260903_0100
Revises: 20260831_0200
Create Date: 2026-09-03 01:00:00.000000

``20260827_0100`` gave Market Insights a prompt library, and
``AiPromptService.ensure_active`` seeds an organization's first version from
``DEFAULT_MARKET_INSIGHTS_PROMPT`` the first time anybody opens the feature.
That seeding happens once. Editing the constant therefore changes what a *new*
organization starts from and nothing at all for one that has already used the
feature: its version 1 sits in the table, untouched, forever.

This revision closes that gap for the organizations that never customised the
wording. The brief has been rewritten from "research this company for a
seller" into a two-to-three page executive market research report, with an
executive summary, key insights, financials, competition, a compliance and
regulatory section, technology maturity and AI opportunity areas. An
organization still running the original default should get it.

**Only the untouched default is replaced.** The match is on the full text of
the active version, so an administrator who has edited the prompt in AI
Settings keeps their wording and their organization is passed over. That is
why this compares text rather than version numbers: being on v1 is not proof
of "never edited", but holding the original bytes is.

**Nothing is rewritten in place.** The library is append-only, and research
already performed resolves to the version it ran under. This appends a new
version and moves the active flag, exactly as publishing from the Settings
screen would.

The work runs set-based across every tenant at once, through a temporary
table, rather than as one data-modifying CTE. The partial unique index
``uq_ai_prompt_versions_active`` permits a single active row per
(organization, key), and deactivating the old row and inserting the new one
inside one statement would leave that ordering to the planner.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0100"
down_revision: str | None = "20260831_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY = "market_insights"
CHANGE_NOTE = "Executive market research report brief"

#: The wording ``20260827_0100`` shipped, copied verbatim rather than imported
#: from ``app.platform.ai.service``: that constant is now the *new* text, and a
#: migration that read it would compare the new brief against itself and match
#: nothing. A migration has to carry its own copy of the history it moves.
OLD_BRIEF = """\
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

#: Must stay byte-identical to ``DEFAULT_MARKET_INSIGHTS_PROMPT`` as of this
#: revision, so that a tenant moved here and a tenant seeded fresh afterwards
#: run the same brief.
NEW_BRIEF = """\
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

#: The briefs as ``AiPromptService.publish`` writes them — ``prompt.strip()``.
#:
#: Normalised here in Python rather than with ``btrim`` in SQL, which is a trap
#: worth naming: one-argument ``btrim`` removes *spaces*, not whitespace, so it
#: leaves the trailing newline these literals end with. Comparing
#: ``btrim(prompt) = btrim(:brief)`` therefore matches no organization at all,
#: and the migration silently does nothing.
OLD_PROMPT = OLD_BRIEF.strip()
NEW_PROMPT = NEW_BRIEF.strip()

COLLECT_STALE = sa.text(
    """
    CREATE TEMP TABLE _market_insights_rollforward AS
    SELECT v.organization_id,
           (SELECT MAX(x.version)
              FROM platform.ai_prompt_versions x
             WHERE x.organization_id = v.organization_id
               AND x.key = :key) + 1 AS next_version
      FROM platform.ai_prompt_versions v
     WHERE v.key = :key
       AND v.is_active
       AND v.prompt = :brief
    """
)

DEACTIVATE = sa.text(
    """
    UPDATE platform.ai_prompt_versions v
       SET is_active = false,
           updated_at = now()
      FROM _market_insights_rollforward r
     WHERE v.organization_id = r.organization_id
       AND v.key = :key
       AND v.is_active
    """
)

APPEND = sa.text(
    """
    INSERT INTO platform.ai_prompt_versions
           (organization_id, key, version, prompt, change_note, is_active)
    SELECT r.organization_id, :key, r.next_version, :brief, :note, true
      FROM _market_insights_rollforward r
    """
)

DROP_SCRATCH = sa.text("DROP TABLE IF EXISTS _market_insights_rollforward")


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(DROP_SCRATCH)
    connection.execute(COLLECT_STALE, {"key": KEY, "brief": OLD_PROMPT})
    connection.execute(DEACTIVATE, {"key": KEY})
    connection.execute(APPEND, {"key": KEY, "brief": NEW_PROMPT, "note": CHANGE_NOTE})
    connection.execute(DROP_SCRATCH)


def downgrade() -> None:
    """Put the original brief back and remove the version this added.

    Deleting rather than appending a third version is defensible only because
    the row being removed is one this migration created: ``upgrade`` is the
    sole writer of a version carrying ``CHANGE_NOTE`` with this exact text, and
    a downgrade is not a history an operator wants preserved. Any version an
    administrator published is left alone, and so is any organization whose
    active brief is not the one this revision installed.
    """
    connection = op.get_bind()

    connection.execute(DROP_SCRATCH)
    # The organizations upgrade() moved: still active on the new brief, under
    # the change note only upgrade() writes.
    connection.execute(
        sa.text(
            """
            CREATE TEMP TABLE _market_insights_rollforward AS
            SELECT v.organization_id, v.id AS appended_id
              FROM platform.ai_prompt_versions v
             WHERE v.key = :key
               AND v.is_active
               AND v.change_note = :note
               AND v.prompt = :brief
            """
        ),
        {"key": KEY, "note": CHANGE_NOTE, "brief": NEW_PROMPT},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM platform.ai_prompt_versions v
             USING _market_insights_rollforward r
             WHERE v.id = r.appended_id
            """
        )
    )
    # Reactivate the newest surviving version per organization, which is the
    # row deactivated on the way up. One row each, so the partial unique index
    # sees exactly one active version again.
    connection.execute(
        sa.text(
            """
            UPDATE platform.ai_prompt_versions v
               SET is_active = true,
                   updated_at = now()
             WHERE v.id IN (
                   SELECT DISTINCT ON (x.organization_id) x.id
                     FROM platform.ai_prompt_versions x
                     JOIN _market_insights_rollforward r
                       ON r.organization_id = x.organization_id
                    WHERE x.key = :key
                    ORDER BY x.organization_id, x.version DESC
             )
            """
        ),
        {"key": KEY},
    )
    connection.execute(DROP_SCRATCH)
