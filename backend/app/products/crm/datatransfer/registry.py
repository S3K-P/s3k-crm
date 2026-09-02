"""What each CRM module looks like to import, export and bulk operations.

The three features need the same three facts about a module — which fields
exist, what type each one holds, and which of them identify a record — so they
are declared once here rather than three times.

**This is data, not logic.** A descriptor names columns and types; it contains
no branching about how a particular module behaves. Anything that is genuinely
module-specific (an account's duplicate rule, a lead's state machine) stays in
that module's service, and the importer goes through the service to get it.
That is the whole reason the importer does not write rows directly: a row that
arrives by CSV must obey the same invariants as one that arrives by API, or
the importer becomes a hole in every rule the services enforce.

Adding a module here makes it importable, exportable and bulk-editable at once.
Deliberately narrow to start with: the four entities a customer actually
migrates on day one (analysis §5.8 — import is "the single biggest adoption
blocker"), plus the two that hang off them.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.products.crm.accounts.models import Account, AccountStatus
from app.products.crm.common import Priority
from app.products.crm.contacts.models import Contact, ContactStatus
from app.products.crm.leads.models import Lead, LeadSource, LeadStatus
from app.products.crm.opportunities.models import Opportunity
from app.products.crm.tasks.models import Task, TaskStatus


class FieldKind(enum.StrEnum):
    """How a CSV cell is turned into a column value."""

    TEXT = "TEXT"
    INTEGER = "INTEGER"
    DECIMAL = "DECIMAL"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    UUID = "UUID"
    ENUM = "ENUM"
    EMAIL = "EMAIL"


class FieldValueError(ValueError):
    """A cell could not be turned into the column's type."""


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """One importable/exportable column."""

    name: str
    kind: FieldKind
    #: Required on **create**. An update may legitimately omit it, so the
    #: importer only enforces this when it is about to insert.
    required: bool = False
    max_length: int | None = None
    #: Permitted values for ``ENUM``. Compared case-insensitively on import and
    #: reported in full when a cell misses, because "invalid status" without the
    #: list is a support ticket rather than a fix.
    choices: tuple[str, ...] = ()
    #: A lookup the importer resolves by *name* as well as by id, so a customer
    #: can write "Website" in a lead_source_id column instead of a UUID nobody
    #: has. ``None`` means id-only.
    lookup_model: type[Any] | None = None
    lookup_column: str = "name"
    #: Excluded from export. Nothing here is secret; these are columns whose
    #: value is meaningless outside the row that produced it.
    exportable: bool = True

    def label(self) -> str:
        return self.name


def _clean(raw: str) -> str:
    return raw.strip()


def coerce(spec: FieldSpec, raw: str) -> Any:
    """Turn one CSV cell into a column value, or explain why it cannot be.

    An empty cell is ``None`` for every kind. Distinguishing "the column was
    absent" from "the column held an empty string" is the caller's job — it is
    what ``skip_empty_values`` turns on — and both arrive here identically.
    """
    text = _clean(raw)
    if not text:
        return None

    match spec.kind:
        case FieldKind.TEXT | FieldKind.EMAIL:
            if spec.max_length is not None and len(text) > spec.max_length:
                raise FieldValueError(
                    f"longer than {spec.max_length} characters ({len(text)})"
                )
            if spec.kind is FieldKind.EMAIL and "@" not in text:
                raise FieldValueError("not an email address")
            return text

        case FieldKind.INTEGER:
            try:
                return int(text)
            except ValueError as error:
                raise FieldValueError(f"{text!r} is not a whole number") from error

        case FieldKind.DECIMAL:
            try:
                # Thousands separators are what a spreadsheet exports, so
                # rejecting them would fail on the format customers actually
                # have rather than on bad data.
                return Decimal(text.replace(",", ""))
            except (InvalidOperation, ValueError) as error:
                raise FieldValueError(f"{text!r} is not a number") from error

        case FieldKind.BOOLEAN:
            lowered = text.lower()
            if lowered in {"true", "yes", "y", "1"}:
                return True
            if lowered in {"false", "no", "n", "0"}:
                return False
            raise FieldValueError(f"{text!r} is not true/false")

        case FieldKind.DATE:
            try:
                return dt.date.fromisoformat(text)
            except ValueError as error:
                raise FieldValueError(f"{text!r} is not a date (expected YYYY-MM-DD)") from error

        case FieldKind.DATETIME:
            try:
                parsed = dt.datetime.fromisoformat(text)
            except ValueError as error:
                raise FieldValueError(f"{text!r} is not a date and time") from error
            # A naive timestamp is read as UTC rather than rejected: every
            # column it can land in is timezone-aware, and asking a customer to
            # add offsets to a spreadsheet is not a reasonable import rule.
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)

        case FieldKind.UUID:
            try:
                return uuid.UUID(text)
            except ValueError as error:
                raise FieldValueError(f"{text!r} is not an identifier") from error

        case FieldKind.ENUM:
            upper = text.upper().replace(" ", "_").replace("-", "_")
            if upper not in spec.choices:
                raise FieldValueError(
                    f"{text!r} is not one of: {', '.join(sorted(spec.choices))}"
                )
            return upper

    raise FieldValueError(f"unsupported field kind {spec.kind}")  # pragma: no cover


