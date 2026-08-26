"""SQLAlchemy models for the search module.

Deliberately empty. Search owns no tables: it reads the ``search_vector``
columns that belong to accounts, contacts, leads and opportunities, each
declared on its own model and maintained by PostgreSQL (revision
``20260826_0100``).

A ``search_index`` table of its own would be the obvious alternative and is the
wrong shape here — it would be a copy of four tables that has to be kept in
step with them, and every gap between a write and the reindex is a window
where search returns stale titles or misses new records entirely. The vectors
live on the rows they describe, so there is no window.
"""

from __future__ import annotations

__all__: list[str] = []
