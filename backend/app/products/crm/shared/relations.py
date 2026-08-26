"""Validation for polymorphic ``related_entity_type``/``related_entity_id`` links.

Activities, tasks and notes all point at "some CRM record" through a type/id
pair rather than a foreign key, because one column cannot reference five
tables. That flexibility removes the database's guarantee that the target
exists, so it has to be re-established here.

**The rule this module enforces:** a link may only point at a record that
exists *inside the caller's organization*. Without this check a caller could
attach a note to another tenant's account by guessing its id — the note row
itself would pass RLS (it carries the caller's own ``organization_id``), and
the dangling reference would leak the target's existence.

This is the "dedicated read model" ARCHITECTURE-BOUNDARIES.md rule 6 permits:
it reads across module tables but writes nothing, so no module's invariants can
be bypassed through it. It is deliberately the *only* place that does so for
these links, rather than each module growing its own copy.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.products.crm.accounts.models import Account
from app.products.crm.campaigns.models import Campaign
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead
from app.products.crm.opportunities.models import Opportunity


class UnknownRelatedEntityError(ValidationFailedError):
    """The link target does not exist in this organization.

    Deliberately indistinguishable from "no such record": an id belonging to
    another tenant and an id belonging to nobody must produce the same answer.
    """

    code = "unknown_related_entity"
    message = "The linked record does not exist."


def _selector(
    entity_type: CrmEntityType, entity_id: uuid.UUID, organization_id: uuid.UUID
) -> Select[tuple[uuid.UUID]]:
    """Build the existence query for one entity type, always org-scoped."""
    model: Final = {
        CrmEntityType.ACCOUNT: Account,
        CrmEntityType.CONTACT: Contact,
        CrmEntityType.LEAD: Lead,
        CrmEntityType.OPPORTUNITY: Opportunity,
        CrmEntityType.CAMPAIGN: Campaign,
    }[entity_type]

    return select(model.id).where(
        model.id == entity_id,
        model.organization_id == organization_id,
        model.deleted_at.is_(None),
    )


async def validate_related_entity(
    session: AsyncSession,
    *,
    entity_type: CrmEntityType | None,
    entity_id: uuid.UUID | None,
    organization_id: uuid.UUID,
) -> None:
    """Confirm a polymorphic link resolves inside ``organization_id``.

    A link is optional on activities and tasks, so ``None``/``None`` is valid.
    Supplying one half without the other is not: a type with no id points
    nowhere, and an id with no type cannot be resolved.

    Raises:
        ValidationFailedError: the pair is incomplete.
        UnknownRelatedEntityError: the target does not exist in this
            organization — which is also what another tenant's id looks like.
    """
    if entity_type is None and entity_id is None:
        return

    if entity_type is None or entity_id is None:
        raise ValidationFailedError(
            "A linked record needs both related_entity_type and related_entity_id.",
            details={
                "related_entity_type": entity_type.value if entity_type else None,
                "related_entity_id": str(entity_id) if entity_id else None,
            },
        )

    result = await session.execute(_selector(entity_type, entity_id, organization_id))
    if result.scalar_one_or_none() is None:
        raise UnknownRelatedEntityError(
            details={"related_entity_type": entity_type.value, "related_entity_id": str(entity_id)}
        )


__all__ = ["UnknownRelatedEntityError", "validate_related_entity"]
