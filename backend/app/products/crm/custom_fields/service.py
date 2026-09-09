"""Business rules for tenant-defined fields and picklists (Phase E).

Three services, one per thing an administrator manipulates and one for the
thing every record write goes through:

* :class:`PicklistService` — option sets and their options.
* :class:`CustomFieldService` — field definitions.
* :class:`CustomFieldValueService` — resolving a record's submitted custom
  values against the definitions that apply to it.

The last is the one with a hard guarantee attached. It is reached from
:class:`~app.products.crm.shared.service.TenantScopedService`, which every CRM
entity write funnels through, so a record cannot be written with a custom value
that was never validated — including by a module added later that nobody
remembered to wire up.

**What "deactivated" means, precisely**, because the whole design turns on it:

* An *inactive definition* is not rendered, not required and not validated.
  Values already stored under it are left exactly as they are and are still
  returned, so retiring a field never destroys the data collected through it.
  A write that supplies a value for one is refused — quietly accepting it would
  store data against a field the product has stopped promising anything about.
* An *inactive option* cannot be newly selected, but a record already holding
  it keeps it, and re-saving that record without touching the field keeps it
  too. This is the case the naive implementation gets wrong: validating the
  whole document against the live option set on every write would silently
  strip a colleague's historical value the first time anybody edited an
  unrelated field on that record.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.products.crm.common import CrmEntityType
from app.products.crm.custom_fields.models import (
    MAX_FIELDS_PER_ENTITY,
    MAX_OPTIONS_PER_PICKLIST,
    PICKLIST_TYPES,
    CustomFieldDefinition,
    CustomFieldType,
    Picklist,
    PicklistOption,
)
from app.products.crm.custom_fields.repository import (
    CustomFieldDefinitionRepository,
    PicklistRepository,
)
from app.products.crm.custom_fields.validation import (
    CustomFieldValueError,
    coerce,
    compile_pattern,
    is_empty,
)
from app.products.crm.shared.service import TenantScopedService

#: A machine name: lowercase, starts with a letter, letters/digits/underscores.
#:
#: Restrictive on purpose. The value becomes a JSON object key, a query-string
#: parameter (``?cf_region=EMEA``), a CSV column header and a React form field
#: name. Anything permitted here has to survive all four, and the intersection
#: of what those accept unambiguously is this.
_API_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

#: Names an administrator may not claim, because a record already has them.
#:
#: A custom field called ``id`` or ``owner_id`` would be legal in the JSONB
#: document but ruinous everywhere the two are merged for display, export or
#: import — the built-in column and the custom one would each appear to be the
#: other's value depending on which the code reached first.
_RESERVED_API_NAMES: frozenset[str] = frozenset(
    {
        "id",
        "organization_id",
        "created_at",
        "updated_at",
        "created_by_id",
        "updated_by_id",
        "deleted_at",
        "owner_id",
        "custom_fields",
        "search_vector",
    }
)


class DuplicateApiNameError(ConflictError):
    code = "duplicate_api_name"
    message = "A field with that API name already exists on this record type."


class DuplicatePicklistError(ConflictError):
    code = "duplicate_picklist"
    message = "A picklist with that API name already exists."


class DuplicateOptionError(ConflictError):
    code = "duplicate_picklist_option"
    message = "That option value is already in this picklist."


class PicklistInUseError(ConflictError):
    code = "picklist_in_use"
    message = "This picklist is still used by custom fields. Remove them first."


class FieldLimitReachedError(ConflictError):
    code = "custom_field_limit_reached"
    message = f"A record type may have at most {MAX_FIELDS_PER_ENTITY} custom fields."


class OptionLimitReachedError(ConflictError):
    code = "picklist_option_limit_reached"
    message = f"A picklist may have at most {MAX_OPTIONS_PER_PICKLIST} options."


# ---------------------------------------------------------------------------
# Picklists
# ---------------------------------------------------------------------------


class PicklistService(TenantScopedService[Picklist]):
    """Option sets, and the options inside them."""

    entity_name = "Picklist"

    def __init__(self, session: AsyncSession) -> None:
        self._picklists = PicklistRepository(session)
        super().__init__(self._picklists, Picklist)
        self._session = session
        self._definitions = CustomFieldDefinitionRepository(session)

    @property
    def audit_module(self) -> str:
        # Picklists and field definitions are one permission module, so the
        # trail is filtered by the same word the permission matrix uses. The
        # base class would derive "picklists" from the table name.
        return "custom_fields"

    # --- Lists -------------------------------------------------------------

    async def create_picklist(
        self, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> Picklist:
        api_name = _normalize_api_name(values.get("api_name"))
        if await self._picklists.by_api_name(organization_id, api_name) is not None:
            raise DuplicatePicklistError
        payload = dict(values, api_name=api_name)
        return await self.create(organization_id=organization_id, actor_id=actor_id, values=payload)

    async def update_picklist(
        self, picklist: Picklist, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> Picklist:
        """Patch a list. ``api_name`` is not patchable — see :meth:`_reject_api_name_change`."""
        self._reject_api_name_change(values, picklist.api_name)
        return await self.update(picklist, actor_id=actor_id, values=values)

    async def archive_picklist(self, picklist: Picklist, *, actor_id: uuid.UUID | None) -> Picklist:
        """Archive a list once no live field still draws its options from it.

        Blocked rather than cascaded: removing it would leave those fields
        unrenderable and the values stored through them unexplainable, and the
        foreign key is RESTRICT for the same reason. The refusal names the
        fields so the administrator knows what to change.
        """
        in_use = await self._definitions.using_picklist(picklist.organization_id, picklist.id)
        if in_use:
            raise PicklistInUseError(
                "This picklist is still used by: "
                + ", ".join(sorted(definition.label for definition in in_use))
                + "."
            )
        return await self.soft_delete(picklist, actor_id=actor_id)

    async def option_counts(self, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
        return await self._picklists.option_counts(organization_id)

    # --- Options -----------------------------------------------------------

    async def options(
        self,
        organization_id: uuid.UUID,
        picklist_id: uuid.UUID,
        *,
        include_inactive: bool = True,
    ) -> Sequence[PicklistOption]:
        return await self._picklists.options(
            organization_id, picklist_id, include_inactive=include_inactive
        )

    async def options_for(
        self,
        organization_id: uuid.UUID,
        picklist_ids: Sequence[uuid.UUID],
        *,
        include_inactive: bool = True,
    ) -> Sequence[PicklistOption]:
        """Options of several lists at once, in display order.

        The plural read every caller that renders more than one select uses:
        asking per list is the N+1 the record form would otherwise perform.
        """
        return await self._picklists.options_for(
            organization_id, picklist_ids, include_inactive=include_inactive
        )

    async def get_option_or_404(self, picklist: Picklist, option_id: uuid.UUID) -> PicklistOption:
        """Resolve an option **within a named list**.

        Both halves are checked: the option must be in the caller's
        organization *and* belong to the list in the URL. Without the second,
        ``PATCH /picklists/{a}/options/{b}`` would edit an option of a
        different list whenever the caller guessed a real option id — a
        legitimate id, the wrong parent, and no error anywhere.
        """
        option = await self._picklists.get_option(picklist.organization_id, option_id)
        if option is None or option.picklist_id != picklist.id:
            raise NotFoundError("Picklist option not found.")
        return option

    async def add_option(
        self, picklist: Picklist, *, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> PicklistOption:
        value = str(values.get("value", "")).strip()
        if not value:
            raise ValidationFailedError("An option needs a value.")
        if await self._picklists.option_value_taken(picklist.id, value):
            raise DuplicateOptionError
        if await self._picklists.count_options(picklist.id) >= MAX_OPTIONS_PER_PICKLIST:
            raise OptionLimitReachedError

        option = PicklistOption(
            organization_id=picklist.organization_id,
            picklist_id=picklist.id,
            value=value,
            label=str(values.get("label") or value).strip(),
            position=int(values.get("position") or 0),
            is_active=bool(values.get("is_active", True)),
            is_default=bool(values.get("is_default", False)),
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(option)
        if option.is_default:
            # Demote the incumbent *before* the INSERT reaches the database.
            # The partial unique index does not tolerate two defaults even
            # momentarily inside a transaction, so flushing the new row first
            # and demoting afterwards raises an integrity error rather than
            # doing what the administrator asked.
            await self._picklists.clear_default(picklist.id, excluding=option.id)
        await self._session.flush()
        await self._record_option_change(picklist, option, actor_id=actor_id, action="added")
        return option

    async def update_option(
        self,
        picklist: Picklist,
        option: PicklistOption,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> PicklistOption:
        """Patch an option.

        ``value`` is patchable and renaming it does **not** rewrite stored
        records — a record holding the old value keeps it. That is deliberate
        and is why the API separates ``value`` from ``label``: relabelling is
        the safe, expected operation and is what an administrator almost always
        wants. Changing ``value`` is available for correcting a genuine
        mistake made before the option was ever used, and the response makes no
        claim about records that already hold the old one.
        """
        new_value = values.get("value")
        if new_value is not None:
            new_value = str(new_value).strip()
            if not new_value:
                raise ValidationFailedError("An option needs a value.")
            if new_value.lower() != option.value.lower() and (
                await self._picklists.option_value_taken(
                    picklist.id, new_value, excluding=option.id
                )
            ):
                raise DuplicateOptionError
            option.value = new_value

        if values.get("label"):
            option.label = str(values["label"]).strip()
        if "position" in values and values["position"] is not None:
            option.position = int(values["position"])
        if "is_active" in values and values["is_active"] is not None:
            option.is_active = bool(values["is_active"])
        if "is_default" in values and values["is_default"] is not None:
            option.is_default = bool(values["is_default"])

        option.updated_by_id = actor_id
        if option.is_default:
            # Before the flush, for the reason given in `add_option`.
            await self._picklists.clear_default(picklist.id, excluding=option.id)
        await self._session.flush()
        await self._record_option_change(picklist, option, actor_id=actor_id, action="updated")
        return option

    async def remove_option(
        self, picklist: Picklist, option: PicklistOption, *, actor_id: uuid.UUID | None
    ) -> None:
        """Soft-delete an option.

        Not blocked when records hold it, and this is the design rather than an
        omission. Stored values are strings, so a removed option cannot orphan
        anything: the records that hold it keep rendering it, and it simply
        stops being offered. Blocking would mean scanning five record tables'
        JSONB on every option deletion to produce a refusal an administrator
        can do nothing useful about.
        """
        option.updated_by_id = actor_id
        # Marked here rather than through `PicklistRepository.soft_delete`,
        # which is generic over `Picklist` and would be the wrong table's
        # contract applied to a child row. Soft, like every deletion in the
        # product: the option leaves the API and the records keep their values.
        option.deleted_at = dt.datetime.now(dt.UTC)
        await self._session.flush()
        await self._record_option_change(picklist, option, actor_id=actor_id, action="removed")

    async def _record_option_change(
        self,
        picklist: Picklist,
        option: PicklistOption,
        *,
        actor_id: uuid.UUID | None,
        action: str,
    ) -> None:
        """Append an audit entry for an option change.

        Options are edited through the *list's* audit identity rather than
        their own, so "what happened to the Region picklist" is one readable
        history instead of a scatter of entries about rows whose ids mean
        nothing to the reader.
        """
        from app.platform.audit.service import Action as AuditAction

        await self.audit.record(
            organization_id=picklist.organization_id,
            action=AuditAction.UPDATED,
            module=self.audit_module,
            entity_type="PICKLIST",
            entity_id=picklist.id,
            entity_label=picklist.name,
            actor_id=actor_id,
            details={
                "option": action,
                "value": option.value,
                "label": option.label,
                "is_active": option.is_active,
                "is_default": option.is_default,
            },
        )

    @staticmethod
    def _reject_api_name_change(values: Mapping[str, Any], current: str) -> None:
        submitted = values.get("api_name")
        if submitted is not None and str(submitted).strip().lower() != current.lower():
            raise ValidationFailedError(
                "A picklist's API name cannot be changed: field definitions "
                "resolve their options through it."
            )


# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------


class CustomFieldService(TenantScopedService[CustomFieldDefinition]):
    """Definitions of the fields a tenant has added to a record type."""

    entity_name = "Custom field"

    def __init__(self, session: AsyncSession) -> None:
        self._definitions = CustomFieldDefinitionRepository(session)
        super().__init__(self._definitions, CustomFieldDefinition)
        self._session = session
        self._picklists = PicklistRepository(session)

    @property
    def audit_module(self) -> str:
        return "custom_fields"

    def audit_label(self, entity: CustomFieldDefinition) -> str | None:
        # `label` alone is ambiguous across record types — two entities may
        # each have a "Region". The trail has to say which one moved.
        return f"{entity.entity_type.value}.{entity.api_name}"

    async def for_entity(
        self,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
        *,
        include_inactive: bool = True,
    ) -> Sequence[CustomFieldDefinition]:
        return await self._definitions.for_entity(
            organization_id, entity_type, include_inactive=include_inactive
        )

    async def all_for_organization(
        self, organization_id: uuid.UUID
    ) -> Sequence[CustomFieldDefinition]:
        return await self._definitions.all_for_organization(organization_id)

    async def create_definition(
        self, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, values: dict[str, Any]
    ) -> CustomFieldDefinition:
        entity_type = _require_entity_type(values.get("entity_type"))
        api_name = _normalize_api_name(values.get("api_name"))
        if api_name in _RESERVED_API_NAMES:
            raise ValidationFailedError(
                f"'{api_name}' is reserved by a built-in field. Choose another API name."
            )
        if await self._definitions.api_name_taken(organization_id, entity_type, api_name):
            raise DuplicateApiNameError
        if (
            await self._definitions.count_for_entity(organization_id, entity_type)
            >= MAX_FIELDS_PER_ENTITY
        ):
            raise FieldLimitReachedError

        payload = dict(values, api_name=api_name, entity_type=entity_type)
        await self._validate_configuration(organization_id, payload)
        definition = await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )
        # The default is validated last, against the finished definition, so it
        # is checked by exactly the code a submitted value is checked by.
        # A default that the field itself would reject is a configuration that
        # makes every subsequent record creation fail, which is the kind of
        # thing that must be a 422 here rather than a 500 later.
        await self._validate_default(definition)
        return definition

    async def update_definition(
        self,
        definition: CustomFieldDefinition,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
    ) -> CustomFieldDefinition:
        """Patch a definition, refusing the two changes that would strand data.

        ``api_name`` is the key stored values are filed under and ``field_type``
        decides how they are read back. Changing either would not migrate the
        records that already hold values — it would make them unreadable, or,
        worse, readable as something they are not. The supported way to change
        a field's meaning is to deactivate it and add another, which keeps the
        collected data legible.
        """
        if "api_name" in values and values["api_name"] is not None:
            submitted = _normalize_api_name(values["api_name"])
            if submitted != definition.api_name:
                raise ValidationFailedError(
                    "A field's API name cannot be changed: existing records "
                    "store their values under it. Deactivate this field and "
                    "add a new one instead."
                )
        if "field_type" in values and values["field_type"] is not None:
            submitted_type = _require_field_type(values["field_type"])
            if submitted_type is not definition.field_type:
                raise ValidationFailedError(
                    "A field's type cannot be changed: existing records store "
                    "values in the old type's shape. Deactivate this field and "
                    "add a new one instead."
                )
        if "entity_type" in values and values["entity_type"] is not None:
            submitted_entity = _require_entity_type(values["entity_type"])
            if submitted_entity is not definition.entity_type:
                raise ValidationFailedError("A field cannot be moved to another record type.")

        payload = {
            key: value
            for key, value in values.items()
            if key not in {"api_name", "field_type", "entity_type"}
        }
        merged = {
            "field_type": definition.field_type,
            "picklist_id": definition.picklist_id,
            **payload,
        }
        await self._validate_configuration(definition.organization_id, merged)
        updated = await self.update(definition, actor_id=actor_id, values=payload)
        await self._validate_default(updated)
        return updated

    async def archive_definition(
        self, definition: CustomFieldDefinition, *, actor_id: uuid.UUID | None
    ) -> CustomFieldDefinition:
        """Soft-delete a definition.

        Stored values are *not* removed from the records that hold them. The
        field stops being offered, validated and rendered; the data it
        collected stays in the row, where a later export or an undelete can
        still reach it. Scrubbing it would be the one irreversible act in a
        product whose deletion is otherwise all soft.
        """
        return await self.soft_delete(definition, actor_id=actor_id)

    async def reorder(
        self,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
        order: Sequence[uuid.UUID],
        *,
        actor_id: uuid.UUID | None,
    ) -> Sequence[CustomFieldDefinition]:
        """Set display order from a list of ids, in one round trip.

        Takes the whole order rather than a position per field: positions are
        only meaningful relative to each other, and a per-field endpoint would
        let a client leave the set in a state no drag-and-drop UI can produce
        — two fields at position 3 and nothing at 2.

        Every live definition on the entity must appear exactly once. A partial
        list is refused rather than appended to, because "the ids I sent, then
        everything else in whatever order it was" is not an order anybody
        chose.
        """
        definitions = await self._definitions.for_entity(organization_id, entity_type)
        known = {definition.id: definition for definition in definitions}
        submitted = list(order)
        if len(submitted) != len(set(submitted)) or set(submitted) != set(known):
            raise ValidationFailedError(
                "The order must list every field on this record type exactly once."
            )

        for position, field_id in enumerate(submitted):
            known[field_id].position = position
            known[field_id].updated_by_id = actor_id
        await self._session.flush()

        from app.platform.audit.service import Action as AuditAction

        await self.audit.record(
            organization_id=organization_id,
            action=AuditAction.UPDATED,
            module=self.audit_module,
            entity_type="CUSTOM_FIELD_ORDER",
            actor_id=actor_id,
            details={
                "entity_type": entity_type.value,
                "order": [str(field_id) for field_id in submitted],
            },
        )
        return [known[field_id] for field_id in submitted]

    # --- Configuration validation -----------------------------------------

    async def _validate_configuration(
        self, organization_id: uuid.UUID, values: Mapping[str, Any]
    ) -> None:
        """Refuse a definition that could not be rendered or validated.

        The database's CHECK constraints say the same thing about the
        picklist pairing; this exists so the caller gets a 422 naming what is
        wrong instead of a 500 carrying an integrity error.
        """
        field_type = _require_field_type(values.get("field_type"))
        picklist_id = values.get("picklist_id")

        if field_type in PICKLIST_TYPES:
            if picklist_id is None:
                raise ValidationFailedError(
                    "A picklist field must name the picklist it draws its options from."
                )
            picklist = await self._picklists.get(uuid.UUID(str(picklist_id)), organization_id)
            if picklist is None:
                # 422 rather than 404: the picklist is a field *of* the request,
                # not the resource being addressed.
                raise ValidationFailedError("That picklist does not exist.")
        elif picklist_id is not None:
            raise ValidationFailedError(
                f"A {field_type.value} field does not draw from a picklist."
            )

        if values.get("pattern"):
            compile_pattern(str(values["pattern"]))

        minimum, maximum = values.get("min_value"), values.get("max_value")
        if minimum is not None and maximum is not None and float(minimum) > float(maximum):
            raise ValidationFailedError("The minimum value cannot exceed the maximum.")

        min_length, max_length = values.get("min_length"), values.get("max_length")
        if min_length is not None and max_length is not None and int(min_length) > int(max_length):
            raise ValidationFailedError("The minimum length cannot exceed the maximum.")

    async def _validate_default(self, definition: CustomFieldDefinition) -> None:
        if definition.default_value is None:
            return
        options = await self._active_option_values(definition)
        # Raises `CustomFieldValueError`, a 422, naming the field and the
        # reason — the same message a user would get for typing it into a form.
        coerce(definition, definition.default_value, allowed_options=options)

    async def _active_option_values(self, definition: CustomFieldDefinition) -> tuple[str, ...]:
        if definition.picklist_id is None:
            return ()
        options = await self._picklists.options(
            definition.organization_id, definition.picklist_id, include_inactive=False
        )
        return tuple(option.value for option in options)


# ---------------------------------------------------------------------------
# Record values
# ---------------------------------------------------------------------------


class CustomFieldValueService:
    """Resolves a record's ``custom_fields`` on the way into the database.

    Not a :class:`TenantScopedService`: it owns no table. It is the one piece
    of this module that runs on the hot path of every record write, so it does
    exactly two queries — definitions for the entity type, then options for
    whichever picklists those name — and it does them once per write, not once
    per field.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._definitions = CustomFieldDefinitionRepository(session)
        self._picklists = PicklistRepository(session)

    async def resolve(
        self,
        *,
        organization_id: uuid.UUID,
        entity_type: CrmEntityType,
        submitted: Mapping[str, Any] | None,
        existing: Mapping[str, Any] | None = None,
        creating: bool = False,
    ) -> dict[str, Any]:
        """Return the ``custom_fields`` document to store.

        Args:
            organization_id: the tenant whose definitions apply.
            entity_type: which record type is being written.
            submitted: the caller's ``custom_fields``, or ``None`` when the
                request did not mention them at all. ``None`` and ``{}`` are
                different: the first is "leave the document alone", the second
                is "clear every field", and a PATCH must be able to say the
                first.
            existing: the document to merge into — the record's current one on
                an update, the configured defaults on a create.
            creating: whether this is a new record. Passed explicitly rather
                than inferred from ``existing is None``, because a create whose
                entity has configured defaults arrives here with a non-empty
                ``existing`` and would otherwise be mistaken for an update —
                and the two differ in the one place that matters, which is how
                much of the required-field rule applies.

        Returns:
            The complete document to persist. Keys absent from ``submitted``
            keep their existing values; a key present with an empty value is
            removed.

        Raises:
            CustomFieldValueError: a value does not satisfy its definition.
            ValidationFailedError: an unknown or retired field was supplied, or
                a required field is missing.
        """
        current = dict(existing or {})
        definitions = await self._definitions.for_entity(organization_id, entity_type)
        by_name = {definition.api_name: definition for definition in definitions}

        if submitted is None:
            if not creating:
                # Nothing to validate and nothing to change. Required-field
                # enforcement deliberately does not run: a PATCH that renames
                # an account must not fail because a field was made required
                # after that account was created. Requiredness is enforced
                # where the user can act on it — creation, and any update that
                # touches the field.
                return current
            # A create that mentioned no custom fields still has to satisfy the
            # required ones; the defaults already in `current` may well do it.
            submitted = {}

        unknown = sorted(set(submitted) - set(by_name))
        if unknown:
            raise ValidationFailedError(
                "Unknown custom field(s): " + ", ".join(unknown) + ".",
                details={"fields": unknown},
            )

        retired = sorted(name for name in submitted if not by_name[name].is_active)
        if retired:
            raise ValidationFailedError(
                "These custom fields are no longer active: " + ", ".join(retired) + ".",
                details={"fields": retired},
            )

        options = await self._option_values(organization_id, definitions)

        for api_name, raw in submitted.items():
            definition = by_name[api_name]
            value = coerce(definition, raw, allowed_options=options.get(definition.picklist_id, ()))
            if value is None:
                current.pop(api_name, None)
            else:
                current[api_name] = value

        self._require_present(definitions, current, touched=set(submitted), creating=creating)
        return current

    async def defaults_for(
        self, *, organization_id: uuid.UUID, entity_type: CrmEntityType
    ) -> dict[str, Any]:
        """The document a brand-new record starts from.

        Only active fields with a configured default contribute. Coercion runs
        again here rather than trusting what was stored: a default configured
        before an option was retired would otherwise be written onto every new
        record as a value that field no longer accepts.
        """
        definitions = await self._definitions.for_entity(
            organization_id, entity_type, include_inactive=False
        )
        with_defaults = [d for d in definitions if d.default_value is not None]
        if not with_defaults:
            return {}

        options = await self._option_values(organization_id, with_defaults)
        document: dict[str, Any] = {}
        for definition in with_defaults:
            try:
                value = coerce(
                    definition,
                    definition.default_value,
                    allowed_options=options.get(definition.picklist_id, ()),
                )
            except CustomFieldValueError:
                # A default that has become invalid is skipped rather than
                # allowed to fail the record creation. The administrator's
                # stale configuration is their problem to fix; a rep who cannot
                # create a lead because of it is the product's.
                continue
            if value is not None:
                document[definition.api_name] = value
        return document

    async def _option_values(
        self, organization_id: uuid.UUID, definitions: Iterable[CustomFieldDefinition]
    ) -> dict[uuid.UUID | None, tuple[str, ...]]:
        """Active option values, keyed by picklist id, for these definitions.

        One query for every picklist the entity's fields reference. Only
        *active* options are returned, because this set is what a **new** value
        may be chosen from — a record already holding a retired option keeps
        it, since only the keys the caller actually submitted are re-coerced.
        """
        picklist_ids = {d.picklist_id for d in definitions if d.picklist_id is not None}
        if not picklist_ids:
            return {}
        options = await self._picklists.options_for(
            organization_id, sorted(picklist_ids), include_inactive=False
        )
        grouped: dict[uuid.UUID | None, list[str]] = {
            picklist_id: [] for picklist_id in picklist_ids
        }
        for option in options:
            grouped[option.picklist_id].append(option.value)
        return {key: tuple(values) for key, values in grouped.items()}

    @staticmethod
    def _require_present(
        definitions: Sequence[CustomFieldDefinition],
        document: Mapping[str, Any],
        *,
        touched: set[str],
        creating: bool,
    ) -> None:
        """Enforce required fields, over the right set of fields.

        On create, every active required field must have a value. On update,
        only the ones the caller actually touched — so a field made required
        today does not make yesterday's records uneditable, while clearing a
        required field in the request in front of you is still refused.
        """
        missing = sorted(
            definition.api_name
            for definition in definitions
            if definition.is_active
            and definition.is_required
            and (creating or definition.api_name in touched)
            and is_empty(document.get(definition.api_name))
        )
        if missing:
            raise ValidationFailedError(
                "Required custom field(s) missing: " + ", ".join(missing) + ".",
                details={"fields": missing},
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_api_name(value: Any) -> str:
    api_name = str(value or "").strip().lower()
    if not _API_NAME_RE.match(api_name):
        raise ValidationFailedError(
            "An API name must start with a letter and contain only lowercase "
            "letters, digits and underscores (max 64 characters)."
        )
    return api_name


def _require_entity_type(value: Any) -> CrmEntityType:
    if isinstance(value, CrmEntityType):
        return value
    try:
        return CrmEntityType(str(value))
    except ValueError as exc:
        raise ValidationFailedError(
            "Unknown record type. Expected one of: "
            + ", ".join(member.value for member in CrmEntityType)
            + "."
        ) from exc


def _require_field_type(value: Any) -> CustomFieldType:
    if isinstance(value, CustomFieldType):
        return value
    try:
        return CustomFieldType(str(value))
    except ValueError as exc:
        raise ValidationFailedError("Unknown field type.") from exc


__all__ = [
    "CustomFieldService",
    "CustomFieldValueService",
    "DuplicateApiNameError",
    "DuplicateOptionError",
    "DuplicatePicklistError",
    "FieldLimitReachedError",
    "OptionLimitReachedError",
    "PicklistInUseError",
    "PicklistService",
]
