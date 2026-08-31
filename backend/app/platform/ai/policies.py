"""Authorization for the AI gateway (ADR-010).

The gateway holds no policy predicates of its own: its routes are gated by
``require_permission("ai", ...)`` at the router, using the ordinary catalogue
vocabulary. Editing a prompt is ``ai.ADMIN``, which no system role template
grants — only the wildcard ``Admin`` role holds it, which is what keeps the
Settings surface administrator-only (§13).

Kept as a module so the gateway takes the same shape as every other Platform
module, and so a future per-feature policy has an obvious home.
"""

from __future__ import annotations

__all__: list[str] = []
