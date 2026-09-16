"""What a custom report may select, filter, group and aggregate by.

This is the allow-list the whole custom-report engine (:mod:`.custom`) is
built on. A field a report can touch has to come from *here* — a name typed
into a request body is looked up against this registry and rejected if it is
not in it — never from a column name taken off the request and interpolated
into SQL. That is the entire security property of an "ad-hoc" report over the
one the built-in catalogue has: :mod:`.catalog`'s nine reports are reviewed
code with no user-authored shape at all; this module is what lets a report be
user-authored without becoming user-authored SQL.

**Five entities, not the five ``CrmEntityType`` members.** Reports cover the
four entities the built-in catalogue already reads (accounts, contacts,
leads, opportunities) plus activities, which the catalogue's own
``activity_by_owner`` already aggregates. Campaigns are out of scope here for
the same reason :mod:`app.products.crm.layouts.catalog` gives for excluding
them from the form builder: no real list/detail surface exists for a builder
to be useful against yet.

**A field's SQLAlchemy column may need a join.** ``stage`` on an opportunity
and ``lead_source`` on a lead or opportunity are names on a *related* table,
not a column of the entity's own. :class:`ReportField.join` names the model
to join and the ON condition, applied once per statement no matter how many
selected fields need the same join.

**Custom fields are filter-only, not select/group/aggregate targets, in this
first version.** Every tenant-defined field is already filterable through
:func:`app.products.crm.custom_fields.filters.custom_field_filter`, and the
custom-report engine reuses that verbatim for a ``custom:<api_name>``
condition. Grouping or aggregating by a JSONB value would need the same
guarded-cast machinery that module already has, layered under a *second*
allow-list this module does not yet keep (which custom fields are numeric
enough to sum). That is a real gap, not an oversight — see the checkpoint's
progress notes for the reasoning — and the fix is additive: a future version
can widen :class:`ReportField` to cover it without moving anything that
exists today.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.orm import InstrumentedAttribute

from app.products.crm.accounts.models import Account
from app.products.crm.activities.models import Activity
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead, LeadSource
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.reports.catalog import ColumnType


class ReportEntity(enum.StrEnum):
    """The record types a custom report may run over."""

    LEAD = "LEAD"
    CONTACT = "CONTACT"
    ACCOUNT = "ACCOUNT"
    OPPORTUNITY = "OPPORTUNITY"
    ACTIVITY = "ACTIVITY"


#: The permission module each entity's data belongs to — the same string
#: ``RecordVisibility.for_module`` and ``principal.has_permission`` key on,
#: so one string decides both "may this report run" and "how much of it".
MODULE_FOR_ENTITY: dict[ReportEntity, str] = {
    ReportEntity.LEAD: "leads",
    ReportEntity.CONTACT: "contacts",
    ReportEntity.ACCOUNT: "accounts",
    ReportEntity.OPPORTUNITY: "opportunities",
    ReportEntity.ACTIVITY: "activities",
}

MODEL_FOR_ENTITY: dict[ReportEntity, type[Any]] = {
    ReportEntity.LEAD: Lead,
    ReportEntity.CONTACT: Contact,
    ReportEntity.ACCOUNT: Account,
    ReportEntity.OPPORTUNITY: Opportunity,
    ReportEntity.ACTIVITY: Activity,
}

#: The ``CrmEntityType`` counterpart, for entities that have custom fields.
#: ``None`` for activities — :class:`~app.products.crm.activities.models.Activity`
#: carries no ``CustomFieldValuesMixin`` and no ``CrmEntityType`` member names
#: it, so a custom report over activities simply offers no ``custom:`` filters.
CRM_ENTITY_TYPE_FOR_ENTITY: dict[ReportEntity, CrmEntityType | None] = {
    ReportEntity.LEAD: CrmEntityType.LEAD,
    ReportEntity.CONTACT: CrmEntityType.CONTACT,
    ReportEntity.ACCOUNT: CrmEntityType.ACCOUNT,
    ReportEntity.OPPORTUNITY: CrmEntityType.OPPORTUNITY,
    ReportEntity.ACTIVITY: None,
}

#: The reverse of the above, for callers that start from a ``CrmEntityType``
#: (``views.schemas``, validating a saved view's advanced filter). ``CAMPAIGN``
#: is deliberately absent — no reportable-field registry exists for it, the
#: same scope boundary :mod:`app.products.crm.layouts.catalog` draws.
REPORT_ENTITY_FOR_CRM_ENTITY_TYPE: dict[CrmEntityType, ReportEntity] = {
    CrmEntityType.LEAD: ReportEntity.LEAD,
    CrmEntityType.CONTACT: ReportEntity.CONTACT,
    CrmEntityType.ACCOUNT: ReportEntity.ACCOUNT,
    CrmEntityType.OPPORTUNITY: ReportEntity.OPPORTUNITY,
}


class AggOp(enum.StrEnum):
    """The five aggregations a group may be summarised by."""

    COUNT = "COUNT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


#: Which aggregations make sense over which column type. ``COUNT`` always
#: applies — "how many rows in this group" is meaningful for text and dates
#: too — the others only where arithmetic or ordering means something.
AGGREGATIONS_BY_TYPE: dict[ColumnType, frozenset[AggOp]] = {
    ColumnType.NUMBER: frozenset(AggOp),
    ColumnType.CURRENCY: frozenset(AggOp),
    ColumnType.PERCENT: frozenset(AggOp),
    ColumnType.DATE: frozenset({AggOp.COUNT, AggOp.MIN, AggOp.MAX}),
    ColumnType.TEXT: frozenset({AggOp.COUNT}),
    ColumnType.STATUS: frozenset({AggOp.COUNT}),
    ColumnType.PERSON: frozenset({AggOp.COUNT}),
}


class DateInterval(enum.StrEnum):
    """A ``date_trunc`` bucket, for grouping a date field into a trend."""

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


@dataclass(frozen=True, slots=True)
class JoinSpec:
    """One related table a field's column lives on."""

    model: type[Any]
    #: The join's ON condition, e.g. ``Opportunity.stage_id == PipelineStage.id``.
    on: ColumnElement[bool]
    #: ``True`` for a nullable foreign key: a LEFT JOIN keeps the row when the
    #: reference is unset, so an unassigned lead source groups under "None"
    #: rather than silently dropping the record from the report.
    outer: bool = False


