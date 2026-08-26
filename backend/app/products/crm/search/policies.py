"""What global search is allowed to look at, and for whom (ADR-010).

Search has no permission module of its own, and that is deliberate. A
``search`` permission would be a second, parallel answer to a question the CRM
already answers per module — and the two would eventually disagree, which in a
search endpoint means returning a record the caller cannot open.

Instead the rule is compositional, and it has two independent halves:

**Which entity types are searched at all.** Only those where the caller holds
``<module>.VIEW``. A caller without ``leads.VIEW`` does not get zero lead
results — the leads branch is never added to the query, so leads cannot
influence ranking, counts, or anything else observable.

**Which rows within those types.** ``RecordVisibility.for_module``, the same
object every list endpoint uses. Owner, then team, then organization.

Both are applied inside the SQL. Nothing is filtered after ranking: see the
module docstring in :mod:`app.products.crm.search.repository` for why that
distinction is the whole security model here (risk R14).
"""

from __future__ import annotations

from typing import Final

from app.products.crm.accounts.models import Account
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead
from app.products.crm.opportunities.models import Opportunity
from app.products.crm.search.schemas import SearchEntityType

#: Entity type -> the permission module gating it. The names on the right are
#: the CRM modules from ``PERMISSION_MODULES``; they are what
#: ``RecordVisibility.for_module`` is keyed on too, so one string decides both
#: "may they search this" and "how much of it may they see".
MODULE_FOR_TYPE: Final[dict[SearchEntityType, str]] = {
    SearchEntityType.ACCOUNT: "accounts",
    SearchEntityType.CONTACT: "contacts",
    SearchEntityType.LEAD: "leads",
    SearchEntityType.OPPORTUNITY: "opportunities",
}

#: Entity type -> its model. Kept beside the permission map so adding a fifth
#: searchable entity means editing one file, and so the check below can refuse
#: to import a half-finished pair rather than letting an ungated table be
#: searched.
MODEL_FOR_TYPE: Final[dict[SearchEntityType, type]] = {
    SearchEntityType.ACCOUNT: Account,
    SearchEntityType.CONTACT: Contact,
    SearchEntityType.LEAD: Lead,
    SearchEntityType.OPPORTUNITY: Opportunity,
}


def _check_maps_are_complete() -> None:
    """Fail at import if a searchable type is missing from either map.

    A ``raise`` rather than an ``assert``: assertions are stripped under
    ``python -O``, and this one guards the case where a fifth entity type is
    added to the enum and given a model but no permission module — which would
    search an ungated table. That must not be a check the runtime can be
    configured out of.
    """
    types = set(SearchEntityType)
    for name, mapping in (("MODULE_FOR_TYPE", MODULE_FOR_TYPE), ("MODEL_FOR_TYPE", MODEL_FOR_TYPE)):
        missing = types - set(mapping)
        if missing:
            raise RuntimeError(
                f"{name} is missing {sorted(entity.value for entity in missing)}. "
                "Every SearchEntityType needs both a permission module and a "
                "model; one without a module would be searched with no gate."
            )


_check_maps_are_complete()


__all__ = ["MODEL_FOR_TYPE", "MODULE_FOR_TYPE"]
