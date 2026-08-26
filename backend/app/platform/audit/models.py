"""SQLAlchemy models for the audit module (doc 04 "AuditLog", doc 09).

One table, ``platform.audit_logs``, holding the compliance and security trail
for every organization. Three properties define it, and each is enforced by the
database rather than by convention:

**Tenant-scoped.** It carries ``organization_id`` and its migration enables and
FORCEs the same RLS policy every other tenant table gets, so one organization's
administrator can never read another's trail — see :mod:`app.core.rls`.

**Append-only.** A ``BEFORE UPDATE OR DELETE OR TRUNCATE`` trigger raises. That
is deliberately stronger than merely withholding an UPDATE policy: RLS is
ignored by superusers and ``BYPASSRLS`` roles, a trigger is not. An audit trail
the application can quietly rewrite is not evidence of anything.

**Actor by reference, not by copy.** ``actor_id`` carries no foreign key —
audit history must outlive the user row, exactly as ``AuthorshipMixin``
explains — and the actor's address is resolved at read time rather than
denormalised, so the trail cannot drift from the directory.

``details`` is the free-form payload doc 04 calls ``metadata``. It is renamed
because ``metadata`` is reserved on a SQLAlchemy declarative class and cannot
be used as a mapped attribute name. Everything written into it passes through
:mod:`app.platform.audit.redaction` first.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import DateTime, Enum, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, UUIDPrimaryKeyMixin

PLATFORM_SCHEMA = "platform"

#: Name of the trigger that makes the table append-only. Referenced by the
#: migration that creates it and by the tests that prove it still bites.
APPEND_ONLY_TRIGGER = "audit_logs_append_only"


class AuditStatus(enum.StrEnum):
    """Outcome of the audited attempt (doc 04 ``AuditStatus``).

    ``DENIED`` is kept separate from ``FAILURE`` because the two mean different
    things to whoever reads the trail: a denial is the authorization layer
    working, a failure is the action being attempted and not completing.
    """

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    DENIED = "DENIED"


class AuditAction(enum.StrEnum):
    """The vocabulary written into ``audit_logs.action``.

    Stored as text rather than a database enum on purpose: a newly audited
    action must not require an ``ALTER TYPE`` and a coordinated deploy, and an
    unrecognised value read back from an older row must still render. This enum
    is the *writer* side — the set of actions this codebase emits — while the
    column's contract is only "a short, stable, uppercase identifier".
    """

    # --- Authentication ----------------------------------------------------
    LOGIN_SUCCEEDED = "LOGIN_SUCCEEDED"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGIN_BLOCKED = "LOGIN_BLOCKED"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    LOGOUT = "LOGOUT"
    # The three suppressions below are bandit false positives: S105 matches on
    # the member *name* containing TOKEN/PASSWORD. These are action identifiers,
    # and the one thing this module guarantees is that no credential is ever
    # stored — see app.platform.audit.redaction.
    TOKEN_REUSE_DETECTED = "TOKEN_REUSE_DETECTED"  # noqa: S105
    PASSWORD_CHANGED = "PASSWORD_CHANGED"  # noqa: S105
    PASSWORD_RESET_BY_ADMIN = "PASSWORD_RESET_BY_ADMIN"  # noqa: S105

    # --- Record lifecycle --------------------------------------------------
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"

    # --- Access control ----------------------------------------------------
    ROLE_ASSIGNED = "ROLE_ASSIGNED"
    ROLE_REVOKED = "ROLE_REVOKED"
    MEMBER_ADDED = "MEMBER_ADDED"
    MEMBER_STATUS_CHANGED = "MEMBER_STATUS_CHANGED"
    USER_PROVISIONED = "USER_PROVISIONED"

    # --- Attachments -------------------------------------------------------
    #
    # Downloads are audited as well as writes: a pre-signed URL is a bearer
    # credential and the storage layer's own logs are neither tenant-scoped nor
    # visible to an organization's administrator, so this is the only record of
    # who read which file (doc 13, "Data Access Control").
    ATTACHMENT_UPLOADED = "ATTACHMENT_UPLOADED"
    ATTACHMENT_DOWNLOADED = "ATTACHMENT_DOWNLOADED"
    ATTACHMENT_DELETED = "ATTACHMENT_DELETED"

    # --- Teams and departments ---------------------------------------------
    #
    # Membership changes are audited as carefully as permission changes,
    # because they have the same effect: moving somebody onto a team widens
    # what they can read, through ``VIEW_TEAM``, without touching a role.
    DEPARTMENT_CREATED = "DEPARTMENT_CREATED"
    DEPARTMENT_UPDATED = "DEPARTMENT_UPDATED"
    DEPARTMENT_DELETED = "DEPARTMENT_DELETED"
    TEAM_CREATED = "TEAM_CREATED"
    TEAM_UPDATED = "TEAM_UPDATED"
    TEAM_DELETED = "TEAM_DELETED"
    TEAM_MEMBER_ADDED = "TEAM_MEMBER_ADDED"
    TEAM_MEMBER_REMOVED = "TEAM_MEMBER_REMOVED"

    # --- CRM state transitions ---------------------------------------------
    LEAD_STATUS_CHANGED = "LEAD_STATUS_CHANGED"
    LEAD_CONVERTED = "LEAD_CONVERTED"
    OPPORTUNITY_STAGE_CHANGED = "OPPORTUNITY_STAGE_CHANGED"
    OPPORTUNITY_REOPENED = "OPPORTUNITY_REOPENED"
    OWNER_REASSIGNED = "OWNER_REASSIGNED"


class AuditLog(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """One recorded action.

    Deliberately **not** built from ``TimestampMixin``, ``AuthorshipMixin`` or
    ``SoftDeleteMixin``: an append-only row has no ``updated_at`` to maintain,
    no ``updated_by_id`` that could ever be set, and archiving an audit record
    rather than keeping it would defeat the point of having one.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        # Reverse-chronological browse: the view the screen opens on.
        Index("ix_audit_logs_organization_id_created_at", "organization_id", "created_at"),
        # "What did this person do?"
        Index(
            "ix_audit_logs_organization_id_actor_id_created_at",
            "organization_id",
            "actor_id",
            "created_at",
        ),
        # "What happened to this record?" — including entity_id is what makes a
        # single record's history an index scan rather than a filtered sort.
        Index(
            "ix_audit_logs_organization_id_entity_created_at",
            "organization_id",
            "entity_type",
            "entity_id",
            "created_at",
        ),
        # "Show me every failed sign-in", "every deletion".
        Index(
            "ix_audit_logs_organization_id_action_created_at",
            "organization_id",
            "action",
            "created_at",
        ),
        Index(
            "ix_audit_logs_organization_id_module_created_at",
            "organization_id",
            "module",
            "created_at",
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    #: Who acted. ``NULL`` only for an action the system took on nobody's
    #: behalf (provisioning, scheduled work) — never for a user request.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    #: Short, stable identifier — see :class:`AuditAction`.
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The permission module the action belongs to, e.g. ``leads``, ``roles``.
    #: Matches ``PERMISSION_MODULES`` so the trail and the RBAC vocabulary line
    #: up, plus ``auth`` for sign-in events, which are not permission-gated.
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The kind of record acted on, e.g. ``LEAD``. ``NULL`` for actions with no
    #: record subject, such as a failed sign-in.
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    #: Human-readable name of the subject *as it was when the action happened*,
    #: so the trail still reads sensibly after the record is renamed or purged.
    entity_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus, name="audit_status", schema=PLATFORM_SCHEMA, native_enum=True),
        nullable=False,
        default=AuditStatus.SUCCESS,
        server_default=AuditStatus.SUCCESS.value,
    )
    #: Correlation id of the request, from :mod:`app.core.request_context`.
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: Redacted, JSON-safe detail: field diffs, transition endpoints, reasons.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "APPEND_ONLY_TRIGGER",
    "PLATFORM_SCHEMA",
    "AuditAction",
    "AuditLog",
    "AuditStatus",
]
