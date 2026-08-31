"""Domain events for the AI gateway.

None yet. Prompt publication is an administrative act already captured in the
audit trail (``AI_PROMPT_PUBLISHED``), and no consumer exists for an outbox
event — a table with no reader only grows (ADR-013).
"""

from __future__ import annotations

__all__: list[str] = []
