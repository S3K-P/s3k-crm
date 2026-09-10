"""Domain events for merges.

Placeholder. A merge is recorded in the audit trail rather than published:
nothing in the product reacts to one today, and an outbox event nobody consumes
is a queue that only ever grows. The trail entry carries the surviving id, the
losing ids and the field choices, which is what an investigation needs.
"""
