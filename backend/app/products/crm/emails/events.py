"""Domain events emitted by the emails module (ADR-013).

One event type, and it carries an identifier rather than a message.

The platform's own email events put the whole rendered context in the payload,
which is right for a three-line invitation. It is wrong here: a sales email is
a body somebody typed, possibly with attachments, and copying it into the
outbox would store the message twice — once in ``crm.email_messages`` where it
is edited and read, and once in ``platform.outbox_events`` where it is not.
The two would then disagree the moment a draft was edited between the enqueue
and the send, and the copy in the outbox is the one that would go out.

So the payload is ``{"message_id": ...}`` and the handler reads the row. The
row is the message; the event is only the instruction to send it.
"""

from __future__ import annotations

from typing import Final

#: Requested when a user sends a composed message. Tenant-scoped: a CRM email
#: always belongs to the organization whose record it is filed against, and one
#: that somehow arrived without an organization must dead-letter rather than
#: deliver unscoped.
CRM_EMAIL_SEND_REQUESTED: Final = "crm.email.send_requested"

__all__ = ["CRM_EMAIL_SEND_REQUESTED"]