@dataclass(frozen=True, slots=True)
class ReportField:
    key: str
    label: str
    column: InstrumentedAttribute[Any]
    type: ColumnType
    #: Non-``None`` when the column lives on a joined table.
    join: JoinSpec | None = None
    filterable: bool = True
    groupable: bool = True
    sortable: bool = True

    @property
    def aggregations(self) -> frozenset[AggOp]:
        return AGGREGATIONS_BY_TYPE.get(self.type, frozenset({AggOp.COUNT}))


def _field(
    key: str,
    label: str,
    column: InstrumentedAttribute[Any],
    type_: ColumnType,
    *,
    join: JoinSpec | None = None,
    filterable: bool = True,
    groupable: bool = True,
    sortable: bool = True,
) -> ReportField:
    return ReportField(
        key=key,
        label=label,
        column=column,
        type=type_,
        join=join,
        filterable=filterable,
        groupable=groupable,
        sortable=sortable,
    )


_LEAD_SOURCE_JOIN = JoinSpec(LeadSource, LeadSource.id == Lead.lead_source_id, outer=True)
_OPP_LEAD_SOURCE_JOIN = JoinSpec(
    LeadSource, LeadSource.id == Opportunity.lead_source_id, outer=True
)
_STAGE_JOIN = JoinSpec(PipelineStage, PipelineStage.id == Opportunity.stage_id)
_ACCOUNT_JOIN = JoinSpec(Account, Account.id == Opportunity.account_id)

