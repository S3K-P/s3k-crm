"""Domain events for the products module.

None yet. Granting and revoking entitlements are commercial events a billing
integration would want (ADR-013), but no consumer exists, and an outbox with
no reader is a table that only grows.
"""

from __future__ import annotations

__all__: list[str] = []
