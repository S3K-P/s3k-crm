"""Resolving CRM record access for the Platform documents module.

Implements ``app.platform.documents.service.EntityAccessVerifier``. The
documents module owns the attachment table and the storage client but cannot
answer *may this caller see the account this file hangs off* — that depends on
``owner_id`` and on the caller's ``VIEW_ALL`` grant, both of which are CRM
concepts. ARCHITECTURE-BOUNDARIES.md rule 1 forbids Platform from importing a
product and prescribes exactly this inversion, so the answer is computed here
and injected by the composition root.

**Nothing new is decided in this file.** It reuses ``RecordVisibility`` — the
same predicate every CRM list and detail endpoint applies — rather than
re-deriving what "may see" means. That is deliberate: a second implementation
of record-level visibility would be a second thing to keep correct, and the
first time the two disagreed, attachments would become the way around the
control. The type-to-module mapping below is the only new information, and it
is a mapping, not a rule.

The read is a dedicated cross-module read model in the sense
ARCHITECTURE-BOUNDARIES.md rule 6 permits: it reads across the five CRM entity
tables and writes nothing, so no module's invariants can be bypassed through it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.platform.documents.service import EntityAccess
from app.products.crm.accounts.models import Account
from app.products.crm.campaigns.models import Campaign
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead
from app.products.crm.opportunities.models import Opportunity
from app.products.crm.shared.visibility import RecordVisibility


@dataclass(frozen=True, slots=True)
class _AttachableEntity:
    """How one CRM entity type answers the three questions attachments ask."""

    model: type[Any]
    #: Permission module, for both the ``EDIT`` check and the visibility rule.
    module: str
    #: Attributes tried in order when naming the record for the audit trail.
    label_attributes: tuple[str, ...]


#: The CRM records a file may be attached to.
#:
#: Keyed by ``CrmEntityType`` so the vocabulary is the one activities, tasks
#: and notes already use for their polymorphic links — an attachment points at
#: a record the same way a note does, and inventing a second spelling would
#: guarantee they drift.
#:
#: Anything absent is simply not attachable, and resolves to denied rather than
#: to an error. Tasks and notes are deliberately absent: they are themselves
#: children of a record, and a file belongs on the record, not on a note about
#: it.
ATTACHABLE: Final[dict[str, _AttachableEntity]] = {
    CrmEntityType.ACCOUNT.value: _AttachableEntity(Account, "accounts", ("name",)),
    CrmEntityType.CONTACT.value: _AttachableEntity(
        Contact, "contacts", ("full_name", "email")
    ),
    CrmEntityType.LEAD.value: _AttachableEntity(Lead, "leads", ("full_name", "email")),
    CrmEntityType.OPPORTUNITY.value: _AttachableEntity(
        Opportunity, "opportunities", ("name",)
    ),
    CrmEntityType.CAMPAIGN.value: _AttachableEntity(Campaign, "campaigns", ("name",)),
}


class CrmEntityAccess:
    """Answers attachment authorization questions about CRM records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self, *, principal: Principal, entity_type: str, entity_id: uuid.UUID
    ) -> EntityAccess:
        """What ``principal`` may do with one CRM record.

        One query, with the record-level visibility predicate applied **in
        SQL** rather than evaluated afterwards. A record the caller may not see
        therefore returns no row at all, which is indistinguishable from one
        that does not exist — the same answer the CRM's own detail endpoints
        give, and the reason attachments cannot be used to probe for records.

        Never raises: an unknown entity type and a missing record are both
        ordinary conditions on this path and both resolve to denied.
        """
        attachable = ATTACHABLE.get(entity_type)
        if attachable is None:
            return EntityAccess.denied()

        record = (
            await self._session.execute(
                self._visible_query(attachable, entity_id, principal)
            )
        ).scalar_one_or_none()
        if record is None:
            return EntityAccess.denied()

        # Attaching or removing a file changes the record's contents, so it
        # takes EDIT on that module — not merely the ability to read it.
        can_edit = principal.has_permission(attachable.module, PermissionAction.EDIT)
        return EntityAccess(
            can_view=True, can_edit=can_edit, label=_label(record, attachable)
        )

    def _visible_query(
        self,
        attachable: _AttachableEntity,
        entity_id: uuid.UUID,
        principal: Principal,
    ) -> Select[tuple[Any]]:
        model = attachable.model
        statement = select(model).where(
            model.id == entity_id,
            model.organization_id == principal.organization_id,
            model.deleted_at.is_(None),
        )
        visibility = RecordVisibility.for_module(principal, attachable.module)
        predicate = visibility.filter_for(model)
        if predicate is not None:
            statement = statement.where(predicate)
        return statement


def _label(record: Any, attachable: _AttachableEntity) -> str | None:
    for attribute in attachable.label_attributes:
        value = getattr(record, attribute, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def crm_entity_access(session: AsyncSession) -> CrmEntityAccess:
    """Factory the composition root hands to the attachments router."""
    return CrmEntityAccess(session)


__all__ = ["ATTACHABLE", "CrmEntityAccess", "crm_entity_access"]