FIELDS: dict[ReportEntity, dict[str, ReportField]] = {
    ReportEntity.LEAD: {
        f.key: f
        for f in (
            _field("first_name", "First name", Lead.first_name, ColumnType.TEXT),
            _field("last_name", "Last name", Lead.last_name, ColumnType.TEXT),
            _field("company", "Company", Lead.company, ColumnType.TEXT),
            _field("email", "Email", Lead.email, ColumnType.TEXT),
            _field("phone", "Phone", Lead.phone, ColumnType.TEXT),
            _field("status", "Status", Lead.status, ColumnType.STATUS),
            _field("priority", "Priority", Lead.priority, ColumnType.STATUS),
            _field(
                "lead_source",
                "Lead source",
                LeadSource.name,
                ColumnType.TEXT,
                join=_LEAD_SOURCE_JOIN,
                sortable=False,
            ),
            _field("owner_id", "Owner", Lead.owner_id, ColumnType.PERSON, sortable=False),
            _field("industry", "Industry", Lead.industry, ColumnType.TEXT),
            _field("website", "Website", Lead.website, ColumnType.TEXT),
            _field("company_size", "Company size", Lead.company_size, ColumnType.TEXT),
            _field(
                "product_interest", "Product interest", Lead.product_interest, ColumnType.TEXT
            ),
            _field(
                "expected_deal_size",
                "Expected deal size",
                Lead.expected_deal_size,
                ColumnType.CURRENCY,
            ),
            _field("ai_score", "AI score", Lead.ai_score, ColumnType.NUMBER),
            _field(
                "lost_reason", "Lost reason", Lead.lost_reason, ColumnType.TEXT, groupable=True
            ),
            _field("converted_at", "Converted at", Lead.converted_at, ColumnType.DATE),
            _field("created_at", "Created", Lead.created_at, ColumnType.DATE),
        )
    },
    ReportEntity.CONTACT: {
        f.key: f
        for f in (
            _field("first_name", "First name", Contact.first_name, ColumnType.TEXT),
            _field("last_name", "Last name", Contact.last_name, ColumnType.TEXT),
            _field("email", "Email", Contact.email, ColumnType.TEXT),
            _field("phone", "Phone", Contact.phone, ColumnType.TEXT),
            _field("job_title", "Job title", Contact.job_title, ColumnType.TEXT),
            _field("department", "Department", Contact.department, ColumnType.TEXT),
            _field("status", "Status", Contact.status, ColumnType.STATUS),
            _field("owner_id", "Owner", Contact.owner_id, ColumnType.PERSON, sortable=False),
            _field("city", "City", Contact.city, ColumnType.TEXT),
            _field("state", "State", Contact.state, ColumnType.TEXT),
            _field("country", "Country", Contact.country, ColumnType.TEXT),
            _field("created_at", "Created", Contact.created_at, ColumnType.DATE),
        )
    },
    ReportEntity.ACCOUNT: {
        f.key: f
        for f in (
            _field("name", "Name", Account.name, ColumnType.TEXT),
            _field("industry", "Industry", Account.industry, ColumnType.TEXT),
            _field("website", "Website", Account.website, ColumnType.TEXT),
            _field("phone", "Phone", Account.phone, ColumnType.TEXT),
            _field("company_size", "Company size", Account.company_size, ColumnType.TEXT),
            _field(
                "annual_revenue", "Annual revenue", Account.annual_revenue, ColumnType.CURRENCY
            ),
            _field("status", "Status", Account.status, ColumnType.STATUS),
            _field("owner_id", "Owner", Account.owner_id, ColumnType.PERSON, sortable=False),
            _field("health_score", "Health score", Account.health_score, ColumnType.NUMBER),
            _field("source", "Source", Account.source, ColumnType.TEXT),
            _field("city", "City", Account.city, ColumnType.TEXT),
            _field("state", "State", Account.state, ColumnType.TEXT),
            _field("country", "Country", Account.country, ColumnType.TEXT),
            _field("created_at", "Created", Account.created_at, ColumnType.DATE),
        )
    },
    ReportEntity.OPPORTUNITY: {
        f.key: f
        for f in (
            _field("name", "Deal name", Opportunity.name, ColumnType.TEXT),
            _field(
                "account",
                "Account",
                Account.name,
                ColumnType.TEXT,
                join=_ACCOUNT_JOIN,
                sortable=False,
            ),
            _field(
                "stage",
                "Stage",
                PipelineStage.name,
                ColumnType.TEXT,
                join=_STAGE_JOIN,
                sortable=False,
            ),
            _field("deal_value", "Deal value", Opportunity.deal_value, ColumnType.CURRENCY),
            _field("currency", "Currency", Opportunity.currency, ColumnType.TEXT),
            _field(
                "win_probability",
                "Win probability",
                Opportunity.win_probability,
                ColumnType.PERCENT,
            ),
            _field(
                "expected_close_date",
                "Expected close date",
                Opportunity.expected_close_date,
                ColumnType.DATE,
            ),
            _field("owner_id", "Owner", Opportunity.owner_id, ColumnType.PERSON, sortable=False),
            _field(
                "forecast_category",
                "Forecast category",
                Opportunity.forecast_category,
                ColumnType.TEXT,
            ),
            _field("competitor", "Competitor", Opportunity.competitor, ColumnType.TEXT),
            _field(
                "lead_source",
                "Lead source",
                LeadSource.name,
                ColumnType.TEXT,
                join=_OPP_LEAD_SOURCE_JOIN,
                sortable=False,
            ),
            _field("won_at", "Won at", Opportunity.won_at, ColumnType.DATE),
            _field("lost_at", "Lost at", Opportunity.lost_at, ColumnType.DATE),
            _field("created_at", "Created", Opportunity.created_at, ColumnType.DATE),
        )
    },
    ReportEntity.ACTIVITY: {
        f.key: f
        for f in (
            _field("type", "Type", Activity.type, ColumnType.STATUS),
            _field("subject", "Subject", Activity.subject, ColumnType.TEXT),
            _field("status", "Status", Activity.status, ColumnType.STATUS),
            _field("outcome", "Outcome", Activity.outcome, ColumnType.TEXT),
            _field(
                "duration_minutes",
                "Duration (minutes)",
                Activity.duration_minutes,
                ColumnType.NUMBER,
            ),
            _field("owner_id", "Owner", Activity.owner_id, ColumnType.PERSON, sortable=False),
            _field("due_date", "Due date", Activity.due_date, ColumnType.DATE),
            _field("completed_at", "Completed at", Activity.completed_at, ColumnType.DATE),
            _field("created_at", "Created", Activity.created_at, ColumnType.DATE),
        )
    },
}

#: The field every entity offers as the default reporting window — see
#: :mod:`.custom` for how ``date_field`` bounds a report by ``date_from``/
#: ``date_to`` the same way ``ReportDefinition.accepts_date_range`` does for
#: the built-in catalogue.
DEFAULT_DATE_FIELD = "created_at"


def field_for(entity: ReportEntity, key: str) -> ReportField:
    """Look up one field, or raise ``KeyError`` if it is not offered.

    The single point every part of the custom-report engine resolves a
    client-supplied field name through — nothing downstream ever sees a
    field name that did not come from this registry.
    """
    return FIELDS[entity][key]


__all__ = [
    "AGGREGATIONS_BY_TYPE",
    "CRM_ENTITY_TYPE_FOR_ENTITY",
    "DEFAULT_DATE_FIELD",
    "FIELDS",
    "MODEL_FOR_ENTITY",
    "MODULE_FOR_ENTITY",
    "REPORT_ENTITY_FOR_CRM_ENTITY_TYPE",
    "AggOp",
    "DateInterval",
    "JoinSpec",
    "ReportEntity",
    "ReportField",
    "field_for",
]
