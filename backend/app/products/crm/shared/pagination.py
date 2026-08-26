"""Pagination, sorting and the standard list envelope — CRM's import path.

The definitions moved to :mod:`app.core.pagination` when the Platform audit
module needed them: ``app.platform.*`` must never import ``app.products.*``
(ARCHITECTURE-BOUNDARIES.md rule 1), and duplicating the envelope would have
given the API two subtly divergent list shapes.

Re-exported here rather than removed, so every CRM router and repository keeps
importing the path it already used and the wire format is provably identical —
these are the same objects, not a copy.
"""

from __future__ import annotations

from app.core.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    Page,
    PageMeta,
    PageParams,
    SortDirection,
    page_params,
)

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "Page",
    "PageMeta",
    "PageParams",
    "SortDirection",
    "page_params",
]
