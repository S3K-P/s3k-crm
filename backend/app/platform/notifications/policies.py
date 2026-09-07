"""Authorization for the notifications module, and the reminder-source contract.

**Notifications carry no permission module.** Every other Platform and CRM
module gates access with ``require_permission(module, action)`` against
``authorization.catalog.PERMISSION_MODULES`` — but a notification is not
organizational data somebody might be granted broader access to, the way a
lead or a report is. It is one user's own mailbox. The access rule is simply
*the caller may read and mark read only notifications addressed to them*,
which is not a role grant at all: it is identity, enforced by
:class:`~app.platform.notifications.repository.NotificationRepository`
filtering every query on ``recipient_user_id`` as well as ``organization_id``
(see that module's docstring). Authentication (``CurrentPrincipal``) is
therefore the whole gate on every route in ``router.py`` — there is no
``VIEW``/``CREATE``/``EDIT``/``DELETE`` to hold or withhold, on purpose.

**The reminder-source inversion.** Deciding *which reminders are due* needs
CRM data — meetings, tasks — that Platform may not import
(ARCHITECTURE-BOUNDARIES.md rule 1). The dependency is inverted the same way
``app.platform.documents.policies.EntityAccessVerifier`` inverts attachment
access: this module declares the :class:`ReminderSource` Protocol,
``service.py`` holds a fail-closed registry for it (:func:`register_reminder_source`
there — placed in the service rather than the router, because the scheduler
that consumes it runs outside any HTTP request), and ``app/api/router.py`` —
the one module permitted to see both layers — registers the CRM
implementation (:func:`app.products.crm.shared.reminders.crm_reminder_source`)
at import time, before the application starts serving.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ReminderDue:
    """One reminder a :class:`ReminderSource` has determined is due now.

    Carries everything
    :meth:`~app.platform.notifications.service.NotificationService.dispatch_due_reminders`
    needs to write a :class:`~app.platform.notifications.models.Notification`
    without knowing anything about the record the reminder came from.
    """

    recipient_user_id: uuid.UUID
    kind: str
    title: str
    body: str | None
    entity_type: str
    entity_id: uuid.UUID
    #: Unique per (organization, recipient) — see the ``notifications`` table's
    #: unique constraint. Firing the same reminder on the next tick, before it
    #: has been superseded (a meeting rescheduled, a task completed), must
    #: produce the same key so the second insert is a harmless no-op rather
    #: than a duplicate notification.
    dedupe_key: str


class ReminderSource(Protocol):
    """What the scheduler needs from a product in order to raise reminders.

    Implemented by :mod:`app.products.crm.shared.reminders`. A second product
    gaining its own remindable records in future would add a second
    implementation and a second registration, not a change here.
    """

    async def due_reminders(
        self, session: AsyncSession, *, organization_id: uuid.UUID, now: dt.datetime
    ) -> Sequence[ReminderDue]:
        """Reminders that should fire for ``organization_id`` as of ``now``.

        ``session`` is already scoped to ``organization_id`` (the caller has
        applied :func:`app.core.database.provisioning_scope` around this
        call), so a correct implementation is an ordinary tenant-scoped
        read — no additional filtering is required for isolation, only for
        which rows count as "due".
        """
        ...


class NullReminderSource:
    """The default before anything registers a real source.

    Returns no reminders, ever — the same "fail closed" shape
    ``DenyAllEntityAccess`` uses for attachments. A wiring mistake here means
    reminders silently stop firing, which is a bug to notice and fix, not a
    security hole; unlike attachment access, "sees nothing it shouldn't" is
    not the risk on this path, so this is a plain no-op rather than a raise.
    """

    async def due_reminders(
        self, session: AsyncSession, *, organization_id: uuid.UUID, now: dt.datetime
    ) -> Sequence[ReminderDue]:
        return ()


__all__ = ["NullReminderSource", "ReminderDue", "ReminderSource"]
