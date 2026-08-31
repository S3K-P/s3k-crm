"""Authorization for market_insights (ADR-010).

Two rules, both expressed through machinery that already exists rather than
through predicates written here:

* **Module access** — ``require_permission("market_insights", ...)`` on every
  route, exactly like every other CRM module.
* **Whose research is whose** — ``market_insights`` is registered in
  ``OWNER_SCOPED_MODULES``, so ``RecordVisibility`` narrows reads to sessions
  the caller owns unless they hold ``VIEW_TEAM`` or ``VIEW_ALL``. A rep sees
  their own research; a manager with ``VIEW_ALL`` sees the team's. That is the
  system's existing answer to "users cannot read another user's AI history"
  (§13), and reusing it means there is no second permission model to keep in
  step with the first.
"""

from __future__ import annotations

__all__: list[str] = []
