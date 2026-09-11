"""Business rules for the record layout / form builder (Checkpoint 4).

One service, :class:`LayoutService`, over four tables — the same shape
``PicklistService``/``CustomFieldService`` share one module for: a layout's
sections, fields and rules have no meaning apart from the layout that owns
them, and a caller never wants "a section" without also knowing which layout
it belongs to.

**What publishing means, precisely**, because the whole conditional-fields
feature turns on it:

* A layout is created and edited as ``DRAFT``. Nothing reads a draft except
  the builder screen that is editing it — no form renders against it, and
  :class:`~app.products.crm.custom_fields.service.CustomFieldValueService`
  does not consult it.
* :meth:`LayoutService.publish` makes one layout, for one entity type, the
  live one: every new form render and every write's conditional-required
  check uses it from that moment on. Publishing a second layout for the same
  entity type demotes the incumbent to ``DRAFT`` (never deletes it) — the same
  "clear the old claim before the new one can be written" ordering
  ``PicklistService.add_option`` uses for a picklist's single default, and for
  the identical reason: the partial unique index on
  ``(organization_id, entity_type)`` where ``status = 'PUBLISHED'`` does not
  tolerate two publishers even momentarily inside one transaction.
* A layout is validated before it may publish: every placed field's
  ``field_key`` must still resolve (a built-in field the schema still has, or
  an active custom field definition), and every rule's ``target_field_key``
  must be a *placed*, active custom field. A layout that fails validation
  stays a draft with a 422 naming what is wrong — publishing a broken layout
  would make every record write for that entity type start evaluating rules
  against fields that no longer exist.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.platform.audit.service import Action as AuditAction
from app.products.crm.common import CrmEntityType
from app.products.crm.custom_fields.repository import CustomFieldDefinitionRepository
from app.products.crm.layouts.catalog import (
    builtin_field_names,
    custom_field_api_name,
    is_custom_field_key,
    is_layout_entity,
)
from app.products.crm.layouts.evaluate import FieldState, effective_custom_field_states
from app.products.crm.layouts.models import (
    MAX_FIELDS_PER_LAYOUT,
    MAX_RULES_PER_LAYOUT,
    MAX_SECTIONS_PER_LAYOUT,
    LayoutField,
    LayoutFieldRule,
    LayoutSection,
    LayoutStatus,
    RecordLayout,
)
from app.products.crm.layouts.repository import (
    LayoutFieldRepository,
    LayoutFieldRuleRepository,
    LayoutSectionRepository,
    RecordLayoutRepository,
)
from app.products.crm.shared.service import TenantScopedService


class UnknownFieldKeyError(ValidationFailedError):
    pass


class DuplicateFieldPlacementError(ConflictError):
    code = "field_already_placed"
    message = "That field is already placed on this layout."


class LayoutNotPublishableError(ValidationFailedError):
    pass


class LayoutService(TenantScopedService[RecordLayout]):
    entity_name = "Layout"

    def __init__(self, session: AsyncSession) -> None:
        self._layouts = RecordLayoutRepository(session)
        super().__init__(self._layouts, RecordLayout)
        self._session = session
        self._sections = LayoutSectionRepository(session)
        self._fields = LayoutFieldRepository(session)
        self._rules = LayoutFieldRuleRepository(session)
        self._definitions = CustomFieldDefinitionRepository(session)

    @property
    def audit_module(self) -> str:
        return "record_layouts"

    # --- Layouts -------------------------------------------------------

    async def list_for_entity(
        self, organization_id: uuid.UUID, entity_type: CrmEntityType
    ) -> Sequence[RecordLayout]:
        self._require_layout_entity(entity_type)
        return await self._layouts.for_entity(organization_id, entity_type)

    async def create_layout(
        self, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> RecordLayout:
        entity_type = values.get("entity_type")
        if not isinstance(entity_type, CrmEntityType):
            entity_type = CrmEntityType(str(entity_type))
        self._require_layout_entity(entity_type)
        return await self.create(
            organization_id=organization_id,
            actor_id=actor_id,
            values={**values, "entity_type": entity_type, "status": LayoutStatus.DRAFT},
        )

    async def archive_layout(
        self, layout: RecordLayout, *, actor_id: uuid.UUID | None
    ) -> RecordLayout:
        """Retire a layout. A published layout may not be archived directly.

        Archiving the live layout would leave the entity type with no
        published layout at all, silently turning off every conditional rule
        mid-flight for records already relying on it. An administrator must
        publish a replacement (or explicitly demote this one) first.
        """
        if layout.status is LayoutStatus.PUBLISHED:
            raise ValidationFailedError(
                "This layout is published. Publish another layout for this "
                "record type before archiving it."
            )
        return await self.soft_delete(layout, actor_id=actor_id)

    async def publish(self, layout: RecordLayout, *, actor_id: uuid.UUID | None) -> RecordLayout:
        sections = await self._sections.for_layout(layout.organization_id, layout.id)
        fields = await self._fields.for_layout(layout.organization_id, layout.id)
        rules = await self._rules.for_layout(layout.organization_id, layout.id)
        await self._validate_publishable(layout, fields=fields, rules=rules)

        incumbent = await self._layouts.published_for(layout.organization_id, layout.entity_type)
        if incumbent is not None and incumbent.id != layout.id:
            incumbent.status = LayoutStatus.DRAFT
            incumbent.updated_by_id = actor_id

        layout.status = LayoutStatus.PUBLISHED
        layout.published_at = dt.datetime.now(dt.UTC)
        layout.updated_by_id = actor_id
        await self._session.flush()

        await self.audit.record(
            organization_id=layout.organization_id,
            action=AuditAction.UPDATED,
            module=self.audit_module,
            entity_type="RECORD_LAYOUT",
            entity_id=layout.id,
            entity_label=layout.name,
            actor_id=actor_id,
            details={
                "published": True,
                "entity_type": layout.entity_type.value,
                "sections": len(sections),
                "fields": len(fields),
                "rules": len(rules),
            },
        )
        return layout

    async def unpublish(self, layout: RecordLayout, *, actor_id: uuid.UUID | None) -> RecordLayout:
        """Demote a published layout back to draft, leaving no layout live.

        A deliberate, explicit act — unlike ``publish``, which always leaves
        exactly one layout live, this can leave the entity type with none.
        That is a valid state (conditional rules simply do not apply, and
        every field falls back to its own base configuration) and is why
        ``CustomFieldValueService.resolve`` treats "no published layout" as
        "nothing to evaluate" rather than an error.
        """
        if layout.status is not LayoutStatus.PUBLISHED:
            return layout
        layout.status = LayoutStatus.DRAFT
        layout.updated_by_id = actor_id
        await self._session.flush()
        await self.audit.record(
            organization_id=layout.organization_id,
            action=AuditAction.UPDATED,
            module=self.audit_module,
            entity_type="RECORD_LAYOUT",
            entity_id=layout.id,
            entity_label=layout.name,
            actor_id=actor_id,
            details={"published": False},
        )
        return layout

    async def _validate_publishable(
        self,
        layout: RecordLayout,
        *,
        fields: Sequence[LayoutField],
        rules: Sequence[LayoutFieldRule],
    ) -> None:
        if not fields:
            raise LayoutNotPublishableError("A layout needs at least one field before publishing.")

        builtins = builtin_field_names(layout.entity_type)
        definitions = await self._definitions.for_entity(
            layout.organization_id, layout.entity_type, include_inactive=False
        )
        active_custom = {definition.api_name for definition in definitions}

        placed_keys = {field.field_key for field in fields}
        bad_fields = sorted(
            key
            for key in placed_keys
            if not (
                (is_custom_field_key(key) and custom_field_api_name(key) in active_custom)
                or (not is_custom_field_key(key) and key in builtins)
            )
        )
        if bad_fields:
            raise LayoutNotPublishableError(
                "These placed fields no longer exist: "
                + ", ".join(bad_fields)
                + ". Remove them before publishing.",
                details={"fields": bad_fields},
            )

        bad_targets = sorted(
            rule.target_field_key
            for rule in rules
            if rule.target_field_key not in placed_keys
            or custom_field_api_name(rule.target_field_key) not in active_custom
        )
        if bad_targets:
            raise LayoutNotPublishableError(
                "These rules target a field that is not an active, placed "
                "custom field: " + ", ".join(sorted(set(bad_targets))) + ".",
                details={"fields": sorted(set(bad_targets))},
            )

    # --- Sections --------------------------------------------------------

    async def add_section(
        self, layout: RecordLayout, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> LayoutSection:
        existing = await self._sections.for_layout(layout.organization_id, layout.id)
        if len(existing) >= MAX_SECTIONS_PER_LAYOUT:
            raise ValidationFailedError(
                f"A layout may have at most {MAX_SECTIONS_PER_LAYOUT} sections."
            )
        position = values.get("position")
        if position is None:
            position = (max((s.position for s in existing), default=-1)) + 1
        section = LayoutSection(
            organization_id=layout.organization_id,
            layout_id=layout.id,
            name=str(values["name"]).strip(),
            position=int(position),
            columns=int(values.get("columns") or 1),
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(section)
        await self._session.flush()
        return section

    async def update_section(
        self, section: LayoutSection, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> LayoutSection:
        if values.get("name") is not None:
            section.name = str(values["name"]).strip()
        if values.get("position") is not None:
            section.position = int(values["position"])
        if values.get("columns") is not None:
            section.columns = int(values["columns"])
        section.updated_by_id = actor_id
        await self._session.flush()
        return section

    async def remove_section(
        self, section: LayoutSection, *, actor_id: uuid.UUID | None
    ) -> None:
        """Remove a section and every field placed inside it.

        Fields are soft-deleted alongside it rather than left orphaned: a
        ``LayoutField`` with no live parent section could not be rendered or
        moved, and leaving it would silently shrink the layout the next time
        it was loaded with no record of why.
        """
        fields = await self._fields.for_layout(section.organization_id, section.layout_id)
        now = dt.datetime.now(dt.UTC)
        for field in fields:
            if field.section_id == section.id:
                field.deleted_at = now
                field.updated_by_id = actor_id
        section.deleted_at = now
        section.updated_by_id = actor_id
        await self._session.flush()

    async def get_section_or_404(
        self, layout: RecordLayout, section_id: uuid.UUID
    ) -> LayoutSection:
        section = await self._sections.get(section_id, layout.organization_id)
        if section is None or section.layout_id != layout.id:
            raise NotFoundError("Section not found.")
        return section

    # --- Fields ------------------------------------------------------------

    async def add_field(
        self, layout: RecordLayout, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> LayoutField:
        section = await self.get_section_or_404(layout, values["section_id"])
        field_key = str(values["field_key"]).strip()
        await self._require_resolvable_field_key(layout, field_key)

        existing = await self._fields.for_layout(layout.organization_id, layout.id)
        if len(existing) >= MAX_FIELDS_PER_LAYOUT:
            raise ValidationFailedError(
                f"A layout may have at most {MAX_FIELDS_PER_LAYOUT} fields."
            )
        if await self._fields.field_key_taken(layout.id, field_key):
            raise DuplicateFieldPlacementError

        position = values.get("position")
        if position is None:
            in_section = [f for f in existing if f.section_id == section.id]
            position = (max((f.position for f in in_section), default=-1)) + 1

        field = LayoutField(
            organization_id=layout.organization_id,
            layout_id=layout.id,
            section_id=section.id,
            field_key=field_key,
            position=int(position),
            column_span=int(values.get("column_span") or 1),
            is_visible=bool(values.get("is_visible", True)),
            is_required_override=values.get("is_required_override"),
            is_read_only=bool(values.get("is_read_only", False)),
            label_override=_clean(values.get("label_override")),
            help_text_override=_clean(values.get("help_text_override")),
            placeholder_override=_clean(values.get("placeholder_override")),
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(field)
        await self._session.flush()
        return field

    async def update_field(
        self, field: LayoutField, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> LayoutField:
        if values.get("section_id") is not None and values["section_id"] != field.section_id:
            layout = await self.get_or_404(field.layout_id, field.organization_id)
            new_section = await self.get_section_or_404(layout, values["section_id"])
            field.section_id = new_section.id
        if values.get("position") is not None:
            field.position = int(values["position"])
        if values.get("column_span") is not None:
            field.column_span = int(values["column_span"])
        if values.get("is_visible") is not None:
            field.is_visible = bool(values["is_visible"])
        if values.get("clear_required_override"):
            field.is_required_override = None
        elif "is_required_override" in values and values["is_required_override"] is not None:
            field.is_required_override = bool(values["is_required_override"])
        if values.get("is_read_only") is not None:
            field.is_read_only = bool(values["is_read_only"])
        if "label_override" in values:
            field.label_override = _clean(values["label_override"])
        if "help_text_override" in values:
            field.help_text_override = _clean(values["help_text_override"])
        if "placeholder_override" in values:
            field.placeholder_override = _clean(values["placeholder_override"])
        field.updated_by_id = actor_id
        await self._session.flush()
        return field

    async def remove_field(self, field: LayoutField, *, actor_id: uuid.UUID | None) -> None:
        field.updated_by_id = actor_id
        field.deleted_at = dt.datetime.now(dt.UTC)
        await self._session.flush()

    async def get_field_or_404(self, layout: RecordLayout, field_id: uuid.UUID) -> LayoutField:
        field = await self._fields.get(field_id, layout.organization_id)
        if field is None or field.layout_id != layout.id:
            raise NotFoundError("Layout field not found.")
        return field

    async def reorder_fields(
        self,
        layout: RecordLayout,
        *,
        actor_id: uuid.UUID | None,
        entries: Sequence[Mapping[str, Any]],
    ) -> Sequence[LayoutField]:
        """Apply a drag-and-drop's complete new arrangement in one call.

        Takes every field's new ``(section_id, position)`` at once, for the
        reason ``CustomFieldService.reorder`` takes a whole order: a partial
        update could leave two fields claiming the same slot, which is not a
        state any drag-and-drop UI could have produced deliberately.
        """
        existing = await self._fields.for_layout(layout.organization_id, layout.id)
        by_id = {field.id: field for field in existing}
        submitted_ids = [entry["field_id"] for entry in entries]
        if len(submitted_ids) != len(set(submitted_ids)) or set(submitted_ids) != set(by_id):
            raise ValidationFailedError(
                "The arrangement must list every field on this layout exactly once."
            )
        section_ids = {section.id for section in await self._sections.for_layout(
            layout.organization_id, layout.id
        )}
        for entry in entries:
            if entry["section_id"] not in section_ids:
                raise NotFoundError("Section not found.")

        for entry in entries:
            field = by_id[entry["field_id"]]
            field.section_id = entry["section_id"]
            field.position = int(entry["position"])
            field.updated_by_id = actor_id
        await self._session.flush()

        await self.audit.record(
            organization_id=layout.organization_id,
            action=AuditAction.UPDATED,
            module=self.audit_module,
            entity_type="RECORD_LAYOUT",
            entity_id=layout.id,
            entity_label=layout.name,
            actor_id=actor_id,
            details={"reordered_fields": len(entries)},
        )
        return await self._fields.for_layout(layout.organization_id, layout.id)

    # --- Rules ---------------------------------------------------------

    async def add_rule(
        self, layout: RecordLayout, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> LayoutFieldRule:
        target = str(values["target_field_key"]).strip()
        await self._require_placed_custom_field(layout, target)

        existing = await self._rules.for_layout(layout.organization_id, layout.id)
        if len(existing) >= MAX_RULES_PER_LAYOUT:
            raise ValidationFailedError(f"A layout may have at most {MAX_RULES_PER_LAYOUT} rules.")

        conditions = _dump_conditions(values.get("conditions") or [])
        for condition in conditions:
            self._require_known_field_key(layout.entity_type, str(condition.get("field_key", "")))

        rule = LayoutFieldRule(
            organization_id=layout.organization_id,
            layout_id=layout.id,
            name=_clean(values.get("name")),
            target_field_key=target,
            logic=values.get("logic") or "AND",
            conditions=conditions,
            effect_visible=bool(values.get("effect_visible", True)),
            effect_required=values.get("effect_required"),
            position=(max((r.position for r in existing), default=-1)) + 1,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(rule)
        await self._session.flush()
        return rule

    async def update_rule(
        self, rule: LayoutFieldRule, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> LayoutFieldRule:
        if "name" in values:
            rule.name = _clean(values["name"])
        if values.get("logic") is not None:
            rule.logic = values["logic"]
        if values.get("conditions") is not None:
            layout = await self.get_or_404(rule.layout_id, rule.organization_id)
            conditions = _dump_conditions(values["conditions"])
            for condition in conditions:
                self._require_known_field_key(
                    layout.entity_type, str(condition.get("field_key", ""))
                )
            rule.conditions = conditions
        if values.get("effect_visible") is not None:
            rule.effect_visible = bool(values["effect_visible"])
        if values.get("clear_effect_required"):
            rule.effect_required = None
        elif "effect_required" in values and values["effect_required"] is not None:
            rule.effect_required = bool(values["effect_required"])
        rule.updated_by_id = actor_id
        await self._session.flush()
        return rule

    async def remove_rule(self, rule: LayoutFieldRule, *, actor_id: uuid.UUID | None) -> None:
        rule.updated_by_id = actor_id
        rule.deleted_at = dt.datetime.now(dt.UTC)
        await self._session.flush()

    async def get_rule_or_404(self, layout: RecordLayout, rule_id: uuid.UUID) -> LayoutFieldRule:
        rule = await self._rules.get(rule_id, layout.organization_id)
        if rule is None or rule.layout_id != layout.id:
            raise NotFoundError("Rule not found.")
        return rule

    # --- Reads for the builder / form renderer ------------------------------

    async def sections_with_fields(
        self, layout: RecordLayout
    ) -> list[tuple[LayoutSection, list[LayoutField]]]:
        sections = await self._sections.for_layout(layout.organization_id, layout.id)
        fields = await self._fields.for_layout(layout.organization_id, layout.id)
        by_section: dict[uuid.UUID, list[LayoutField]] = {section.id: [] for section in sections}
        for field in sorted(fields, key=lambda f: f.position):
            by_section.setdefault(field.section_id, []).append(field)
        return [(section, by_section.get(section.id, [])) for section in sections]

    async def rules_for(self, layout: RecordLayout) -> Sequence[LayoutFieldRule]:
        return await self._rules.for_layout(layout.organization_id, layout.id)

    async def fields_in_section(self, section: LayoutSection) -> Sequence[LayoutField]:
        fields = await self._fields.for_layout(section.organization_id, section.layout_id)
        return sorted(
            (field for field in fields if field.section_id == section.id),
            key=lambda f: f.position,
        )

    async def available_fields(
        self, layout: RecordLayout
    ) -> list[tuple[str, str, bool, bool, bool]]:
        """``(field_key, label, is_custom, is_required_base, placed)`` for the picker."""
        placed = {field.field_key for field in await self._fields.for_layout(
            layout.organization_id, layout.id
        )}
        result: list[tuple[str, str, bool, bool, bool]] = [
            (name, name.replace("_", " ").title(), False, False, name in placed)
            for name in sorted(builtin_field_names(layout.entity_type))
        ]
        definitions = await self._definitions.for_entity(
            layout.organization_id, layout.entity_type, include_inactive=False
        )
        for definition in definitions:
            key = f"custom:{definition.api_name}"
            result.append(
                (key, definition.label, True, definition.is_required, key in placed)
            )
        return result

    async def evaluate_states(
        self, layout: RecordLayout, values: Mapping[str, Any]
    ) -> dict[str, FieldState]:
        """Live preview of every rule-governed custom field, for the builder.

        Calls the exact function
        :class:`~app.products.crm.custom_fields.service.CustomFieldValueService`
        calls on write — see :mod:`.evaluate` — so what the builder previews
        and what the server enforces cannot disagree.
        """
        rules = await self._rules.for_layout(layout.organization_id, layout.id)
        fields = await self._fields.for_layout(layout.organization_id, layout.id)
        base_required = {
            field.field_key: bool(field.is_required_override)
            for field in fields
            if is_custom_field_key(field.field_key) and field.is_required_override is not None
        }
        base_visible = {
            field.field_key: field.is_visible
            for field in fields
            if is_custom_field_key(field.field_key)
        }
        return effective_custom_field_states(
            list(rules), values, base_visible=base_visible, base_required=base_required
        )

    # --- Validation helpers --------------------------------------------

    def _require_layout_entity(self, entity_type: CrmEntityType) -> None:
        if not is_layout_entity(entity_type):
            raise ValidationFailedError(
                f"The layout builder does not support {entity_type.value} records."
            )

    def _require_known_field_key(self, entity_type: CrmEntityType, field_key: str) -> None:
        if is_custom_field_key(field_key):
            return  # Existence of the definition is checked where org context is available.
        if field_key not in builtin_field_names(entity_type):
            raise UnknownFieldKeyError(f"'{field_key}' is not a field on {entity_type.value}.")

    async def _require_resolvable_field_key(self, layout: RecordLayout, field_key: str) -> None:
        """Like :meth:`_require_known_field_key`, but resolves a custom key too.

        Used when placing a field on a layout (org context is available), so
        an administrator learns immediately that ``custom:doesnotexist`` is
        not a real field rather than only at publish time.
        """
        if not is_custom_field_key(field_key):
            self._require_known_field_key(layout.entity_type, field_key)
            return
        definitions = await self._definitions.for_entity(
            layout.organization_id, layout.entity_type, include_inactive=False
        )
        if custom_field_api_name(field_key) not in {d.api_name for d in definitions}:
            raise UnknownFieldKeyError(
                f"'{field_key}' is not an active custom field on {layout.entity_type.value}."
            )

    async def _require_placed_custom_field(self, layout: RecordLayout, field_key: str) -> None:
        if not is_custom_field_key(field_key):
            raise ValidationFailedError(
                "A rule may only target a tenant-defined (custom) field. "
                "See the layout builder documentation for why."
            )
        if not await self._fields.field_key_taken(layout.id, field_key):
            raise ValidationFailedError(
                "Place this field on the layout before adding a rule for it."
            )


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dump_conditions(conditions: Sequence[Any]) -> list[dict[str, Any]]:
    dumped = []
    for condition in conditions:
        if hasattr(condition, "model_dump"):
            dumped.append(condition.model_dump(mode="json"))
        else:
            dumped.append(dict(condition))
    return dumped


__all__ = [
    "DuplicateFieldPlacementError",
    "LayoutNotPublishableError",
    "LayoutService",
    "UnknownFieldKeyError",
]
