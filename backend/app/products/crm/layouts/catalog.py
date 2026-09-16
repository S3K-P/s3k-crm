"""Which entity types have a layout, and what their built-in fields are.

A field a layout can place or a rule can read has to come from *somewhere
authoritative*. That source is each entity's own ``*Response`` schema —
deliberately the response, not the ``*Create`` schema ``imports/catalog.py``
uses for the same kind of lookup. The two catalogues answer different
questions: an import maps a CSV column onto something a client may *submit*,
so only writable fields belong. A layout field or a rule condition may
instead need to *place or read* a column no create request ever carries at
all — a lead's ``status``, an opportunity's ``stage_id`` — because those are
exactly the fields "IF Lead Status = Qualified" (the checkpoint brief's own
example) is written about. Using the response schema's full field surface
means a rule can read anything the record actually has, not only what a form
could have submitted when the record was made.

Deriving the field list from ``model_fields`` rather than hand-maintaining a
parallel list means the catalogue cannot drift: a field added to
``LeadResponse`` is placeable, and readable by a condition, the moment it
exists, with nothing else to remember to update.

**Scope.** Layouts, like the global search endpoint and the bulk-operation
endpoints this checkpoint also adds, cover the four entities with a real list
view and detail page: accounts, contacts, leads, opportunities. Campaigns and
the five-entity-wide custom-fields module are unaffected — a tenant may still
define custom fields on a campaign, there is simply no layout to arrange them
into. Extending the builder to campaigns is a catalog entry away, not a
redesign, should a later checkpoint want it.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.products.crm.accounts.schemas import AccountResponse
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.schemas import ContactResponse
from app.products.crm.leads.schemas import LeadResponse
from app.products.crm.opportunities.schemas import OpportunityResponse

#: Entity types the layout builder covers. See the module docstring for why
#: this is narrower than ``custom_fields.CUSTOM_FIELD_ENTITY_TYPES``.
LAYOUT_ENTITY_TYPES: frozenset[CrmEntityType] = frozenset(
    {
        CrmEntityType.ACCOUNT,
        CrmEntityType.CONTACT,
        CrmEntityType.LEAD,
        CrmEntityType.OPPORTUNITY,
    }
)

#: Prefix that marks a ``field_key`` as a tenant-defined field's api_name
#: rather than a built-in column. Matches the querystring convention
#: ``custom_fields/query.py`` already uses for ``?cf_<api_name>=`` filters,
#: kept distinct (``custom:`` vs ``cf_``) because a layout field key is never
#: parsed out of a URL and does not need to be one token.
CUSTOM_FIELD_KEY_PREFIX = "custom:"

_SCHEMA_BY_ENTITY: dict[CrmEntityType, type[BaseModel]] = {
    CrmEntityType.ACCOUNT: AccountResponse,
    CrmEntityType.CONTACT: ContactResponse,
    CrmEntityType.LEAD: LeadResponse,
    CrmEntityType.OPPORTUNITY: OpportunityResponse,
}

#: Columns every ``*Response`` schema declares that are bookkeeping rather
#: than "a field on the record" — framework-maintained identity and audit
#: columns, plus the custom-values bag, which is resolved through its own
#: mechanism rather than as one more built-in field a layout could place.
#: Matches ``shared.service._AUDIT_IGNORED_COLUMNS`` in spirit: the same
#: columns that say nothing about what a user entered.
_EXCLUDED_BUILTIN_FIELDS = frozenset(
    {
        "id",
        "organization_id",
        "created_at",
        "updated_at",
        "created_by_id",
        "updated_by_id",
        "custom_fields",
    }
)


def custom_field_key(api_name: str) -> str:
    """Build the ``field_key`` a layout uses to refer to a custom field."""
    return f"{CUSTOM_FIELD_KEY_PREFIX}{api_name}"


def is_custom_field_key(field_key: str) -> bool:
    return field_key.startswith(CUSTOM_FIELD_KEY_PREFIX)


def custom_field_api_name(field_key: str) -> str:
    """Strip the prefix. Raises ``ValueError`` if ``field_key`` is not one."""
    if not is_custom_field_key(field_key):
        raise ValueError(f"{field_key!r} is not a custom field key.")
    return field_key[len(CUSTOM_FIELD_KEY_PREFIX) :]


def builtin_field_names(entity_type: CrmEntityType) -> frozenset[str]:
    """Built-in fields a layout for ``entity_type`` may place.

    Raises:
        KeyError: ``entity_type`` is not covered by the layout builder — see
            :data:`LAYOUT_ENTITY_TYPES`.
    """
    schema = _SCHEMA_BY_ENTITY[entity_type]
    return frozenset(schema.model_fields) - _EXCLUDED_BUILTIN_FIELDS


def is_layout_entity(entity_type: CrmEntityType) -> bool:
    return entity_type in LAYOUT_ENTITY_TYPES


__all__ = [
    "CUSTOM_FIELD_KEY_PREFIX",
    "LAYOUT_ENTITY_TYPES",
    "builtin_field_names",
    "custom_field_api_name",
    "custom_field_key",
    "is_custom_field_key",
    "is_layout_entity",
]
