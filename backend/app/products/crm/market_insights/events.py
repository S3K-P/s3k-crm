"""Domain events for the market_insights module.

None yet. A completed research session is already recorded in the audit trail
by ``TenantScopedService``; no consumer exists for an outbox event, and an
outbox nobody reads is a table that only grows (ADR-013).
"""

from __future__ import annotations

__all__: list[str] = []
