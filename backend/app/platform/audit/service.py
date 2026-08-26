"""Use cases for the audit module — the public interface every writer uses.

This module is the audit module's whole API. Other modules call
:meth:`AuditService.record` (or the convenience wrappers below) and never touch
``audit.repository`` or ``audit.models``; product code reaches it through
:func:`audit_for_session`, which is why CRM never has to import a Platform
internal (ARCHITECTURE-BOUNDARIES.md rule 2).

Three design decisions are worth stating, because each was a fork in the road.

**Audit writes commit with the action they describe.** A successful business
action appends its record inside the request's own transaction. If the change
rolls back, so does the claim that it happened. The plan (`P1-W08-BE-05`) calls
for routing writes through ARQ so they never block the request; that is a
throughput optimisation and it trades this atomicity for it — a queued record
is lost if the queue is down, and a queued record can describe a transaction
that later failed. No ARQ worker exists yet (`P1-W08-BE-04` is unstarted), so
the synchronous path is what runs. It is one INSERT on an append-only table.

**Failure paths write out of band.** A rejected sign-in raises, and raising
rolls the request transaction back — which would discard the very record
proving the attempt happened. :meth:`record_out_of_band` therefore commits
through an independent session, the same technique
``AuthService._register_failure`` already uses for lockout bookkeeping.

**The tenant setting is applied, never bypassed.** ``audit_logs`` is under the
same RLS policy as every other tenant table, and some writers legitimately run
before a tenant context exists — a sign-in is not scoped to an organization
until the organization has been resolved. :meth:`_ensure_scope` therefore sets
``app.current_org_id`` for the transaction *when it is unset*, and refuses when
it is set to a different organization. That is the opposite of a bypass: the
value is server-derived, it is the same value RLS checks, and a mismatch — the
one case that could actually cross a tenant boundary — is a hard error.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import ColumnElement, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AppError, NotFoundError
from app.core.models import TENANT_SETTING
from app.core.pagination import PageParams
from app.core.request_context import RequestContext, get_request_context
from app.platform.audit.models import AuditAction, AuditLog, AuditStatus
from app.platform.audit.redaction import diff, redact
from app.platform.audit.repository import AuditRepository
from app.platform.auth.repository import AuthRepository

logger = structlog.get_logger(__name__)

#: Re-exported so a caller names an action without importing ``audit.models``.
Action = AuditAction
Status = AuditStatus

#: Module recorded for authentication events. Sign-in is not permission-gated,
#: so it has no entry in ``PERMISSION_MODULES``; naming it explicitly keeps the
#: column's meaning ("which area of the system") true for every row.
AUTH_MODULE = "auth"


class AuditScopeError(AppError):
    """An audit record was about to be written outside its own tenant scope.

    Raised rather than recovered from. Reaching this means a transaction
    already scoped to organization A tried to record an action belonging to
    organization B, which is either a bug in a service signature or an attempt
    to cross a tenant boundary. Both must stop the request.
    """

    code = "audit_scope_mismatch"
    message = "An audit record could not be attributed to the correct organization."


@dataclass(frozen=True, slots=True)
class AuditEntryView:
    """One audit record with its actor resolved for display.

    The actor's address is joined at read time rather than copied into the row
    (see ``models.AuditLog``), so this pairing happens here instead of in the
    table.
    """

    entry: AuditLog
    actor_email: str | None
    actor_name: str | None


class AuditService:
    """Recording and reading the tenant's audit trail."""

    def __init__(
        self,
        repository: AuditRepository,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._repository = repository
        # Only needed by :meth:`record_out_of_band`; absent in unit tests and
        # in callers that never audit a failure path.
        self._session_factory = session_factory

    # --- Writing -----------------------------------------------------------

    async def record(
        self,
        *,
        organization_id: uuid.UUID,
        action: AuditAction | str,
        module: str,
        actor_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        entity_label: str | None = None,
        status: AuditStatus = AuditStatus.SUCCESS,
        details: Mapping[str, Any] | None = None,
        request: RequestContext | None = None,
    ) -> AuditLog:
        """Append one record inside the caller's transaction.

        Args:
            organization_id: the tenant the action belongs to. Always taken
                from the verified principal or from a server-side lookup —
                never from a request body.
            action: see :class:`~app.platform.audit.models.AuditAction`.
            module: the permission module, or ``auth`` for sign-in events.
            details: free-form context. Passed through
                :func:`~app.platform.audit.redaction.redact`, so a caller
                cannot store a credential here even by accident.
            request: correlation context; read from the contextvar when omitted.

        Raises:
            AuditScopeError: the transaction is scoped to another organization.
        """
        await self._ensure_scope(organization_id)

        context = request or get_request_context()
        entry = AuditLog(
            organization_id=organization_id,
            actor_id=actor_id,
            action=str(action),
            module=module,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=_clip(entity_label, 255),
            status=status,
            details=redact(details),
            request_id=context.request_id if context else None,
            ip_address=context.ip_address if context else None,
            user_agent=_clip(context.user_agent, 512) if context else None,
        )
        await self._repository.add(entry)
        logger.debug(
            "audit_recorded",
            action=str(action),
            module=module,
            organization_id=str(organization_id),
            status=status.value,
        )
        return entry

    async def record_change(
        self,
        *,
        organization_id: uuid.UUID,
        action: AuditAction,
        module: str,
        entity_type: str,
        entity_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        entity_label: str | None = None,
        before: Mapping[str, Any] | None = None,
        after: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> AuditLog | None:
        """Record a record-level change as a field diff.

        Returns ``None`` — writing nothing — when an update turns out to have
        changed no field. A PATCH that re-sends identical values is not an
        event, and recording it would bury the real ones.
        """
        details: dict[str, Any] = dict(extra or {})
        if before is not None and after is not None:
            changes = diff(before, after)
            if not changes and not details:
                return None
            details["changes"] = changes
        elif after is not None:
            details["values"] = dict(after)

        return await self.record(
            organization_id=organization_id,
            action=action,
            module=module,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label,
            details=details or None,
        )

    async def record_out_of_band(
        self,
        *,
        organization_id: uuid.UUID,
        action: AuditAction | str,
        module: str,
        actor_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        entity_label: str | None = None,
        status: AuditStatus = AuditStatus.FAILURE,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Commit a record through an independent session.

        For paths that raise immediately afterwards: the request transaction is
        rolled back and would take an in-transaction audit row with it.

        Never raises. This runs while an error is already being reported, and
        an audit failure must not replace the authentication error the caller
        is about to receive — that would turn a wrong password into a 500 and
        tell an attacker more, not less. A failure is logged at ``error`` so it
        is visible to monitoring.
        """
        if self._session_factory is None:
            logger.warning(
                "audit_out_of_band_skipped",
                reason="no independent session factory was supplied",
                action=str(action),
            )
            return

        context = get_request_context()
        try:
            async with self._session_factory() as session:
                await _apply_scope(session, organization_id)
                session.add(
                    AuditLog(
                        organization_id=organization_id,
                        actor_id=actor_id,
                        action=str(action),
                        module=module,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        entity_label=_clip(entity_label, 255),
                        status=status,
                        details=redact(details),
                        request_id=context.request_id if context else None,
                        ip_address=context.ip_address if context else None,
                        user_agent=_clip(context.user_agent, 512) if context else None,
                    )
                )
                await session.commit()
        except Exception as error:
            logger.error(
                "audit_write_failed",
                action=str(action),
                module=module,
                organization_id=str(organization_id),
                error=str(error),
            )

    # --- Reading -----------------------------------------------------------

    async def list_entries(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
    ) -> tuple[list[AuditEntryView], int]:
        """One page of the trail, with each actor resolved to a person.

        Authorization is the caller's responsibility and is enforced by the
        route (``audit.VIEW``); tenant scoping is enforced here *and* by RLS.
        """
        entries, total = await self._repository.list(
            organization_id, params=params, filters=filters
        )
        return await self._resolve_actors(entries), total

    async def get_entry(
        self, entry_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AuditLog:
        """One record from the caller's own trail.

        Raises:
            NotFoundError: unknown id, **or** an id belonging to another
                organization. Distinguishing the two would confirm that a
                record exists elsewhere.
        """
        entry = await self._repository.get(entry_id, organization_id)
        if entry is None:
            raise NotFoundError("Audit record not found.")
        return entry

    async def get_entry_view(
        self, entry_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AuditEntryView:
        """:meth:`get_entry` with the actor resolved, for the detail response."""
        entry = await self.get_entry(entry_id, organization_id)
        (view,) = await self._resolve_actors([entry])
        return view

    async def _resolve_actors(
        self, entries: Sequence[AuditLog]
    ) -> list[AuditEntryView]:
        """Pair each record with its actor in one batched directory read.

        One query for the whole page, not one per row: the trail is browsed in
        pages of 25 to 200 and the actors repeat heavily across them.
        """
        actor_ids = {entry.actor_id for entry in entries if entry.actor_id is not None}

        directory: dict[uuid.UUID, tuple[str | None, str | None]] = {}
        if actor_ids:
            users = await AuthRepository(self._repository.session).list_users(
                list(actor_ids)
            )
            for user in users:
                name = None
                if user.profile is not None:
                    name = f"{user.profile.first_name} {user.profile.last_name}".strip()
                directory[user.id] = (user.email, name or None)

        return [
            AuditEntryView(
                entry=entry,
                actor_email=directory.get(entry.actor_id, (None, None))[0]
                if entry.actor_id is not None
                else None,
                actor_name=directory.get(entry.actor_id, (None, None))[1]
                if entry.actor_id is not None
                else None,
            )
            for entry in entries
        ]

    async def filter_options(
        self, organization_id: uuid.UUID
    ) -> tuple[Sequence[str], Sequence[str], dt.datetime | None]:
        """Actions, entity types and trail start date present in this tenant."""
        return (
            await self._repository.distinct_actions(organization_id),
            await self._repository.distinct_entity_types(organization_id),
            await self._repository.earliest_entry_at(organization_id),
        )

    @staticmethod
    def build_filters(
        *,
        occurred_from: dt.datetime | None = None,
        occurred_to: dt.datetime | None = None,
        actor_id: uuid.UUID | None = None,
        action: str | None = None,
        module: str | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        status: AuditStatus | None = None,
    ) -> list[ColumnElement[bool]]:
        """Translate query parameters into SQL predicates.

        Every one of these is applied in the database, on top of the mandatory
        organization filter — nothing is narrowed in Python after the fact,
        which is what keeps a filtered page and its total count consistent.
        """
        filters: list[ColumnElement[bool]] = []
        if occurred_from is not None:
            filters.append(AuditLog.created_at >= occurred_from)
        if occurred_to is not None:
            filters.append(AuditLog.created_at <= occurred_to)
        if actor_id is not None:
            filters.append(AuditLog.actor_id == actor_id)
        if action:
            filters.append(AuditLog.action == action)
        if module:
            filters.append(AuditLog.module == module)
        if entity_type:
            filters.append(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            filters.append(AuditLog.entity_id == entity_id)
        if status is not None:
            filters.append(AuditLog.status == status)
        return filters

    # --- Internals ---------------------------------------------------------

    async def _ensure_scope(self, organization_id: uuid.UUID) -> None:
        """Make the transaction's tenant setting match the record being written.

        Sets it when unset — a sign-in has no tenant context until the
        organization is resolved — and refuses when it names a different
        organization. See the module docstring for why this is not a bypass.
        """
        session = self._repository.session
        current = (
            await session.execute(
                text("SELECT NULLIF(current_setting(:setting, true), '')"),
                {"setting": TENANT_SETTING},
            )
        ).scalar_one_or_none()

        if current is None:
            await _apply_scope(session, organization_id)
            return

        if uuid.UUID(str(current)) != organization_id:
            logger.error(
                "audit_scope_mismatch",
                transaction_organization_id=str(current),
                record_organization_id=str(organization_id),
            )
            raise AuditScopeError


async def _apply_scope(session: AsyncSession, organization_id: uuid.UUID) -> None:
    """Scope ``session``'s current transaction to ``organization_id``.

    ``set_config(..., is_local => true)`` is the callable form of ``SET
    LOCAL``: PostgreSQL discards it when the transaction ends, so a pooled
    connection cannot carry the scope into the next request.
    """
    await session.execute(
        text("SELECT set_config(:setting, :value, true)"),
        {"setting": TENANT_SETTING, "value": str(organization_id)},
    )


def _clip(value: str | None, length: int) -> str | None:
    if value is None:
        return None
    return value[:length] or None


def audit_for_session(
    session: AsyncSession,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> AuditService:
    """Build an :class:`AuditService` bound to an existing session.

    The seam product code uses. CRM imports this function and nothing else from
    the audit module, so it never names ``AuditRepository`` — which
    ARCHITECTURE-BOUNDARIES.md rule 2 forbids it from importing.
    """
    return AuditService(AuditRepository(session), session_factory=session_factory)


__all__ = [
    "AUTH_MODULE",
    "Action",
    "AuditEntryView",
    "AuditScopeError",
    "AuditService",
    "Status",
    "audit_for_session",
]
