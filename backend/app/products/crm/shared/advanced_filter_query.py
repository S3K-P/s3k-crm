"""The ``advanced_filter`` query parameter every list endpoint shares (Checkpoint 5).

One JSON-encoded ``reports.conditions.ReportFilterGroup`` per request — the
same document shape a saved view's own ``advanced_filter`` column stores and
the custom-report builder's filter step produces, so a condition means the
same thing in all three places. Parsing lives here so every list endpoint
that offers the parameter gets identical error behaviour for malformed JSON,
rather than four slightly different try/except blocks.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from app.core.exceptions import ValidationFailedError
from app.products.crm.reports.conditions import ReportFilterGroup

#: Comfortably past what a person builds by hand in a filter UI (Checkpoint
#: 5's builder caps a group at 20 conditions — see ``ReportFilterGroup``) with
#: headroom for the JSON punctuation around it, without leaving the query
#: string open to an arbitrarily large body smuggled in through a GET.
_MAX_LENGTH = 4000


def parse_advanced_filter(
    advanced_filter: Annotated[
        str | None,
        Query(
            max_length=_MAX_LENGTH,
            description=(
                "JSON-encoded ReportFilterGroup — the same shape a saved "
                "view's advanced_filter stores."
            ),
        ),
    ] = None,
) -> ReportFilterGroup | None:
    if advanced_filter is None or not advanced_filter.strip():
        return None
    try:
        return ReportFilterGroup.model_validate_json(advanced_filter)
    except ValueError as exc:
        msg = f"advanced_filter is not valid: {exc}"
        raise ValidationFailedError(msg) from exc


AdvancedFilterDep = Annotated[ReportFilterGroup | None, Depends(parse_advanced_filter)]

__all__ = ["AdvancedFilterDep", "parse_advanced_filter"]
