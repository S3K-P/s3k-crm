"""The vocabulary a template may use, resolved from one CRM record.

A flat ``dict[str, str]``, built here and handed to
:func:`~app.products.crm.emails.templating.render_placeholders`. Flat and
pre-resolved on purpose: the renderer never touches an ORM object, so a
template cannot reach a column its author was not offered, cannot trigger a
lazy load, and cannot be made to traverse a relationship into another tenant's
data. Everything a template can see is decided in this file.

**This is a dedicated cross-module read model** in the sense
ARCHITECTURE-BOUNDARIES.md rule 6 permits: it reads the five CRM entity tables
and writes nothing, so no module's invariants can be bypassed through it. It
is the same shape as ``shared/relations.py`` and ``shared/attachments.py``, and
for the same reason — one column cannot carry a foreign key to five tables, so
the resolution has to live somewhere that is allowed to see all of them.

**The record is fetched org-scoped, again.** The caller has already validated
the link through ``validate_related_entity``; this fetch re-applies
``organization_id`` rather than trusting that, because the cost is a predicate
on a primary-key lookup and the failure mode it removes is one tenant's
merge fields rendering another tenant's customer names into an email.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.accounts.models import Account
from app.products.crm.campaigns.models import Campaign
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead
from app.products.crm.opportunities.models import Opportunity

#: Attribute names offered as ``{{record.<name>}}`` for each entity type.
#:
#: An allow-list per type rather than "every column", which is what keeps
#: ``{{record.search_vector}}`` and ``{{record.created_by_id}}`` out of a
#: customer's mail — and, more importantly, keeps this decision reviewable. A
#: column added to the contacts table does not silently become a merge field.
#: ``full_name`` on contacts and leads is a Python property rather than a
#: column, which is exactly why this list is names-to-``getattr`` and not a
#: column reflection: the useful merge field is the one a person would write,
#: and here that is derived.
_FIELDS: Final[dict[CrmEntityType, tuple[str, ...]]] = {
    CrmEntityType.ACCOUNT: (
        "name",
        "industry",
        "website",
        "city",
        "state",
        "country",
    ),
    CrmEntityType.CONTACT: (
        "first_name",
        "last_name",
        "full_name",
        "email",
        "phone",
        "mobile",
        "job_title",
        "department",
    ),
    CrmEntityType.LEAD: (
        "first_name",
        "last_name",
        "full_name",
        "email",
        "phone",
        "company",
        "industry",
        "website",
    ),
    #: No stage name: the stage is a foreign key to ``crm.pipeline_stages``,
    #: and resolving it would mean a join per render for a field a template
    #: rarely wants in a customer-facing message. ``forecast_category`` is the
    #: enum on the row itself and says the same thing internally.
    CrmEntityType.OPPORTUNITY: (
        "name",
        "deal_value",
        "currency",
        "expected_close_date",
        "forecast_category",
    ),
    CrmEntityType.CAMPAIGN: ("name", "type", "status"),
}

_MODELS: Final[dict[CrmEntityType, type[Any]]] = {
    CrmEntityType.ACCOUNT: Account,
    CrmEntityType.CONTACT: Contact,
    CrmEntityType.LEAD: Lead,
    CrmEntityType.OPPORTUNITY: Opportunity,
    CrmEntityType.CAMPAIGN: Campaign,
}


def offered_placeholders(entity_type: CrmEntityType | None) -> list[str]:
    """Every placeholder name a composer may insert for this record type.

    Drives the "insert field" picker. A template author is shown exactly what
    :func:`resolve_variables` can fill, so the two cannot drift into a picker
    that offers fields which never resolve.
    """
    names = ["sender.name", "sender.email", "organization.name"]
    if entity_type is not None:
        names.extend(f"record.{field}" for field in _FIELDS[entity_type])
    return sorted(names)


async def resolve_variables(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType | None,
    entity_id: uuid.UUID | None,
    sender_name: str | None = None,
    sender_email: str | None = None,
    organization_name: str | None = None,
) -> dict[str, str]:
    """Build the substitution vocabulary for one record.

    A field that is NULL on the record is **left out of the result** rather
    than mapped to an empty string. That is what makes an empty column and a
    misspelled placeholder behave identically — both stay visible in the
    preview as ``{{record.phone}}`` — instead of a missing phone number
    silently rendering "Call me on ." into a customer's inbox.
    """
    variables: dict[str, str] = {}
    if sender_name:
        variables["sender.name"] = sender_name
    if sender_email:
        variables["sender.email"] = sender_email
    if organization_name:
        variables["organization.name"] = organization_name

    if entity_type is None or entity_id is None:
        return variables

    model = _MODELS[entity_type]
    record = (
        await session.execute(
            select(model).where(
                model.id == entity_id,
                model.organization_id == organization_id,
                model.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        # Same answer as "no record": the caller validated the link, so this
        # is a record archived between validation and render. Rendering the
        # placeholders unresolved is the honest outcome.
        return variables

    for field in _FIELDS[entity_type]:
        value = getattr(record, field, None)
        if value is None:
            continue
        text = _stringify(value)
        if text:
            variables[f"record.{field}"] = text
    return variables


def _stringify(value: Any) -> str:
    """Render one column value for insertion into prose.

    Dates as ISO, enums by their value, everything else through ``str``.
    Deliberately plain: a locale-aware currency or date format belongs to the
    reader's locale, which the sender's template does not know, and a wrong
    format in a customer's inbox is worse than an unambiguous one.
    """
    if isinstance(value, bool):
        return "yes" if value else "no"
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    # StrEnum and friends stringify to their value already.
    return str(value).strip()


__all__ = ["offered_placeholders", "resolve_variables"]
