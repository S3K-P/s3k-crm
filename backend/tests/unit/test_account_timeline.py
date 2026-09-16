"""``merge_timeline_entries``: the sort and the cutoff, with no database.

The Account 360 timeline draws from four independent sources (activities,
deal creation, stage changes, contact creation), each queried and limited
separately. What has to be correct about combining them — newest first,
truncated to the caller's limit, ties broken without dropping entries — is a
pure function on plain dataclasses, and is tested here without touching
Postgres. The four repository queries that produce these entries need a real
database and are covered by
``tests/integration/test_account_relationships.py`` instead.
"""

from __future__ import annotations

import datetime as dt
import uuid

from app.products.crm.accounts.overview import TimelineEntry, merge_timeline_entries


def _entry(minutes_ago: int, kind: str = "activity") -> TimelineEntry:
    occurred_at = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.UTC) - dt.timedelta(minutes=minutes_ago)
    return TimelineEntry(
        kind=kind,
        occurred_at=occurred_at,
        title=f"{kind} at -{minutes_ago}m",
        detail=None,
        entity_type="ACCOUNT",
        entity_id=uuid.uuid4(),
    )


def test_entries_from_every_source_are_merged_newest_first() -> None:
    # Minutes ago, smallest (most recent) first once merged: stage(5) <
    # activity(10) < contact(15) < deal(20) < activity(30).
    activities = [_entry(30), _entry(10)]
    deals = [_entry(20, "deal_created")]
    stages = [_entry(5, "stage_changed")]
    contacts = [_entry(15, "contact_created")]

    merged = merge_timeline_entries(activities, deals, stages, contacts, limit=50)

    assert [entry.kind for entry in merged] == [
        "stage_changed",
        "activity",
        "contact_created",
        "deal_created",
        "activity",
    ]
    assert all(
        merged[i].occurred_at >= merged[i + 1].occurred_at for i in range(len(merged) - 1)
    )


def test_the_limit_keeps_the_newest_and_drops_the_rest() -> None:
    activities = [_entry(minutes) for minutes in range(10)]

    merged = merge_timeline_entries(activities, limit=3)

    assert len(merged) == 3
    assert [entry.title for entry in merged] == [
        "activity at -0m",
        "activity at -1m",
        "activity at -2m",
    ]


def test_an_empty_source_contributes_nothing() -> None:
    merged = merge_timeline_entries([], [_entry(1)], [], limit=10)

    assert len(merged) == 1


def test_no_sources_is_an_empty_timeline_not_an_error() -> None:
    assert merge_timeline_entries(limit=10) == []


def test_a_tie_keeps_both_entries() -> None:
    """Two events at the exact same timestamp must not collide or vanish."""
    same_time = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.UTC)
    a = TimelineEntry(
        kind="activity",
        occurred_at=same_time,
        title="a",
        detail=None,
        entity_type="ACCOUNT",
        entity_id=uuid.uuid4(),
    )
    b = TimelineEntry(
        kind="deal_created",
        occurred_at=same_time,
        title="b",
        detail=None,
        entity_type="OPPORTUNITY",
        entity_id=uuid.uuid4(),
    )

    merged = merge_timeline_entries([a], [b], limit=10)

    assert {entry.title for entry in merged} == {"a", "b"}
