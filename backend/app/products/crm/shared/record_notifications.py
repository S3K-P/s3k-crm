"""Notifications for the CRM events the roadmap names (P4-W27-BE-03).

Exactly four, and deliberately no more: **task assigned**, **task completed**,
**lead qualified** and **opportunity won**. Each is a one-off event somebody
other than the actor needs to act on or know about, which is what earns it an
email as well as an in-app notification. Recurring or cosmetic changes — a
field edit, a stage moved forward, a task reopened — stay silent; an inbox that
fills with those is one people learn to filter.

Two rules apply to all of them:

* **Nobody is notified of their own action.** Assigning a task to yourself or
  qualifying your own lead produces nothing.
* **The notification is part of the action's transaction.** It is written, and
  its email enqueued on the outbox, beside the state change: if the change
  rolls back, neither exists. Delivery is Microsoft Graph via the outbox, the
  same path as every other message.

The kinds are stored as plain text on the notification (``Notification.kind``
is ``String(32)``), so these constants are the vocabulary rather than a schema.
"""

from __future__ import annotations

import uuid
from typing import Final

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.notifications.service import notifications_for_session

logger = structlog.get_logger(__name__)

TASK_ASSIGNED: Final = "TASK_ASSIGNED"
TASK_COMPLETED: Final = "TASK_COMPLETED"
LEAD_QUALIFIED: Final = "LEAD_QUALIFIED"
OPPORTUNITY_WON: Final = "OPPORTUNITY_WON"

#: Every kind this module can raise, for tests and for the UI's labels.
RECORD_NOTIFICATION_KINDS: Final = frozenset(
    {TASK_ASSIGNED, TASK_COMPLETED, LEAD_QUALIFIED, OPPORTUNITY_WON}
)


async def notify_record_event(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    recipient_id: uuid.UUID | None,
    actor_id: uuid.UUID | None,
    kind: str,
    title: str,
    message: str,
    entity_type: str,
    entity_id: uuid.UUID,
    record_path: str,
) -> bool:
    """Notify ``recipient_id`` in-app and by email. Returns whether anyone was.

    A missing recipient, or one who is the actor, is a normal outcome rather
    than an error: most tasks have no separate assignee, and people assign
    work to themselves all the time.
    """
    if kind not in RECORD_NOTIFICATION_KINDS:
        msg = f"Unknown CRM notification kind '{kind}'."
        raise ValueError(msg)
    if recipient_id is None or recipient_id == actor_id:
        return False

    await notifications_for_session(session).notify(
        organization_id=organization_id,
        recipient_user_id=recipient_id,
        kind=kind,
        title=title[:255],
        body=message,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        email=True,
        record_path=record_path,
    )
    logger.info(
        "crm_record_notification_raised",
        kind=kind,
        organization_id=str(organization_id),
        entity_id=str(entity_id),
    )
    return True


__all__ = [
    "LEAD_QUALIFIED",
    "OPPORTUNITY_WON",
    "RECORD_NOTIFICATION_KINDS",
    "TASK_ASSIGNED",
    "TASK_COMPLETED",
    "notify_record_event",
]
