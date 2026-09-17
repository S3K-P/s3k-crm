"""SQLAlchemy models for the record layout / form builder (Checkpoint 4).

Four tables, normalized rather than one JSONB blob, for the same reason
``dashboard_components`` and ``custom_field_definitions`` are: a layout is
edited a field or a section at a time — reordered, moved between sections,
individually patched — and a JSONB document would need to be read, mutated in
Python and rewritten whole on every one of those, with no way for two people
editing different sections at once to avoid clobbering each other. A normalized
child row is a unit SQL can update, order and constrain on its own.

**Draft vs published, and why there are two states at all.** An administrator
building a layout is not the same act as a layout being *live*: nothing renders
against a layout mid-edit, and "save" must not mean "every rep's form changes
right now". So a layout is created and edited as ``DRAFT``; :meth:`.service.LayoutService.publish`
is the one act that makes it the layout new forms render against and the one
:class:`~app.products.crm.custom_fields.service.CustomFieldValueService`
consults for conditional required-ness. Publishing a second layout for the same
entity type demotes the incumbent to ``DRAFT`` rather than deleting it —
publishing is reversible by construction: republish the old one.

**Field targeting.** A placed field (:class:`LayoutField`) or a rule's target
(:class:`LayoutFieldRule`) is named by ``field_key``, a string rather than a
foreign key, because a layout field can name either a built-in column (e.g.
``"email"``) or a tenant-defined one (``"custom:region"``) and the two live in
different tables. :mod:`.catalog` is the single place that knows how to
resolve and validate a ``field_key`` against an entity type's real fields.

**Why a rule's *target* must be a custom field.** A rule's ``conditions`` may
read any field on the record — built-in or custom, since evaluating "is this
condition true" only needs to *read* a value. But a rule's ``effect`` writes a
requiredness decision, and a built-in field's requiredness is already fixed by
that entity's Pydantic schema (``LeadCreate.company: str | None`` cannot become
un-optional at request-validation time without rewriting five schema modules to
consult the database before they can validate a body at all — a much larger and
riskier change than this checkpoint should make). Restricting a rule's target
to ``custom:``-prefixed fields keeps the effect enforceable exactly where the
codebase already enforces field requiredness dynamically:
:class:`~app.products.crm.custom_fields.service.CustomFieldValueService`. A
built-in field can still be *positioned* in a layout section and hidden in the
rendered preview; it just cannot be the target of a server-enforced rule.
See :mod:`.evaluate` for the exact precedence a rule resolves against.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, CrmEntityType

#: Grid width available to a section. Two rather than twelve: a record form is
#: read top-to-bottom, and Zoho-class CRMs offer one or two columns, never
#: more — a third column on a form this narrow would make every field too
#: cramped to hold its own label.
MAX_SECTION_COLUMNS = 2

#: Ceiling on sections, fields and rules per layout — the same "every one of
#: these is loaded and evaluated on every render or write" reasoning
#: ``custom_fields.models.MAX_FIELDS_PER_ENTITY`` documents.
MAX_SECTIONS_PER_LAYOUT = 40
MAX_FIELDS_PER_LAYOUT = 200
MAX_RULES_PER_LAYOUT = 100
MAX_CONDITIONS_PER_RULE = 10


class LayoutStatus(enum.StrEnum):
    """Where a layout is in its edit/publish lifecycle."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"


class LayoutType(enum.StrEnum):
    """Which screen a layout arranges fields for.

    Zoho-style CRMs let an administrator configure the full record form, a
    lightweight "Quick Create" popup, and the read-mostly detail view
    independently — the same section can hold different fields, in a
    different order, with different requiredness, depending which of the
    three a rep is looking at. Before this member existed, one published
    layout per entity type drove all three at once (see the migration
    ``20260921_0200``, which backfills every pre-existing row as ``DETAIL``
    and is why the server-side fallback in
    :meth:`~app.products.crm.layouts.repository.RecordLayoutRepository.published_for_with_fallback`
    exists: an organization that published a layout before this member was
    added keeps exactly the behavior it had, on every screen, until an
    administrator deliberately publishes a narrower one).
    """

    CREATE = "CREATE"
    QUICK_CREATE = "QUICK_CREATE"
    DETAIL = "DETAIL"


class RuleLogic(enum.StrEnum):
    """How a rule's conditions combine."""

    AND = "AND"
    OR = "OR"


