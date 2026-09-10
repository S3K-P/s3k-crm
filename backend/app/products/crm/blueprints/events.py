"""Domain events for blueprints.

Placeholder. A configuration change is recorded in the audit trail rather than
published: nothing in the product reacts to a blueprint being edited, and an
outbox event nobody consumes is a queue that only ever grows. A *blocked
transition* is likewise not an event — it is a 422 the user sees immediately.
"""
