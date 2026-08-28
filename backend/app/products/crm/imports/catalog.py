"""What may be imported, and which existing code does the work.

One table, three rows. Each entry names the entity's own ``*Create`` schema and
its own service method, so the import path is a thin caller of code that
already exists rather than a parallel one — the property the module docstring
turns on.

Adding a fourth importable entity is an entry here plus nothing else.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.accounts.schemas import AccountCreate
from app.products.crm.accounts.service import AccountService
from app.products.crm.contacts.schemas import ContactCreate
from app.products.crm.contacts.service import ContactService
from app.products.crm.leads.schemas import LeadCreate
from app.products.crm.leads.service import LeadService

#: Signature every entry's ``create`` conforms to. The keyword names match the
#: three services exactly, which is what lets them be called uniformly.
CreateCallable = Callable[..., Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ImportableEntity:
    """One entity a CSV can be loaded into."""

    #: URL segment and the value the frontend sends, e.g. ``leads``.
    slug: str
    #: Permission module. Import requires ``<module>.CREATE`` -- importing is
    #: creating records, and the catalogue has no separate IMPORT action to
    #: check. Inventing one would mean a migration and a role change for every
    #: existing tenant, to express a grant that ``CREATE`` already covers.
    module: str
    #: Singular label used in messages, e.g. "lead".
    label: str
    #: The entity's own request schema. Import validation *is* API validation.
    schema: type[BaseModel]
    #: Field the duplicate rule keys on, for the preview's summary. The rule
    #: itself lives in the service; this only names it for the reader.
    duplicate_field: str
    #: Builds the service from a session and returns its create method.
    create: Callable[[AsyncSession], CreateCallable]


def _accounts(session: AsyncSession) -> CreateCallable:
    return AccountService(session).create_account


def _contacts(session: AsyncSession) -> CreateCallable:
    return ContactService(session).create_contact


def _leads(session: AsyncSession) -> CreateCallable:
    return LeadService(session).create_lead


IMPORTABLE: dict[str, ImportableEntity] = {
    entity.slug: entity
    for entity in (
        ImportableEntity(
            slug="leads",
            module="leads",
            label="lead",
            schema=LeadCreate,
            duplicate_field="email",
            create=_leads,
        ),
        ImportableEntity(
            slug="accounts",
            module="accounts",
            label="account",
            schema=AccountCreate,
            duplicate_field="name",
            create=_accounts,
        ),
        ImportableEntity(
            slug="contacts",
            module="contacts",
            label="contact",
            schema=ContactCreate,
            duplicate_field="email",
            create=_contacts,
        ),
    )
}


def field_names(entity: ImportableEntity) -> list[str]:
    """Columns a CSV may map onto, in the schema's own order."""
    return list(entity.schema.model_fields)


def required_fields(entity: ImportableEntity) -> list[str]:
    """Fields with no default -- a mapping that omits one cannot validate."""
    return [
        name
        for name, field in entity.schema.model_fields.items()
        if field.is_required()
    ]


def owner_defaulted_fields(entity: ImportableEntity) -> list[str]:
    """Fields the server fills in when a row leaves them blank.

    Surfaced so the mapping step can say so rather than letting an importer
    wonder why ``owner_id`` was optional. ``uuid`` is imported for the type
    check alone; the values are never read here.
    """
    return [
        name
        for name, field in entity.schema.model_fields.items()
        if name == "owner_id" and field.annotation in (uuid.UUID | None, uuid.UUID)
    ]


__all__ = [
    "IMPORTABLE",
    "ImportableEntity",
    "field_names",
    "owner_defaulted_fields",
    "required_fields",
]
