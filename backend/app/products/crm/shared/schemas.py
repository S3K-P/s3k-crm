"""Contract fragments shared by every CRM record schema.

Small on purpose. Only shapes that must be *identical* across entities belong
here — where a difference between accounts and leads would be a bug rather than
a design choice.

Lives in ``shared`` for the same boundary reason ``pagination`` does: five
entity schema modules need this type, and a module importing a sibling's
``schemas.py`` would make the five depend on ``custom_fields`` rather than on
the platform beneath them. ``custom_fields.schemas`` re-exports it, so both
import paths name the same object and the wire format is provably one thing.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

#: The most custom values one request may carry.
#:
#: Matched to the per-entity field limit in
#: ``custom_fields.models.MAX_FIELDS_PER_ENTITY``. Restated rather than
#: imported, because importing it here would reintroduce exactly the dependency
#: this module exists to avoid; the two are asserted equal by a unit test, which
#: is a better guarantee than an import that a refactor could quietly redirect.
MAX_CUSTOM_FIELD_VALUES = 200

#: A record's tenant-defined values, as they appear on the wire.
#:
#: ``dict[str, Any]`` rather than a generated model: the keys are tenant data,
#: so there is no static shape to declare. Every value is validated against the
#: organization's own field definitions inside
#: :class:`~app.products.crm.shared.service.TenantScopedService`, which is the
#: only place that can — it needs a database. What is enforced *here* is only
#: what is enforceable without one: that it is a JSON object, and that it is
#: not unboundedly large.
#:
#: On a create or update this is optional and ``None`` means "not supplied",
#: which is materially different from ``{}``. ``{}`` clears every custom value;
#: ``None`` leaves the document exactly as it was. A PATCH of one built-in
#: column must be able to say the second, or editing an account's phone number
#: would wipe its custom fields.
CustomFieldValues = Annotated[dict[str, Any], Field(max_length=MAX_CUSTOM_FIELD_VALUES)]


class BulkOperationFailure(BaseModel):
    """One record a bulk operation (Checkpoint 4) could not change, and why.

    ``reason`` is the same message the single-record endpoint would have
    returned for this id — permission denied, not found/visible, a validation
    failure, a business rule. A bulk endpoint never reduces an error to a
    generic "failed"; the point of reporting per-record is that the caller can
    fix exactly what is wrong with exactly the records that need it.
    """

    id: uuid.UUID
    reason: str


class BulkOperationResult(BaseModel):
    """What a bulk update/delete/status-change actually did, record by record.

    Never all-or-nothing: each id is processed independently — see
    :meth:`app.products.crm.shared.service.TenantScopedService.bulk_update` —
    so one invalid row cannot block the rows around it, and the caller is told
    exactly which succeeded and which did not, never left to guess from a
    single pass/fail flag. This is the same "no silent partial modification"
    guarantee the CSV importer already gives (``imports/schemas.ImportResult``);
    reusing its shape here is deliberate; nothing about a partial result is
    hidden.
    """

    succeeded: list[uuid.UUID]
    failed: list[BulkOperationFailure]

    @property
    def succeeded_count(self) -> int:
        return len(self.succeeded)

    @property
    def failed_count(self) -> int:
        return len(self.failed)


class BulkIdsRequest(BaseModel):
    """The ids a bulk operation applies to."""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class TimelineEntryResponse(BaseModel):
    """One event in a record's unified timeline (Checkpoint 3).

    The wire shape for ``app.products.crm.shared.timeline.TimelineEntry``,
    reused by every module that exposes a merged timeline — accounts,
    contacts, opportunities — so the frontend has exactly one entry shape to
    render regardless of which record it is looking at.
    """

    model_config = ConfigDict(from_attributes=True)

    kind: str
    occurred_at: dt.datetime
    title: str
    detail: str | None
    entity_type: str
    entity_id: uuid.UUID


__all__ = [
    "MAX_CUSTOM_FIELD_VALUES",
    "BulkIdsRequest",
    "BulkOperationFailure",
    "BulkOperationResult",
    "CustomFieldValues",
    "TimelineEntryResponse",
]
