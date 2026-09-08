"""Shared Platform module: notifications.

The recipient's own in-app inbox, plus the meeting/task reminder scheduler
that fills it (Phase A of the S3K vs Zoho CRM gap-closing plan).

One table, ``platform.notifications``, tenant-scoped under the same RLS
policy as every other tenant table — see ``policies.py`` for the one
guarantee RLS does *not* give it (which recipient a row belongs to) and how
``repository.py`` enforces that instead.

    models.py      the table, and the (writer-side) notification-kind vocabulary
    repository.py  data access; every statement filters on organization_id
                    **and** recipient_user_id
    service.py     the module's public interface: notify(), the recipient's
                    own read/write, the reminder-source registry, and
                    dispatch across every organization
    scheduler.py   the in-process asyncio task that calls dispatch on a timer
    policies.py    why there is no permission module here, and the
                    ReminderSource Protocol that inverts the CRM dependency
    schemas.py     the wire contract
    router.py      /api/v1/notifications — the caller's own inbox only
    events.py      why the outbox flow is not what runs today

The CRM's implementation of ``ReminderSource`` lives at
``app.products.crm.shared.reminders`` and is registered by
``app/api/router.py`` — the same inversion ``crm_entity_access`` uses for
attachments (ARCHITECTURE-BOUNDARIES.md rule 1: Platform may not import a
product).
"""
