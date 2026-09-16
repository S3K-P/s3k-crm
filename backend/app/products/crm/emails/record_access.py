"""May this caller write mail about this record, using this template?

``relations.validate_related_entity`` answers *does the record exist in my
organization*. That is tenant isolation, and it is not enough for mail. Within
an organization a rep with ``leads.VIEW`` but not ``leads.VIEW_ALL`` reads only
the leads they own — and without the check below the same rep could render a
template against a colleague's lead (reading its fields out of the preview) or
send a customer email filed against a record they cannot open.

So linking a message or rendering a template requires what opening the record
requires: ``VIEW`` on the record's module, and record-level visibility
(``RecordVisibility``, the one predicate every CRM read applies). A record that
fails either check produces the same :class:`UnknownRelatedEntityError` as one
that does not exist, so the email endpoints cannot be used to probe for
records the caller is not allowed to see.

A template must likewise be one the caller may read: the organization's shared
templates, or their own private ones.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.models import Account
from app.products.crm.campaigns.models import Campaign
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.emails.models import EmailTemplate
from app.products.crm.emails.policies import may_read_template
from app.products.crm.leads.models import Lead
from app.products.crm.opportunities.models import Opportunity
from app.products.crm.shared.relations import UnknownRelatedEntityError
from app.products.crm.shared.visibility import RecordVisibility

#: The record types mail may be filed against, and the module that governs each.
_RECORDS: Final[dict[CrmEntityType, tuple[type[Any], str]]] = {
    CrmEntityType.ACCOUNT: (Account, "accounts"),
    CrmEntityType.CONTACT: (Contact, "contacts"),
    CrmEntityType.LEAD: (Lead, "leads"),
    CrmEntityType.OPPORTUNITY: (Opportunity, "opportunities"),
    CrmEntityType.CAMPAIGN: (Campaign, "campaigns"),
}


async def load_readable_record(
    session: AsyncSession,
    *,
    principal: Principal,
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
) -> Any:
    """The record, if ``principal`` may open it.

    Raises:
        UnknownRelatedEntityError: it does not exist, belongs to another
            organization, or is hidden from the caller — deliberately one
            answer for all three.
    """
    entry = _RECORDS.get(entity_type)
    if entry is None:
        raise UnknownRelatedEntityError
    model, module = entry
    if not principal.has_permission(module, PermissionAction.VIEW):
        raise UnknownRelatedEntityError

    statement = select(model).where(
        model.id == entity_id,
        model.organization_id == principal.organization_id,
        model.deleted_at.is_(None),
    )
    predicate = RecordVisibility.for_module(principal, module).filter_for(model)
    if predicate is not None:
        statement = statement.where(predicate)
    record = (await session.execute(statement)).scalar_one_or_none()
    if record is None:
        raise UnknownRelatedEntityError
    return record


async def assert_record_readable(
    session: AsyncSession,
    *,
    principal: Principal,
    entity_type: CrmEntityType | None,
    entity_id: uuid.UUID | None,
) -> None:
    """Refuse a link to a record the caller may not open. No link is fine."""
    if entity_type is None or entity_id is None:
        return
    await load_readable_record(
        session, principal=principal, entity_type=entity_type, entity_id=entity_id
    )


async def assert_template_usable(
    session: AsyncSession, *, principal: Principal, template_id: uuid.UUID | None
) -> EmailTemplate | None:
    """The template, if it exists in the caller's organization and is theirs to use.

    Raises:
        NotFoundError: unknown, archived, another tenant's, or somebody else's
            private template.
    """
    if template_id is None:
        return None
    template = (
        await session.execute(
            select(EmailTemplate).where(
                EmailTemplate.id == template_id,
                EmailTemplate.organization_id == principal.organization_id,
                EmailTemplate.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if template is None or not may_read_template(
        is_shared=template.is_shared,
        owner_id=template.owner_id,
        viewer_id=principal.user_id,
    ):
        raise NotFoundError("Template not found.")
    return template


__all__ = ["assert_record_readable", "assert_template_usable", "load_readable_record"]