def format_for_export(value: Any) -> str:
    """Render a column value as a CSV cell.

    ISO 8601 throughout, because it round-trips: a date exported this way can
    be re-imported by :func:`coerce` without a format setting anywhere.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    """Everything import/export/bulk need to know about one CRM entity."""

    #: URL segment and stored identifier, e.g. ``leads``.
    key: str
    #: Permission module. Identical to ``key`` today, kept separate because a
    #: module whose permission lives elsewhere is a change waiting to happen.
    permission_module: str
    model: type[Any]
    fields: tuple[FieldSpec, ...]
    #: Fields offered as the duplicate-matching key, in the order the UI should
    #: present them. The first is the default, and mirrors Zoho's per-module
    #: choice (analysis §3.3): email for people, name for companies.
    match_fields: tuple[str, ...]
    #: Columns a bulk update may set. Narrower than ``fields`` on purpose:
    #: mass-editing a name or an email is a mistake at scale, while
    #: mass-editing a status or an owner is the point.
    bulk_updatable: tuple[str, ...] = ()
    #: Extra rows filtered out of every read, on top of tenant and soft delete.
    label_field: str = "name"

    _by_name: dict[str, FieldSpec] = field(default_factory=dict, compare=False)

    def spec(self, name: str) -> FieldSpec | None:
        if not self._by_name:
            self._by_name.update({item.name: item for item in self.fields})
        return self._by_name.get(name)

    def required_fields(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields if item.required)

    def exportable_fields(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields if item.exportable)


def _enum_choices(enum_type: type[enum.Enum]) -> tuple[str, ...]:
    return tuple(str(member.value) for member in enum_type)


_LEAD_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("first_name", FieldKind.TEXT, required=True, max_length=120),
    FieldSpec("last_name", FieldKind.TEXT, required=True, max_length=120),
    FieldSpec("company", FieldKind.TEXT, max_length=255),
    FieldSpec("email", FieldKind.EMAIL, max_length=320),
    FieldSpec("phone", FieldKind.TEXT, max_length=32),
    FieldSpec("status", FieldKind.ENUM, choices=_enum_choices(LeadStatus)),
    FieldSpec("priority", FieldKind.ENUM, choices=_enum_choices(Priority)),
    FieldSpec("industry", FieldKind.TEXT, max_length=120),
    FieldSpec("website", FieldKind.TEXT, max_length=512),
    FieldSpec("company_size", FieldKind.TEXT, max_length=64),
    FieldSpec("product_interest", FieldKind.TEXT, max_length=255),
    FieldSpec("expected_deal_size", FieldKind.DECIMAL),
    FieldSpec("notes", FieldKind.TEXT),
    FieldSpec("lead_source_id", FieldKind.UUID, lookup_model=LeadSource),
    FieldSpec("owner_id", FieldKind.UUID),
)

_ACCOUNT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", FieldKind.TEXT, required=True, max_length=255),
    FieldSpec("industry", FieldKind.TEXT, max_length=120),
    FieldSpec("website", FieldKind.TEXT, max_length=512),
    FieldSpec("company_size", FieldKind.TEXT, max_length=64),
    FieldSpec("annual_revenue", FieldKind.DECIMAL),
    FieldSpec("status", FieldKind.ENUM, choices=_enum_choices(AccountStatus)),
    FieldSpec("source", FieldKind.TEXT, max_length=120),
    FieldSpec("description", FieldKind.TEXT),
    FieldSpec("address_line1", FieldKind.TEXT, max_length=255),
    FieldSpec("city", FieldKind.TEXT, max_length=120),
    FieldSpec("state", FieldKind.TEXT, max_length=120),
    FieldSpec("postal_code", FieldKind.TEXT, max_length=32),
    FieldSpec("country", FieldKind.TEXT, max_length=120),
    FieldSpec("external_id", FieldKind.TEXT, max_length=255),
    FieldSpec("owner_id", FieldKind.UUID),
)

_CONTACT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("first_name", FieldKind.TEXT, required=True, max_length=120),
    FieldSpec("last_name", FieldKind.TEXT, required=True, max_length=120),
    FieldSpec("email", FieldKind.EMAIL, max_length=320),
    FieldSpec("phone", FieldKind.TEXT, max_length=32),
    FieldSpec("mobile", FieldKind.TEXT, max_length=32),
    FieldSpec("job_title", FieldKind.TEXT, max_length=160),
    FieldSpec("department", FieldKind.TEXT, max_length=120),
    FieldSpec("status", FieldKind.ENUM, choices=_enum_choices(ContactStatus)),
    FieldSpec("linkedin_url", FieldKind.TEXT, max_length=512),
    FieldSpec("notes", FieldKind.TEXT),
    FieldSpec("address_line1", FieldKind.TEXT, max_length=255),
    FieldSpec("city", FieldKind.TEXT, max_length=120),
    FieldSpec("state", FieldKind.TEXT, max_length=120),
    FieldSpec("postal_code", FieldKind.TEXT, max_length=32),
    FieldSpec("country", FieldKind.TEXT, max_length=120),
    # Resolved by account *name* as well as by id: a migrated contact list has
    # the company name in it, never the CRM's internal identifier.
    FieldSpec("account_id", FieldKind.UUID, lookup_model=Account),
    FieldSpec("owner_id", FieldKind.UUID),
)

_OPPORTUNITY_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", FieldKind.TEXT, required=True, max_length=255),
    FieldSpec("account_id", FieldKind.UUID, required=True, lookup_model=Account),
    # Both required for the reasons Stage 0 established: a deal with no stage
    # is not in a pipeline, and one with no close date is in no forecast.
    FieldSpec("stage_id", FieldKind.UUID, required=True),
    FieldSpec("expected_close_date", FieldKind.DATE, required=True),
    FieldSpec("deal_value", FieldKind.DECIMAL),
    FieldSpec("currency", FieldKind.TEXT, max_length=3),
    FieldSpec("win_probability", FieldKind.INTEGER),
    FieldSpec("forecast_category", FieldKind.TEXT, max_length=64),
    FieldSpec("competitor", FieldKind.TEXT, max_length=160),
    FieldSpec("products", FieldKind.TEXT),
    FieldSpec("notes", FieldKind.TEXT),
    FieldSpec("loss_reason", FieldKind.TEXT, max_length=255),
    FieldSpec("win_reason", FieldKind.TEXT, max_length=255),
    FieldSpec("owner_id", FieldKind.UUID),
)

_TASK_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("title", FieldKind.TEXT, required=True, max_length=255),
    FieldSpec("description", FieldKind.TEXT),
    FieldSpec("status", FieldKind.ENUM, choices=_enum_choices(TaskStatus)),
    FieldSpec("priority", FieldKind.ENUM, choices=_enum_choices(Priority)),
    FieldSpec("due_date", FieldKind.DATETIME),
    FieldSpec("owner_id", FieldKind.UUID),
    FieldSpec("assigned_to_id", FieldKind.UUID),
)

_LEAD_SOURCE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("name", FieldKind.TEXT, required=True, max_length=160),
    FieldSpec("category", FieldKind.TEXT, max_length=120),
    FieldSpec("description", FieldKind.TEXT),
)


MODULES: dict[str, ModuleSpec] = {
    spec.key: spec
    for spec in (
        ModuleSpec(
            key="leads",
            permission_module="leads",
            model=Lead,
            fields=_LEAD_FIELDS,
            match_fields=("email", "id"),
            bulk_updatable=("status", "priority", "owner_id", "lead_source_id", "industry"),
            label_field="last_name",
        ),
        ModuleSpec(
            key="accounts",
            permission_module="accounts",
            model=Account,
            fields=_ACCOUNT_FIELDS,
            match_fields=("name", "external_id", "id"),
            bulk_updatable=("status", "owner_id", "industry", "country"),
        ),
        ModuleSpec(
            key="contacts",
            permission_module="contacts",
            model=Contact,
            fields=_CONTACT_FIELDS,
            match_fields=("email", "id"),
            bulk_updatable=("status", "owner_id", "account_id", "department"),
            label_field="last_name",
        ),
        ModuleSpec(
            key="opportunities",
            permission_module="opportunities",
            model=Opportunity,
            fields=_OPPORTUNITY_FIELDS,
            match_fields=("name", "id"),
            # ``stage_id`` is absent deliberately: moving a deal between stages
            # runs win/loss rules and writes history, so it goes through the
            # bulk *stage* endpoint rather than a blind column update.
            bulk_updatable=("owner_id", "forecast_category", "currency"),
        ),
        ModuleSpec(
            key="tasks",
            permission_module="tasks",
            model=Task,
            fields=_TASK_FIELDS,
            match_fields=("id",),
            bulk_updatable=("status", "priority", "owner_id", "assigned_to_id"),
            label_field="title",
        ),
        ModuleSpec(
            key="lead-sources",
            permission_module="lead_sources",
            model=LeadSource,
            fields=_LEAD_SOURCE_FIELDS,
            match_fields=("name", "id"),
            bulk_updatable=("category", "status"),
        ),
    )
}

#: Modules a CSV may be imported into. Everything registered is importable;
#: named separately so a future read-only module can be exported without
#: becoming writable by upload.
IMPORTABLE: frozenset[str] = frozenset(MODULES)

ModuleResolver = Callable[[str], ModuleSpec]


def get_module(key: str) -> ModuleSpec | None:
    return MODULES.get(key)


def module_keys() -> Sequence[str]:
    return tuple(MODULES)


__all__ = [
    "IMPORTABLE",
    "MODULES",
    "FieldKind",
    "FieldSpec",
    "FieldValueError",
    "ModuleSpec",
    "coerce",
    "format_for_export",
    "get_module",
    "module_keys",
]
