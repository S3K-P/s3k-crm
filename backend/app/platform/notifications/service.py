"""Use cases for the notifications module — the module's public interface.

Two audiences, and they arrive through different paths.

**A user reading their own mailbox** — list, unread count, mark read — is
ordinary recipient-scoped read/write, gated by identity alone (see
``policies.py`` for why there is no permission module).

**A reminder becoming due** has no HTTP caller at all. It is discovered by
:func:`dispatch_due_reminders_for_all_organizations`, called on a timer by
``scheduler.py``, which loops every active organization and asks the
registered :class:`~app.platform.notifications.policies.ReminderSource`
(implemented by the CRM, registered by ``app/api/router.py``) what is due.

**Why polling in-process rather than the outbox.** The eventual design
(ADR-013) has every module publish events to a transactional outbox,
dispatched by an ARQ worker. Neither exists yet — no module's ``events.py`` is
implemented, and ``app.core.redis`` explicitly scopes itself to "connection
management and a health probe only" until a later phase — so building the
general outbox as a prerequisite for this one feature would mean doing Phase 4
(``P4-W26``) in order to ship Phase A. Two things make in-process polling the
honest interim choice rather than a shortcut, matching how
``app.platform.audit.service`` reasons about running synchronously ahead of
its own eventual event flow:

* **The deployment is one replica.** ``railway.json`` pins ``numReplicas: 1``,
  and ``scripts/start.sh`` already relies on that same fact to run migrations
  from the entrypoint rather than a separate release step. A single in-process
  polling task cannot double-fire across replicas that do not exist. The
  comment on both files says to revisit if that ever changes; this one does
  too.
* **The state that matters is durable, only the trigger loop is not.** Which
  reminders have already fired lives in ``platform.notifications`` (the
  dedupe key), in PostgreSQL. A restart loses at most one poll interval of
  timeliness, never a reminder — the next tick sees the same due row and finds
  it already deduplicated, or not yet notified and creates it.

Moving :func:`dispatch_due_reminders_for_all_organizations` onto an ARQ cron
job is a drop-in replacement once the worker exists: nothing about its
signature or the ``ReminderSource`` contract depends on how it is scheduled.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable, Sequence
from typing import Final

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.database import provisioning_scope
from app.core.exceptions import NotFoundError
from app.core.ids import uuid7
from app.core.pagination import PageParams
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import AuditService, audit_for_session
from app.platform.auth.dependencies import Principal
from app.platform.email.service import request_email
from app.platform.email.templates import NOTIFICATION
from app.platform.notifications.models import Notification
from app.platform.notifications.policies import (
    NullReminderSource,
    ReminderDue,
    ReminderSource,
)
from app.platform.notifications.repository import NotificationRepository
from app.platform.organizations.models import Organization, OrganizationStatus
from app.platform.organizations.service import organizations_for_session

logger = structlog.get_logger(__name__)

MODULE: Final = "notifications"
ENTITY_TYPE: Final = "NOTIFICATION"


class NotificationService:
    """A recipient's own notifications, plus the write path other modules use."""

    def __init__(
        self, repository: NotificationRepository, *, audit: AuditService | None = None
    ) -> None:
        self._repository = repository
        self._audit = audit or audit_for_session(repository.session)

    # --- The read/write a person's own mailbox uses -------------------------

    async def list_for_recipient(
        self, principal: Principal, *, params: PageParams, unread_only: bool = False
    ) -> tuple[Sequence[Notification], int]:
        return await self._repository.list_for_recipient(
            principal.organization_id,
            principal.user_id,
            params=params,
            unread_only=unread_only,
        )

    async def unread_count(self, principal: Principal) -> int:
        return await self._repository.unread_count(principal.organization_id, principal.user_id)

    async def mark_read(self, notification_id: uuid.UUID, principal: Principal) -> Notification:
        notification = await self._repository.get(
            notification_id, principal.organization_id, principal.user_id
        )
        if notification is None:
            # Another recipient's notification and one that does not exist
            # are indistinguishable here, for the same reason a record from
            # another tenant is: confirming which one it was would leak that
            # something exists for someone else.
            raise NotFoundError("Notification not found.")
        if notification.is_read:
            return notification
        return await self._repository.mark_read(notification)

    async def mark_all_read(self, principal: Principal) -> int:
        """Mark every unread notification read. Returns how many changed."""
        return await self._repository.mark_all_read(principal.organization_id, principal.user_id)

    # --- The write other modules use (record assignment, etc.) -------------

    async def notify(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        kind: str,
        title: str,
        body: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        email: bool = False,
        record_path: str | None = None,
    ) -> Notification:
        """Raise a notification for one recipient, in the caller's transaction.

        ``email`` also sends the notification's email twin — its title and body
        through the ``notification`` template, linked to ``record_path`` — via
        the outbox and so via Microsoft Graph. Opt-in per call, for the reason
        ``ReminderDue.email_template`` is: an email is an interruption, so only
        the events the roadmap names as worth one ask for it. The email joins
        the outbox in this transaction, and a failure to request it is logged
        rather than raised, so a missing directory entry never costs the
        business action that raised the notification.

        Direct calls (as opposed to reminders — see
        :func:`dispatch_due_reminders_for_all_organizations`) are never
        deduplicated: each call is a distinct thing that happened, the same
        way each ``AuditAction.CREATED`` entry is distinct even when two
        records are created a second apart.

        Audited as a system action worth a trail entry — *who was told what,
        and why* — the same reasoning ``ATTACHMENT_DOWNLOADED`` uses for
        recording a read rather than only a write. Marking a notification
        read is deliberately **not** audited: it is a UI toggle with no
        business consequence, the same category ``updated_at`` bumps are
        excluded from audit diffs for (``TenantScopedService._audit_snapshot``).
        """
        notification = Notification(
            organization_id=organization_id,
            recipient_user_id=recipient_user_id,
            kind=kind,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        await self._repository.add(notification)
        await self._audit.record(
            organization_id=organization_id,
            action=AuditAction.CREATED,
            module=MODULE,
            entity_type=ENTITY_TYPE,
            entity_id=notification.id,
            entity_label=title,
            actor_id=actor_id,
            details={
                "recipient_user_id": str(recipient_user_id),
                "kind": kind,
                "email": email,
            },
        )
        if email:
            await self._request_recipient_email(
                organization_id=organization_id,
                recipient_user_id=recipient_user_id,
                kind=kind,
                template=NOTIFICATION,
                context={"title": title, "message": body or title},
                record_path=record_path,
            )
        return notification

    # --- Reminders -----------------------------------------------------

    async def dispatch_due_reminders(self, *, organization_id: uuid.UUID, now: dt.datetime) -> int:
        """Fire every due reminder for one organization. Returns how many are new.

        Reads through the registered :class:`ReminderSource` and writes
        through :meth:`NotificationRepository.create_deduplicated`, so a
        reminder already fired for its dedupe key is silently skipped rather
        than raising. No audit entry is written here for the reminders that
        turn out to be duplicates — only for the ones actually created,
        matching :meth:`notify`.
        """
        source = get_reminder_source(self._repository.session)
        due = await source.due_reminders(
            self._repository.session, organization_id=organization_id, now=now
        )

        created = 0
        for reminder in due:
            notification = Notification(
                # UUIDPrimaryKeyMixin's default only runs on an ORM flush;
                # create_deduplicated writes through a Core INSERT instead
                # (see its docstring), so the id has to be generated here —
                # the same client-side id ``app.core.ids`` documents itself
                # as existing for.
                id=uuid7(),
                organization_id=organization_id,
                recipient_user_id=reminder.recipient_user_id,
                kind=reminder.kind,
                title=reminder.title,
                body=reminder.body,
                entity_type=reminder.entity_type,
                entity_id=reminder.entity_id,
                dedupe_key=reminder.dedupe_key,
            )
            inserted = await self._repository.create_deduplicated(notification)
            if not inserted:
                continue
            created += 1
            # After the insert, and only for a *new* notification. The dedupe
            # key is what makes a reminder fire once; hanging the email off
            # the same branch means a tick that finds the same meeting again
            # re-sends nothing, which is the property that matters most for
            # something arriving in an inbox.
            await self._request_reminder_email(
                reminder, organization_id=organization_id
            )
            await self._audit.record(
                organization_id=organization_id,
                action=AuditAction.CREATED,
                module=MODULE,
                entity_type=ENTITY_TYPE,
                entity_id=notification.id,
                entity_label=reminder.title,
                details={
                    "recipient_user_id": str(reminder.recipient_user_id),
                    "kind": reminder.kind,
                    "reminder_entity_type": reminder.entity_type,
                    "reminder_entity_id": str(reminder.entity_id),
                },
            )
        return created

    async def _request_reminder_email(
        self, reminder: ReminderDue, *, organization_id: uuid.UUID
    ) -> None:
        """Enqueue the email for a reminder that asked for one.

        Enqueued, not sent: this runs inside the scheduler's transaction, so
        the message joins the outbox alongside the notification row and both
        commit or neither does. A reminder that rolled back must not leave an
        email behind saying it happened.

        Every failure here is swallowed with a log rather than raised. The
        reminder itself has already been created and audited, and a directory
        lookup that comes back empty — a member removed between the meeting
        being scheduled and its reminder falling due — is not a reason to
        abandon the rest of the organization's tick.
        """
        if reminder.email_template is None:
            return
        await self._request_recipient_email(
            organization_id=organization_id,
            recipient_user_id=reminder.recipient_user_id,
            kind=reminder.kind,
            template=reminder.email_template,
            context=dict(reminder.email_context),
            record_path=reminder.record_path,
        )

    async def _request_recipient_email(
        self,
        *,
        organization_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        kind: str,
        template: str,
        context: dict[str, str],
        record_path: str | None,
    ) -> None:
        """Enqueue a notification or reminder email to one member.

        The recipient's address is looked up in the organization's member
        directory at request time, never taken from the caller, so a product
        cannot address a notification email to somebody outside the tenant.
        Every failure is logged and swallowed; see the callers for why.
        """
        try:
            directory = await organizations_for_session(
                self._repository.session
            ).member_directory(organization_id, {recipient_user_id})
            identity = directory.get(recipient_user_id)
            if identity is None:
                # Not a member any more, so not somebody to email. The in-app
                # notification is already written and will simply not be read.
                logger.info(
                    "notification_email_skipped_unknown_recipient",
                    recipient_user_id=str(recipient_user_id),
                )
                return

            base = get_settings().public_app_url.rstrip("/")
            full_context: dict[str, str] = {
                **context,
                # Applied *after* the product's fields, so a product cannot
                # redirect the greeting or the link by supplying its own.
                "recipient_name": identity.full_name or identity.email,
                "record_url": f"{base}{record_path}" if record_path is not None else base,
            }
            request_email(
                self._repository.session,
                organization_id=organization_id,
                to_address=identity.email,
                template=template,
                context=full_context,
            )
        except Exception:  # an email must not cost the notification
            logger.exception(
                "notification_email_could_not_be_requested",
                kind=kind,
                organization_id=str(organization_id),
            )


def notifications_for_session(session: AsyncSession) -> NotificationService:
    """Build a :class:`NotificationService` bound to an existing session."""
    return NotificationService(NotificationRepository(session))


# --- Reminder-source registry (see policies.py) -----------------------------
#
# Same shape as ``app.platform.documents.router.register_entity_access``: a
# module-level global set once, at import time, by the composition root
# (``app/api/router.py``). It lives here rather than in ``router.py`` because
# nothing that consumes it runs inside an HTTP request — the scheduler calls
# ``NotificationService.dispatch_due_reminders``, which is the service layer.

ReminderSourceFactory = Callable[[], ReminderSource]

_reminder_source_factory: ReminderSourceFactory | None = None


def register_reminder_source(factory: ReminderSourceFactory) -> None:
    """Register the product implementation of :class:`ReminderSource`.

    Called by ``app/api/router.py`` at import time. Idempotent by nature —
    registering the same factory twice is harmless.
    """
    global _reminder_source_factory
    _reminder_source_factory = factory


def get_reminder_source(session: AsyncSession) -> ReminderSource:
    """The registered reminder source, or one that finds nothing.

    ``session`` is accepted (and unused by the factory call itself) so this
    has the same shape as ``documents.router.get_entity_access`` and so a
    future source that *does* need per-request construction is a
    non-breaking change here.
    """
    if _reminder_source_factory is None:
        return NullReminderSource()
    return _reminder_source_factory()


# --- Cross-organization dispatch, called by scheduler.py --------------------


async def dispatch_due_reminders_for_all_organizations(
    session_factory: async_sessionmaker[AsyncSession], *, now: dt.datetime | None = None
) -> int:
    """Fire due reminders across every active organization. Returns the total created.

    Organizations are read with no tenant context at all — ``platform.
    organizations`` carries no ``organization_id`` of its own (it *is* the
    tenant) and no RLS policy, the same reason
    ``DatabaseMembershipVerifier`` reads ``organization_memberships`` outside
    any tenant scope.

    Each organization then gets its own transaction, scoped to it with
    :func:`app.core.database.provisioning_scope` — the mechanism that already
    exists for exactly this class of write: a system operation that names a
    tenant before (here: without) a request has established one. One
    organization's error is logged and does not stop the rest — a scheduler
    tick failing for every remaining tenant because one had a bad row would
    be a worse outage than a single organization's reminders arriving one
    tick late.
    """
    when = now or dt.datetime.now(dt.UTC)
    total = 0

    async with session_factory() as scan_session:
        organization_ids = (
            (
                await scan_session.execute(
                    select(Organization.id).where(
                        Organization.status == OrganizationStatus.ACTIVE,
                        Organization.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

    for organization_id in organization_ids:
        try:
            async with (
                session_factory() as session,
                session.begin(),
                provisioning_scope(session, organization_id),
            ):
                service = notifications_for_session(session)
                total += await service.dispatch_due_reminders(
                    organization_id=organization_id, now=when
                )
        except Exception:  # one tenant's failure must not sink the tick
            logger.exception(
                "reminder_dispatch_failed_for_organization",
                organization_id=str(organization_id),
            )

    return total


__all__ = [
    "MODULE",
    "NotificationService",
    "ReminderSourceFactory",
    "dispatch_due_reminders_for_all_organizations",
    "get_reminder_source",
    "notifications_for_session",
    "register_reminder_source",
]
