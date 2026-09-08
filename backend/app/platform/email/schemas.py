"""Pydantic contracts for the delivery log.

The absent field is the interesting one: there is no message body here, because
there is none in the table either. ``app.platform.email.models`` sets out why —
a reset link stored where administrators can read it would turn the log into a
way to take a colleague's account over.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict

from app.platform.email.models import EmailDeliveryStatus


class EmailDeliveryResponse(BaseModel):
    """One attempt, as an administrator sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    to_address: str
    subject: str
    template: str
    status: EmailDeliveryStatus
    provider: str
    provider_message_id: str | None = None
    #: Why it failed, verbatim from the provider. Shown because "failed" with
    #: no reason leaves an administrator with nothing to do about it.
    error: str | None = None
    created_at: dt.datetime
    sent_at: dt.datetime | None = None


class EmailDeliverySummaryResponse(BaseModel):
    """Counts by state, plus the filter values worth offering."""

    #: Keyed by status name so the shape survives a new status being added.
    counts: dict[str, int]
    templates: list[str]


__all__ = ["EmailDeliveryResponse", "EmailDeliverySummaryResponse"]
