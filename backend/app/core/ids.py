"""UUID version 7 primary keys (decision D02).

UUID v7 embeds a big-endian Unix millisecond timestamp in its leading bits, so
generated keys are time-ordered. That keeps B-tree inserts append-mostly and
avoids the index fragmentation UUID v4 causes on high-write tables.

PostgreSQL 18 ships a native ``uuidv7()`` which is used as the server-side
column default (see :mod:`app.core.models`). This module provides the
client-side equivalent for code that needs an identifier before INSERT — for
example writing an outbox event that references the row it accompanies.

Python 3.13 has no ``uuid.uuid7``; it arrives in the standard library in 3.14.
Until then this implementation follows RFC 9562 §5.7.
"""

from __future__ import annotations

import os
import time
from uuid import UUID

__all__ = ["uuid7", "uuid7_timestamp_ms"]

_VERSION = 7
_LAST_MS = 0
_SEQUENCE = 0

# 12 bits of monotonic counter (rand_a) per millisecond, per RFC 9562 method 1.
_MAX_SEQUENCE = 0xFFF


def uuid7() -> UUID:
    """Return a time-ordered UUID version 7.

    Values generated within the same millisecond stay strictly increasing via a
    12-bit counter; the remaining 62 bits are random. Not intended to be
    unguessable — never use a primary key as a security token.
    """
    global _LAST_MS, _SEQUENCE

    now_ms = time.time_ns() // 1_000_000

    if now_ms > _LAST_MS:
        _LAST_MS = now_ms
        _SEQUENCE = 0
    elif _SEQUENCE < _MAX_SEQUENCE:
        _SEQUENCE += 1
    else:
        # Counter exhausted within this millisecond: borrow from the next one
        # rather than emit a duplicate or go backwards.
        _LAST_MS += 1
        _SEQUENCE = 0

    timestamp_ms = _LAST_MS

    # 48 bits timestamp | 4 bits version | 12 bits counter | 2 bits variant | 62 bits random
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)

    value = (timestamp_ms & ((1 << 48) - 1)) << 80
    value |= _VERSION << 76
    value |= _SEQUENCE << 64
    value |= 0b10 << 62
    value |= rand_b

    return UUID(int=value)


def uuid7_timestamp_ms(value: UUID) -> int:
    """Extract the embedded Unix millisecond timestamp from a UUID v7.

    Raises:
        ValueError: if ``value`` is not a version 7 UUID.
    """
    if value.version != _VERSION:
        msg = f"expected a UUID version 7, got version {value.version}"
        raise ValueError(msg)
    return value.int >> 80
