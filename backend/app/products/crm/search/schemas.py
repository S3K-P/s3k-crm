"""Pydantic contracts for global CRM search (doc 11: ``GET /crm/search?q=``).

One flat result shape across four entity types, plus a grouped view of the
same rows. Flat is what the ⌘K palette renders — a single ranked list the user
arrows through — and the groups are a convenience for a full results page,
built from the same rows so the two can never disagree.

A result deliberately carries **only** what a palette row needs: type, id,
title, subtitle and score. It is not a preview of the record. Returning richer
fields would mean search became a second, unversioned read API for four
entities, with its own opinion about which fields are safe to expose — and the
first time somebody added a field there without checking, search would leak it
past the detail endpoint's own rules.
"""

from __future__ import annotations

import enum
import uuid

from pydantic import BaseModel, Field


class SearchEntityType(enum.StrEnum):
    """What a hit is. Values match the ``types=`` query parameter."""

    ACCOUNT = "ACCOUNT"
    CONTACT = "CONTACT"
    LEAD = "LEAD"
    OPPORTUNITY = "OPPORTUNITY"


class SearchHit(BaseModel):
    """One matching record, reduced to what a result row shows."""

    type: SearchEntityType
    id: uuid.UUID
    #: The record's own name — account or opportunity name, person's full name.
    title: str
    #: One line of disambiguation: the company, the email, the stage. ``None``
    #: when the record carries nothing useful, rather than an empty string, so
    #: the client can omit the line instead of rendering a blank one.
    subtitle: str | None = None
    #: Relevance, 0..1-ish and comparable *across* entity types — which is the
    #: whole reason it is returned. ``ts_rank`` alone is not comparable between
    #: tables with different vector sizes; see the repository.
    score: float


class SearchGroup(BaseModel):
    """Hits of one entity type, in rank order."""

    type: SearchEntityType
    #: Hits returned in this group. Not a total for the whole organization —
    #: see ``SearchResults.truncated``.
    hits: list[SearchHit]


class SearchResults(BaseModel):
    """The response. ``hits`` and ``groups`` describe the same rows."""

    #: Echoed so a client racing several keystrokes can discard stale replies.
    query: str
    #: Every hit the caller may see, best first, across all searched types.
    hits: list[SearchHit] = Field(default_factory=list)
    #: The same hits, partitioned by type. Types with no hits are omitted.
    groups: list[SearchGroup] = Field(default_factory=list)
    #: Entity types actually searched — those the caller holds ``VIEW`` on.
    #: Exposed so the UI can say "you cannot search leads" rather than
    #: implying there are none.
    searched: list[SearchEntityType] = Field(default_factory=list)
    #: True when the limit cut the list short, so the UI can invite a narrower
    #: query. A flag rather than a total: the total would be honest — every
    #: filter is inside the query, so counting counts only the caller's own
    #: rows — but it costs a second aggregate over the whole union to render a
    #: number nobody acts on. "There is more" is the entire decision a palette
    #: needs, and it is already known from having asked for one row extra.
    truncated: bool = False


__all__ = [
    "SearchEntityType",
    "SearchGroup",
    "SearchHit",
    "SearchResults",
]
