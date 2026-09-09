"""What "merge an account" actually means, written down once.

Merging is the same shape for every record type — pick a survivor, choose which
value wins per field, move everything that pointed at the losers, retire them —
and differs only in *what points at it*. So the shape lives in
:mod:`.service` and the differences live here, as data.

**Why a declared list rather than reflection.** The obvious implementation
walks SQLAlchemy's metadata for foreign keys and repoints whatever it finds.
That is worse in the way that matters: it would silently start rewriting a
column somebody adds next year without anybody deciding it should, and it
cannot see the polymorphic links at all — ``related_entity_type`` /
``related_entity_id`` is not a foreign key, and it is where most of a record's
history hangs. A list that has to be edited when a reference is added is a list
that gets *reviewed* when a reference is added.

The test ``test_merge_catalog_is_complete`` reads the live metadata and fails
if a real foreign key to a mergeable table is missing from here, so "has to be
edited" is enforced rather than hoped for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.products.crm.accounts.models import Account
from app.products.crm.activities.models import Activity
from app.products.crm.campaigns.models import CampaignMember, CampaignMemberType
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.emails.models import EmailMessage, EmailThread
from app.products.crm.leads.models import Lead
from app.products.crm.notes.models import Note
from app.products.crm.opportunities.models import Opportunity
from app.products.crm.tasks.models import Task


@dataclass(frozen=True, slots=True)
class ForeignReference:
    """A column on some table holding the id of a mergeable record.

    Repointed by a bulk UPDATE from each loser to the survivor. Always scoped
    to the organization in the same statement — a merge must not be able to
    touch another tenant's row even if a caller somehow supplied its id.
    """

    model: type[Any]
    column: str
    #: Human name for the audit entry, e.g. "opportunities".
    label: str


@dataclass(frozen=True, slots=True)
class PolymorphicReference:
    """A ``(entity_type, entity_id)`` pair pointing at a mergeable record.

    The links that carry a record's *history* — its activities, tasks, notes
    and mail. Not foreign keys, because one column cannot reference five
    tables, which is exactly why they have to be listed rather than discovered.
    """

    model: type[Any]
    type_column: str
    id_column: str
    label: str
    #: The value ``type_column`` holds for this record kind. Usually the
    #: ``CrmEntityType`` member; campaign membership has its own enum.
    type_value: Any


@dataclass(frozen=True, slots=True)
class MergeTarget:
    """Everything :mod:`.service` needs to merge one record type."""

    entity_type: CrmEntityType
    model: type[Any]
    #: The permission module gating it. Merging needs ``EDIT`` *and*
    #: ``DELETE`` on this module — it changes a record and retires others, and
    #: a role that may do only the first must not be able to do the second by
    #: routing through here.
    module: str
    #: Human name used in messages, e.g. "account".
    noun: str
    #: Columns never taken from a loser, whatever the caller selects. Identity
    #: and bookkeeping: copying them would either corrupt the survivor or
    #: rewrite history that is not the caller's to rewrite.
    protected_fields: frozenset[str]
    foreign_references: tuple[ForeignReference, ...] = ()
    polymorphic_references: tuple[PolymorphicReference, ...] = field(default_factory=tuple)


#: Columns no merge may ever copy from a loser onto the survivor.
#:
#: ``id`` and ``organization_id`` are identity. The authorship and timestamp
#: columns are the survivor's own history and must keep saying when *it* was
#: created and by whom. ``deleted_at`` would resurrect or bury a record as a
#: side effect of a field choice. ``search_vector`` is generated. ``custom_fields``
#: is merged by its own rule (see the service) rather than taken wholesale, so
#: one blank field on the survivor cannot discard every value on it.
_ALWAYS_PROTECTED: frozenset[str] = frozenset(
    {
        "id",
        "organization_id",
        "created_at",
        "updated_at",
        "created_by_id",
        "updated_by_id",
        "deleted_at",
        "search_vector",
        "custom_fields",
        "merged_into_id",
    }
)


def _history_references(type_value: CrmEntityType) -> tuple[PolymorphicReference, ...]:
    """The four polymorphic links every mergeable record shares.

    Activities, tasks, notes and mail all hang off a record through the same
    pair of columns, and all four have to follow the survivor or the merge
    loses exactly the history a merge is supposed to preserve. Mail is two
    tables — the thread and its messages each carry the link, denormalized so
    a record timeline needs no join — and both are moved.
    """
    def link(model: type[Any], label: str) -> PolymorphicReference:
        return PolymorphicReference(
            model, "related_entity_type", "related_entity_id", label, type_value
        )

    return (
        link(Activity, "activities"),
        link(Task, "tasks"),
        link(Note, "notes"),
        link(EmailThread, "email threads"),
        link(EmailMessage, "email messages"),
    )


ACCOUNT_TARGET = MergeTarget(
    entity_type=CrmEntityType.ACCOUNT,
    model=Account,
    module="accounts",
    noun="account",
    protected_fields=_ALWAYS_PROTECTED | {"primary_contact_id"},
    foreign_references=(
        ForeignReference(Contact, "account_id", "contacts"),
        # RESTRICT on this FK, so the losers could not be deleted while it
        # pointed at them even if deletion here were hard rather than soft.
        # Moving it first is what makes the merge legal as well as correct.
        ForeignReference(Opportunity, "account_id", "opportunities"),
        ForeignReference(Lead, "converted_account_id", "converted leads"),
    ),
    polymorphic_references=_history_references(CrmEntityType.ACCOUNT),
)

CONTACT_TARGET = MergeTarget(
    entity_type=CrmEntityType.CONTACT,
    model=Contact,
    module="contacts",
    noun="contact",
    protected_fields=_ALWAYS_PROTECTED,
    foreign_references=(
        ForeignReference(Account, "primary_contact_id", "accounts"),
        ForeignReference(Opportunity, "primary_contact_id", "opportunities"),
        ForeignReference(Lead, "converted_contact_id", "converted leads"),
    ),
    polymorphic_references=(
        *_history_references(CrmEntityType.CONTACT),
        PolymorphicReference(
            CampaignMember,
            "entity_type",
            "entity_id",
            "campaign memberships",
            CampaignMemberType.CONTACT,
        ),
    ),
)

LEAD_TARGET = MergeTarget(
    entity_type=CrmEntityType.LEAD,
    model=Lead,
    module="leads",
    noun="lead",
    #: Conversion outcome is not a field a caller may choose between. A lead
    #: that became an account did so at a moment, into specific records; taking
    #: those columns from a loser would claim a conversion that never happened
    #: and point the survivor at somebody else's account.
    protected_fields=_ALWAYS_PROTECTED
    | {
        "converted_at",
        "converted_account_id",
        "converted_contact_id",
        "converted_opportunity_id",
    },
    polymorphic_references=(
        *_history_references(CrmEntityType.LEAD),
        PolymorphicReference(
            CampaignMember,
            "entity_type",
            "entity_id",
            "campaign memberships",
            CampaignMemberType.LEAD,
        ),
    ),
)

#: The record types a merge is offered for, keyed by the path segment.
#:
#: Accounts, contacts and leads: the three that duplicate in practice, because
#: they are the ones created by imports, web forms and two reps talking to the
#: same company. Opportunities and campaigns are deliberately absent — two
#: deals against one account are usually two deals, and merging them would
#: destroy stage history that the pipeline report is computed from.
MERGE_TARGETS: dict[str, MergeTarget] = {
    "accounts": ACCOUNT_TARGET,
    "contacts": CONTACT_TARGET,
    "leads": LEAD_TARGET,
}

#: The most records one merge may combine, including the survivor.
#:
#: A merge is irreversible in practice — the losers are retired and their
#: references moved — so it is an operation somebody should be reviewing on
#: screen, not applying to a hundred rows at once. Ten is more than any real
#: duplicate cluster and small enough that the confirmation screen stays
#: readable.
MAX_MERGE_RECORDS = 10


__all__ = [
    "MAX_MERGE_RECORDS",
    "MERGE_TARGETS",
    "ForeignReference",
    "MergeTarget",
    "PolymorphicReference",
]
