"""S3K CRM module: Market Insights.

AI-assisted company research. A user names a company — one already in the CRM
or any external business — and the module produces a Market Intelligence
Report with real, retrieved sources, then keeps the conversation open for
follow-up questions about that company.

Boundaries worth stating, because both were easy to get wrong:

**It reads CRM data; it never writes it.** Research is an intelligence layer.
External findings that disagree with the account record do not overwrite it,
and nothing here mutates an account. The one write path is explicit and
user-initiated — "Add to CRM" for an external company — and it goes through
``AccountService``, duplicate warning and all, rather than inserting a row
itself (§7, §8).

**It owns no AI logic.** The model call, the credential and the prompt library
all live in ``app.platform.ai``. This module composes context and stores
results.
"""

from __future__ import annotations
