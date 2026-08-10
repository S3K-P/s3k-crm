"""Tests for UUID v7 generation (decision D02)."""

from __future__ import annotations

import time
from uuid import UUID

import pytest

from app.core.ids import uuid7, uuid7_timestamp_ms


def test_version_and_variant_bits_are_rfc_9562_compliant() -> None:
    value = uuid7()

    assert value.version == 7
    # RFC 9562 variant is the two most significant bits of octet 8 == 0b10.
    assert (value.int >> 62) & 0b11 == 0b10


def test_embedded_timestamp_tracks_wall_clock() -> None:
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000

    embedded = uuid7_timestamp_ms(value)

    assert before <= embedded <= after


def test_values_are_monotonically_increasing() -> None:
    """Time-ordering is the entire point: keys must never go backwards."""
    values = [uuid7() for _ in range(5_000)]

    assert values == sorted(values), "uuid7() emitted a non-monotonic sequence"


def test_values_are_unique() -> None:
    values = [uuid7() for _ in range(10_000)]

    assert len(set(values)) == len(values)


def test_sorting_by_uuid_matches_creation_order_across_milliseconds() -> None:
    first = uuid7()
    time.sleep(0.002)
    second = uuid7()

    assert first < second
    assert uuid7_timestamp_ms(first) < uuid7_timestamp_ms(second)


def test_timestamp_extraction_rejects_other_uuid_versions() -> None:
    v4 = UUID("d9428888-122b-11e1-b85c-61cd3cbb3210")  # version 1

    with pytest.raises(ValueError, match="version 7"):
        uuid7_timestamp_ms(v4)
