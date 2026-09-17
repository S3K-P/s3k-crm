"""AI Account Intelligence, summaries, next-best-action, email drafting,
meeting-to-CRM extraction, natural-language CRM queries and prioritization
(Checkpoint 7).

Built entirely on the AI gateway Checkpoint 1 verified
(:mod:`app.platform.ai`) and the same permission-filtered context pattern
:mod:`app.products.crm.market_insights` established — no second provider
interface, no second AI-status mechanism, no hardcoded "AI-generated" text.
See ``context.py`` for the authorized-context builder, ``structured.py`` for
how a model's free-text answer becomes a validated Pydantic object, and
``prioritization.py``/``insights.py`` for the parts of this checkpoint that
are deliberately *not* AI calls — rules evaluated over real CRM data, per the
checkpoint brief's "rules first, AI explanation second".
"""

from __future__ import annotations

__all__: list[str] = []
