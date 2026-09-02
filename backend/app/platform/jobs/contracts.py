"""What a job handler is given.

The queue's public surface for products. ``app.platform.jobs.models`` is an
internal — ADR-003 says a product consumes Platform through service interfaces,
never through its models or repositories, and
``tests/unit/test_module_boundaries.py`` enforces it.

The first version of the handler signature took the ``Job`` row itself, which
broke that rule. It was also more than a handler needs: the ORM row carries
retry bookkeeping, lock state and a mutable session identity, none of which a
handler has any business touching. :class:`JobContext` is the data, frozen.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class JobContext:
    """One job, as its handler sees it."""

    job_id: uuid.UUID
    #: The tenant this job runs for. The session the handler receives is
    #: already scoped to it, so this is for logging and for payload lookups
    #: rather than for filtering — a handler that filters on it as well is
    #: belt and braces, not a requirement.
    organization_id: uuid.UUID
    job_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    #: Which attempt this is, starting at 1. Lets a handler log differently on
    #: a retry, or skip work that is expensive and known to be redone.
    attempt: int = 1


__all__ = ["JobContext"]
