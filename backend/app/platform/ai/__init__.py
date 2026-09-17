"""Shared Platform module: the AI gateway (ADR-016).

Every model call in the platform goes through here, and this module is the
only place an AI provider credential is read. Product features — S3K CRM's
Market Insights first — call :mod:`app.platform.ai.service` and never build a
request or touch a client themselves.

That boundary exists for three reasons:

* **One credential path.** The key lives in :class:`~app.core.config.Settings`
  as a ``SecretStr`` and is read once, here. It never reaches a response body,
  a log line or the frontend.
* **One honest failure.** When no key is configured the gateway raises
  ``ai_not_configured`` and callers surface it. Nothing anywhere degrades to
  invented output — the specific failure the Phase 1 branch removed the mock
  AI screens to prevent.
* **One place prompts are versioned.** An administrator edits a prompt and a
  *new version row* is written; the old one is never mutated, so research
  performed under the previous wording still says what it said (§12).

Boundaries: this module may not import ``app.products.*``. The CRM feature
depends on the gateway, never the reverse.
"""

from __future__ import annotations
