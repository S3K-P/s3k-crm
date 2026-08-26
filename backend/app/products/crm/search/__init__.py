"""S3K CRM module: search (`P3-W20`, doc 10 Module 14).

Global search across accounts, contacts, leads and opportunities, backed by
PostgreSQL full-text search and ``pg_trgm`` (doc 12) rather than a separate
engine — the revisit trigger is >1M searchable records or p95 > 200 ms.

The module owns no tables. What it owns is one query, and the rule that every
permission filter lives inside it.
"""

from __future__ import annotations
