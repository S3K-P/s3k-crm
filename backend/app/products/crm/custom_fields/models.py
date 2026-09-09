"""SQLAlchemy models for tenant-defined fields and picklists (Phase E).

Three tables and one column, and the column is the part worth explaining.

**Where a custom value is stored.** Each supported record type carries a single
``custom_fields`` JSONB column (:class:`CustomFieldValuesMixin`) rather than
the entity-attribute-value table this is usually built as. Three reasons, in
order of how much they matter:

1. *No N+1, ever.* A record's custom values arrive with the record, in the row
   the list query already selected. An EAV table would need a second query per
   page — or a join whose row multiplication has to be collapsed again — on
   every list screen in the product, which is precisely the class of defect
   Phase H exists to remove rather than introduce.
2. *Deactivating an option cannot corrupt a record.* A stored value is a
   string, not a foreign key, so retiring or renaming an option leaves history
   readable exactly as it was written. Under an EAV design with an
   ``option_id`` FK the same act is either blocked or cascades into stored
   data; both are worse than a value that keeps rendering.
3. *One migration.* Adding a field is data, not DDL. Nothing in the schema
   changes when an administrator defines their fortieth field.

What it costs is typed indexing: a JSONB value is text at the storage layer, so
filtering compares text and sorting orders text. That is bounded by
:func:`app.products.crm.custom_fields.filters.custom_field_filter`, which casts
per the *definition's* declared type before comparing, and by the GIN index the
migration puts on each column. It is the right trade for a feature whose values
are read far more often than they are ranged over.

**Why the definition is not a foreign key of the value.** ``api_name`` is the
key inside the JSONB object. Renaming a field's *label* is free; its
``api_name`` is immutable after creation (:mod:`.service`) precisely because
stored values are keyed by it.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import (
    CRM_SCHEMA,
    CrmEntityMixin,
    CrmEntityType,
    CustomFieldValuesMixin,
)

#: Record types that may carry custom fields.
#:
#: The same five ``CrmEntityType`` members activities, tasks and notes already
#: attach to — the entities a user thinks of as "a record with a detail page".
#: Deliberately not tasks or activities: those are events *about* a record, and
#: giving them a parallel set of tenant-defined columns would fragment the same
#: information across two places without anybody having asked for it.
CUSTOM_FIELD_ENTITY_TYPES: frozenset[CrmEntityType] = frozenset(CrmEntityType)

#: Upper bound on definitions per entity type, per organization.
#:
#: Not an arbitrary tidiness rule. Every definition is validated on every write
#: to that entity and rendered on every form, and the JSONB column is stored
#: inline in the row until it exceeds the TOAST threshold. A four-figure field
#: count would degrade every list screen in the product for the tenant that
#: created it, silently and irreversibly. Two hundred is far above what any
#: real deployment uses and low enough that the degradation cannot happen.
MAX_FIELDS_PER_ENTITY = 200

#: Upper bound on live options in one picklist, for the same reason: the whole
#: option set is loaded to validate a single value and to render a single
#: select.
MAX_OPTIONS_PER_PICKLIST = 500

#: Longest stored value for a single custom field, in characters.
#:
#: Applies to the *stored* string, after coercion. A TEXTAREA field is the
#: only type that can approach it; the rest are bounded far below by their own
#: shape. Enforced in the service rather than the database because the
#: database sees one JSONB document, not the fields inside it.
MAX_VALUE_LENGTH = 32_000


class CustomFieldType(enum.StrEnum):
    """The vocabulary of field types an administrator may choose from.

    Closed on purpose. Each member has exactly one coercion rule, one
    validation rule and one comparison cast, all of them written down in
    :mod:`.validation`; a type that is not in this list has none of those and
    would be stored as whatever the client happened to send.
    """

    TEXT = "TEXT"
    TEXTAREA = "TEXTAREA"
    NUMBER = "NUMBER"
    DECIMAL = "DECIMAL"
    DATE = "DATE"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"
    EMAIL = "EMAIL"
    URL = "URL"
    PHONE = "PHONE"
    PICKLIST = "PICKLIST"
    MULTI_PICKLIST = "MULTI_PICKLIST"


#: Types whose value is chosen from a :class:`Picklist`.
PICKLIST_TYPES: frozenset[CustomFieldType] = frozenset(
    {CustomFieldType.PICKLIST, CustomFieldType.MULTI_PICKLIST}
)

#: Types that may be used as a list filter or a sort key.
#:
#: ``MULTI_PICKLIST`` is filterable (does this record hold that option?) but
#: not sortable: a set has no order, so any ordering the database produced
#: would be an artefact of its serialization rather than an answer to a
#: question a user asked. ``TEXTAREA`` is neither — ranging over prose is not a
#: thing list screens do, and offering it would mean indexing it.
SORTABLE_TYPES: frozenset[CustomFieldType] = frozenset(
    {
        CustomFieldType.TEXT,
        CustomFieldType.NUMBER,
        CustomFieldType.DECIMAL,
        CustomFieldType.DATE,
        CustomFieldType.DATETIME,
        CustomFieldType.BOOLEAN,
        CustomFieldType.EMAIL,
        CustomFieldType.URL,
        CustomFieldType.PHONE,
        CustomFieldType.PICKLIST,
    }
)

FILTERABLE_TYPES: frozenset[CustomFieldType] = SORTABLE_TYPES | {CustomFieldType.MULTI_PICKLIST}


class Picklist(Base, CrmEntityMixin):
    """A named, reusable set of options.

    Reusable is the point: "Region" is one list, and the three fields that ask
    for a region should offer the same options and stay in step when one is
    added. A field-private option list would guarantee they drift.
    """

    __tablename__ = "picklists"
    __table_args__ = (
        # Partial, so a retired list's api_name is free again — the reasoning
        # ``lead_sources`` established, and for the same reason: deletion here
        # is soft, so an unconditional constraint would burn every name
        # anybody ever retired.
        Index(
            "uq_picklists_organization_id_api_name_live",
            "organization_id",
            "api_name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: Stable machine name. Immutable after creation: field definitions and,
    #: through them, stored record values are resolved against it.
    api_name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PicklistOption(Base, CrmEntityMixin):
    """One option within a :class:`Picklist`.

    ``value`` is what lands in a record's ``custom_fields``; ``label`` is what a
    person sees. Separating them is what allows "EMEA" to be relabelled
    "Europe, Middle East & Africa" without touching a single stored record.
    """

    __tablename__ = "picklist_options"
    __table_args__ = (
        Index(
            "uq_picklist_options_picklist_id_value_live",
            "picklist_id",
            "value",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # At most one default per list. Partial on both conditions so it
        # constrains only the rows that make the claim.
        Index(
            "uq_picklist_options_picklist_id_default",
            "picklist_id",
            unique=True,
            postgresql_where=text("is_default AND deleted_at IS NULL"),
        ),
        Index(
            "ix_picklist_options_organization_id_picklist_id",
            "organization_id",
            "picklist_id",
        ),
        {"schema": CRM_SCHEMA},
    )

    picklist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        # CASCADE: an option has no meaning without its list. The list itself
        # is soft-deleted through the API, so this fires only for a hard delete
        # that no API path performs.
        ForeignKey(f"{CRM_SCHEMA}.picklists.id", ondelete="CASCADE"),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: An inactive option cannot be *newly* selected but still renders on the
    #: records that already hold it. That asymmetry is the whole reason the
    #: column exists rather than deletion being the only retirement.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class CustomFieldDefinition(Base, CrmEntityMixin):
    """One tenant-defined field on one record type."""

    __tablename__ = "custom_field_definitions"
    __table_args__ = (
        Index(
            "uq_custom_field_definitions_org_entity_api_name_live",
            "organization_id",
            "entity_type",
            "api_name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_custom_field_definitions_organization_id_entity_type",
            "organization_id",
            "entity_type",
        ),
        # A picklist field without a list, or a non-picklist field with one,
        # are both configurations that cannot be rendered or validated. The
        # service refuses them with a 422; the table refuses them absolutely,
        # so a path that bypassed the schema still cannot store one.
        CheckConstraint(
            "(field_type IN ('PICKLIST', 'MULTI_PICKLIST')) = (picklist_id IS NOT NULL)",
            name="picklist_type_requires_picklist",
        ),
        CheckConstraint(
            "min_value IS NULL OR max_value IS NULL OR min_value <= max_value",
            name="value_range_ordered",
        ),
        CheckConstraint(
            "min_length IS NULL OR max_length IS NULL OR min_length <= max_length",
            name="length_range_ordered",
        ),
        {"schema": CRM_SCHEMA},
    )

    entity_type: Mapped[CrmEntityType] = mapped_column(
        Enum(CrmEntityType, name="crm_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    #: The key this field's value is stored under. Immutable after creation.
    api_name: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    field_type: Mapped[CustomFieldType] = mapped_column(
        Enum(CustomFieldType, name="custom_field_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    help_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    #: An inactive field is neither required nor rendered, and is not validated
    #: on write — but values already stored under it are left alone and are
    #: still returned. Deactivation is how a field is retired without losing
    #: the data collected through it; deletion (soft) is the same, and exists
    #: separately only so a mistyped field can disappear from the admin list.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    #: Applied when a record is created without a value for this field. Stored
    #: as text and coerced through the same path as a submitted value, so a
    #: default cannot be a shape the field would reject.
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    picklist_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        # RESTRICT: deleting a list still referenced by a field would leave
        # that field unrenderable and its stored values unexplainable. The
        # service turns the resulting refusal into a 409 that names the fields.
        ForeignKey(f"{CRM_SCHEMA}.picklists.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # --- Validation rules --------------------------------------------------
    #
    # Nullable throughout: "no rule" is the common case and must not be
    # spelled as a sentinel value that a legitimate bound could collide with.

    min_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    max_value: Mapped[float | None] = mapped_column(Numeric(20, 6), nullable=True)
    min_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: A RE2-safe regular expression the value must match in full. Compiled and
    #: rejected at definition time, so a pattern that cannot compile never
    #: reaches a record write.
    pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)

    @property
    def is_picklist(self) -> bool:
        return self.field_type in PICKLIST_TYPES


__all__ = [
    "CUSTOM_FIELD_ENTITY_TYPES",
    "FILTERABLE_TYPES",
    "MAX_FIELDS_PER_ENTITY",
    "MAX_OPTIONS_PER_PICKLIST",
    "MAX_VALUE_LENGTH",
    "PICKLIST_TYPES",
    "SORTABLE_TYPES",
    "CustomFieldDefinition",
    "CustomFieldType",
    "CustomFieldValuesMixin",
    "Picklist",
    "PicklistOption",
]
