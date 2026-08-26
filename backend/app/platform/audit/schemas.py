"""Pydantic v2 schemas for the audit module.

The ORM row is never returned directly. Two fields on it are joined in rather
than stored — the actor's address and display name — and one, ``details``, is
free-form JSON whose shape depends on the action, so the wire contract is
declared explicitly here rather than inferred from the table.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, Field

from app.platform.audit.models import AuditStatus
from app.platform.audit.service import AuditEntryView


class AuditLogResponse(BaseModel):
    """One row of the trail, as the admin screen renders it."""

    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: dt.datetime

    actor_id: uuid.UUID | None
    #: Joined from ``platform.users`` at read time. ``None`` when the action
    #: had no actor, or when the identity has since been removed — the record
    #: itself survives either way.
    actor_email: str | None
    actor_name: str | None

    action: str
    module: str
    status: AuditStatus

    entity_type: str | None
    entity_id: uuid.UUID | None
    entity_label: str | None

    request_id: str | None
    ip_address: str | None
    user_agent: str | None
    #: Redacted on the way in — see ``app.platform.audit.redaction``.
    details: dict[str, object] | None

    @classmethod
    def from_view(cls, view: AuditEntryView) -> AuditLogResponse:
        entry = view.entry
        return cls(
            id=entry.id,
            organization_id=entry.organization_id,
            created_at=entry.created_at,
            actor_id=entry.actor_id,
            actor_email=view.actor_email,
            actor_name=view.actor_name,
            action=entry.action,
            module=entry.module,
            status=entry.status,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            entity_label=entry.entity_label,
            request_id=entry.request_id,
            ip_address=entry.ip_address,
            user_agent=entry.user_agent,
            details=entry.details,
        )


class AuditFilterOptionsResponse(BaseModel):
    """What the filter controls should offer for *this* organization.

    Derived from the tenant's own rows rather than from the writer enum, so the
    dropdowns never offer a choice that can only return an empty table — and so
    one organization's list of actions tells another organization nothing.
    """

    actions: list[str] = Field(description="Actions present in this trail.")
    entity_types: list[str] = Field(description="Entity types present in this trail.")
    statuses: list[str] = Field(description="Every outcome the system records.")
    recording_since: dt.datetime | None = Field(
        default=None,
        description=(
            "Timestamp of the oldest retained record, so an empty result can be "
            "told apart from a trail that simply does not reach that far back."
        ),
    )


__all__ = ["AuditFilterOptionsResponse", "AuditLogResponse"]