class RecordLayout(Base, CrmEntityMixin):
    """One named arrangement of fields for one record type."""

    __tablename__ = "record_layouts"
    __table_args__ = (
        Index(
            "uq_record_layouts_organization_id_entity_type_name_live",
            "organization_id",
            "entity_type",
            "layout_type",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # At most one published layout per entity type *and screen* — the one
        # that screen's form renders against, and (for CREATE/DETAIL) the one
        # custom-field validation consults. See the module docstring for why
        # publishing demotes rather than deletes.
        Index(
            "uq_record_layouts_organization_id_entity_type_published",
            "organization_id",
            "entity_type",
            "layout_type",
            unique=True,
            postgresql_where=text("status = 'PUBLISHED' AND deleted_at IS NULL"),
        ),
        Index(
            "ix_record_layouts_organization_id_entity_type",
            "organization_id",
            "entity_type",
        ),
        {"schema": CRM_SCHEMA},
    )

    entity_type: Mapped[CrmEntityType] = mapped_column(
        Enum(CrmEntityType, name="crm_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    #: Which screen this layout arranges fields for. See :class:`LayoutType`.
    layout_type: Mapped[LayoutType] = mapped_column(
        Enum(LayoutType, name="layout_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=LayoutType.DETAIL,
        server_default=LayoutType.DETAIL.value,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[LayoutStatus] = mapped_column(
        Enum(LayoutStatus, name="layout_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=LayoutStatus.DRAFT,
        server_default=LayoutStatus.DRAFT.value,
    )
    #: Set (and reset) each time :meth:`~.service.LayoutService.publish` makes
    #: this layout the live one. ``NULL`` for a layout that has never been
    #: published, or a demoted one that has not been republished since.
    published_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_published(self) -> bool:
        return self.status is LayoutStatus.PUBLISHED


class LayoutSection(Base, CrmEntityMixin):
    """One group of fields within a layout, rendered as a titled block."""

    __tablename__ = "layout_sections"
    __table_args__ = (
        CheckConstraint(
            f"columns BETWEEN 1 AND {MAX_SECTION_COLUMNS}", name="ck_layout_sections_columns"
        ),
        CheckConstraint("position >= 0", name="ck_layout_sections_position"),
        Index(
            "ix_layout_sections_organization_id_layout_id",
            "organization_id",
            "layout_id",
        ),
        {"schema": CRM_SCHEMA},
    )

    layout_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.record_layouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    columns: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class LayoutField(Base, CrmEntityMixin):
    """One field placed into one section of a layout.

    ``field_key`` is validated by :mod:`.catalog` against the layout's own
    ``entity_type`` at write time — never at read time, so a field retired
    after being placed does not make the layout unreadable, only unpublishable
    until an administrator removes it (:meth:`~.service.LayoutService.publish`).
    """

    __tablename__ = "layout_fields"
    __table_args__ = (
        CheckConstraint(
            f"column_span BETWEEN 1 AND {MAX_SECTION_COLUMNS}",
            name="ck_layout_fields_column_span",
        ),
        CheckConstraint("position >= 0", name="ck_layout_fields_position"),
        Index(
            "uq_layout_fields_layout_id_field_key_live",
            "layout_id",
            "field_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_layout_fields_organization_id_layout_id", "organization_id", "layout_id"),
        Index("ix_layout_fields_organization_id_section_id", "organization_id", "section_id"),
        {"schema": CRM_SCHEMA},
    )

    #: Denormalized alongside ``section_id`` so "every field on this layout"
    #: is one indexed query rather than a join through every section.
    layout_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.record_layouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.layout_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: ``"email"`` for a built-in column, ``"custom:region"`` for a
    #: tenant-defined field. See the module docstring.
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    column_span: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    #: Base visibility, before any :class:`LayoutFieldRule` is evaluated. A
    #: rule may still override this at read/write time — see ``.evaluate``.
    is_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    #: ``NULL`` means "use the field's own default" (the custom field
    #: definition's ``is_required``, or the built-in schema's own rule).
    #: ``TRUE``/``FALSE`` overrides it for this layout only. See the module
    #: docstring for why an override on a *built-in* field is display-only.
    is_required_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_read_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    label_override: Mapped[str | None] = mapped_column(String(160), nullable=True)
    help_text_override: Mapped[str | None] = mapped_column(String(500), nullable=True)
    placeholder_override: Mapped[str | None] = mapped_column(String(160), nullable=True)


class LayoutFieldRule(Base, CrmEntityMixin):
    """A conditional visibility/requiredness rule targeting one custom field.

    ``conditions`` is a JSON array of ``{"field_key", "operator", "value"}``
    objects, combined by ``logic``. Stored as JSONB rather than a child table
    because a condition has no identity of its own to update independently —
    the whole list is replaced together, exactly the way a saved view's
    ``filters`` document is (``views/models.py``).

    ``position`` decides precedence when more than one rule targets the same
    field and both match: the later rule (higher position) wins, applied in
    order — see :func:`.evaluate.effective_custom_field_states`. This is
    stated once here and once at the point it is applied, deliberately: an
    administrator authoring several rules for one field needs to know the
    order is meaningful, and the evaluator needs to know why it iterates in
    that order rather than any other.
    """

    __tablename__ = "layout_field_rules"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_layout_field_rules_position"),
        Index("ix_layout_field_rules_organization_id_layout_id", "organization_id", "layout_id"),
        {"schema": CRM_SCHEMA},
    )

    layout_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.record_layouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    #: Always ``"custom:<api_name>"`` — see the module docstring for why a
    #: rule's effect cannot target a built-in field.
    target_field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    logic: Mapped[RuleLogic] = mapped_column(
        Enum(RuleLogic, name="layout_rule_logic", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=RuleLogic.AND,
        server_default=RuleLogic.AND.value,
    )
    conditions: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    effect_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: ``NULL`` means the rule does not change requiredness when it matches —
    #: only visibility. ``TRUE``/``FALSE`` forces the target's requiredness
    #: while the rule matches, taking precedence over the field's own
    #: definition and over the layout field's own ``is_required_override``.
    effect_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


__all__ = [
    "MAX_CONDITIONS_PER_RULE",
    "MAX_FIELDS_PER_LAYOUT",
    "MAX_RULES_PER_LAYOUT",
    "MAX_SECTIONS_PER_LAYOUT",
    "MAX_SECTION_COLUMNS",
    "LayoutField",
    "LayoutFieldRule",
    "LayoutSection",
    "LayoutStatus",
    "LayoutType",
    "RecordLayout",
    "RuleLogic",
]
