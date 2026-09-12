"""The one outbox event a CRM write publishes for workflow automation.

**Why one event type instead of one per trigger.** ``crm.record.event_occurred``
carries an ``entity_type``, a ``trigger`` reason (``created`` / ``updated`` /
``status_changed`` / ``stage_changed``) and, for an update, which fields
changed. The handler (`.service.handle_record_event`) matches it against every
active :class:`~app.products.crm.workflows.models.WorkflowRule` for that
entity — a lead status change and a lead's free-text notes being edited are
the same event shape, differing only in ``trigger``/``changed_fields``, and a
rule's ``trigger_type`` is what narrows one down to the other. Minting a
distinct outbox event type per trigger would mean the same write enqueueing
up to half a dozen events for handlers that all do the same lookup anyway.

**Payload is identifiers plus the change delta, never a full record.** Per the
outbox's own rule (`app.platform.events.models`), the handler re-reads the
record fresh — so condition evaluation never runs against a value that went
stale between enqueue and delivery. ``changed_fields`` is the exception worth
noting: it is not "the record's data," it is the delta *that caused the
event*, already computed once for the audit trail this same write appends —
recording it again here is what lets a ``FIELD_CHANGED`` rule ask "did it
change *to* this value" without re-deriving a diff the caller already knows
and the re-read alone cannot answer (a second write between enqueue and
delivery would make the *current* value agree with `to` even when this
particular change did not cause it).
"""

from __future__ import annotations

from typing import Final

#: A CRM record (or task) was created, updated, or moved through a guarded
#: transition. Tenant-scoped: dead-letters rather than running unscoped if the
#: event somehow arrives without an organization.
CRM_RECORD_EVENT_OCCURRED: Final = "crm.record.event_occurred"

__all__ = ["CRM_RECORD_EVENT_OCCURRED"]
