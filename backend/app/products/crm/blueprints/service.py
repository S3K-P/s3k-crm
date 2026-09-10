"""Business rules for blueprints (Phase G).

Configuration, not enforcement — :mod:`.enforcement` is what a state change
goes through. What lives here is the set of refusals that stop an
unsatisfiable or meaningless process reaching the database in the first place,
because a blueprint that cannot be satisfied is a record nobody can move and an
administrator with no obvious way to find out why.

**Server-side validation is the whole job of this module.** Every rule below is
checked here rather than on the configuration screen:

* a state must be one the field actually has — an enum member, or a live
  pipeline stage in this organization;
* a transition must be one the *built-in* machine allows, so a blueprint cannot
  describe a move that will always be refused underneath it;
* a required field must be a real column or a live custom field, or the rule
  can never be satisfied;
* a required permission must exist in the catalogue;
* at most one blueprint may be active per field, refused with a message naming
  the one already there rather than an integrity error.

**Activation is the moment a process starts constraining people**, so it is the
one place the validation runs in full. A draft may be half-built; an active
blueprint may not be.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import class_mapper

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.platform.authorization.catalog import all_permission_codes
from app.products.crm.blueprints.models import (
    ANY_STATE,
    FIELD_ENTITY,
    MAX_REQUIRED_FIELDS,
    MAX_TRANSITIONS,
    Blueprint,
    BlueprintField,
    BlueprintTransition,
)
from app.products.crm.blueprints.repository import BlueprintRepository
from app.products.crm.custom_fields.repository import CustomFieldDefinitionRepository
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.shared.service import TenantScopedService

MODULE = "blueprints"

#: The model whose columns each governed field belongs to.
_FIELD_MODEL: dict[BlueprintField, type[Any]] = {
    BlueprintField.LEAD_STATUS: Lead,
    BlueprintField.OPPORTUNITY_STAGE: Opportunity,
}


class DuplicateBlueprintError(ConflictError):
    code = "duplicate_blueprint"
    message = "A blueprint with that name already exists."


class BlueprintAlreadyActiveError(ConflictError):
    code = "blueprint_already_active"
    message = "Another blueprint is already active for that field."


class DuplicateTransitionError(ConflictError):
    code = "duplicate_blueprint_transition"
    message = "That move is already described by this blueprint."


class TransitionLimitReachedError(ConflictError):
    code = "blueprint_transition_limit"
    message = f"A blueprint may describe at most {MAX_TRANSITIONS} moves."


class BlueprintService(TenantScopedService[Blueprint]):
    """Blueprints and the transitions that make them up."""

    entity_name = "Blueprint"

    def __init__(self, session: AsyncSession) -> None:
        self._blueprints = BlueprintRepository(session)
        super().__init__(self._blueprints, Blueprint)
        self._session = session
        self._custom_fields = CustomFieldDefinitionRepository(session)

    @property
    def audit_module(self) -> str:
        return MODULE

    # --- Reads -------------------------------------------------------------

    async def list_blueprints(self, organization_id: uuid.UUID) -> Sequence[Blueprint]:
        return await self._blueprints.all_for_organization(organization_id)

    async def transitions(
        self, organization_id: uuid.UUID, blueprint_id: uuid.UUID
    ) -> Sequence[BlueprintTransition]:
        return await self._blueprints.transitions(organization_id, blueprint_id)

    async def transition_counts(self, organization_id: uuid.UUID) -> dict[uuid.UUID, int]:
        return await self._blueprints.transition_counts(organization_id)

    async def get_transition_or_404(
        self, blueprint: Blueprint, transition_id: uuid.UUID
    ) -> BlueprintTransition:
        """Resolve a transition **within a named blueprint**.

        Both halves are checked: the transition must be in the caller's
        organization *and* belong to the blueprint in the URL. Without the
        second, a legitimate id with the wrong parent would edit a different
        blueprint's rule and report success.
        """
        transition = await self._blueprints.get_transition(
            blueprint.organization_id, transition_id
        )
        if transition is None or transition.blueprint_id != blueprint.id:
            raise NotFoundError("Blueprint transition not found.")
        return transition

    async def available_states(
        self, organization_id: uuid.UUID, field: BlueprintField
    ) -> list[dict[str, str]]:
        """The states this field can hold, for the configuration screen.

        Read from the source of truth in both cases — the enum for a lead's
        status, the tenant's live pipeline stages for an opportunity's — rather
        than from anything stored on the blueprint. A configuration screen
        offering a stage that was retired last week is how unsatisfiable
        processes get built.
        """
        if field is BlueprintField.LEAD_STATUS:
            return [
                {"value": status.value, "label": status.value.replace("_", " ").title()}
                for status in LeadStatus
            ]

        result = await self._session.execute(
            select(PipelineStage)
            .where(
                PipelineStage.organization_id == organization_id,
                PipelineStage.deleted_at.is_(None),
            )
            .order_by(PipelineStage.sort_order.asc())
        )
        return [
            {"value": str(stage.id), "label": stage.name} for stage in result.scalars().all()
        ]

    # --- Blueprints --------------------------------------------------------

    async def create_blueprint(
        self, *, organization_id: uuid.UUID, actor_id: uuid.UUID | None, values: Mapping[str, Any]
    ) -> Blueprint:
        """Define a blueprint. Created inactive whatever the body says.

        Activation is a separate act because it is the moment a process starts
        refusing people's work, and doing it in the same request that creates
        an empty blueprint would activate one describing nothing.
        """
        field = _require_field(values.get("field"))
        name = str(values.get("name", "")).strip()
        if not name:
            raise ValidationFailedError("A blueprint needs a name.")
        if await self._blueprints.name_taken(organization_id, name):
            raise DuplicateBlueprintError

        payload = dict(values)
        payload["name"] = name
        payload["field"] = field
        # Derived, never taken from the body: a blueprint claiming to govern a
        # lead's status on an opportunity is not a state the schema should be
        # able to reach.
        payload["entity_type"] = FIELD_ENTITY[field]
        payload["is_active"] = False

        return await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )

    async def update_blueprint(
        self, blueprint: Blueprint, *, actor_id: uuid.UUID | None, values: Mapping[str, Any]
    ) -> Blueprint:
        """Patch a blueprint's name, description, or whether it is active.

        ``field`` is not patchable: its transitions name states of *that* field,
        and moving it would leave every one of them describing a move that
        cannot happen. Activation is validated in full — see
        :meth:`_validate_for_activation`.
        """
        payload = dict(values)
        submitted_field = payload.pop("field", None)
        if submitted_field is not None and _require_field(submitted_field) is not blueprint.field:
            raise ValidationFailedError(
                "A blueprint's field cannot be changed: its moves name states of "
                "that field. Create a new blueprint instead."
            )
        payload.pop("entity_type", None)

        new_name = payload.get("name")
        if new_name is not None:
            new_name = str(new_name).strip()
            payload["name"] = new_name
            if new_name.lower() != blueprint.name.lower() and await self._blueprints.name_taken(
                blueprint.organization_id, new_name, excluding=blueprint.id
            ):
                raise DuplicateBlueprintError

        if payload.get("is_active") and not blueprint.is_active:
            await self._validate_for_activation(blueprint)

        return await self.update(blueprint, actor_id=actor_id, values=payload)

    async def archive_blueprint(
        self, blueprint: Blueprint, *, actor_id: uuid.UUID | None
    ) -> Blueprint:
        """Retire a blueprint. It stops constraining anything immediately.

        Not blocked when it is active: an active blueprint that turns out to
        block work has to be removable *now*, and requiring a deactivate-then-
        delete dance would mean the escape hatch has two steps at exactly the
        moment nobody has time for the second.
        """
        return await self.soft_delete(blueprint, actor_id=actor_id)

    # --- Transitions -------------------------------------------------------

    async def add_transition(
        self, blueprint: Blueprint, *, actor_id: uuid.UUID | None, values: Mapping[str, Any]
    ) -> BlueprintTransition:
        from_state, to_state = await self._validated_states(blueprint, values)

        if await self._blueprints.transition_exists(blueprint.id, from_state, to_state):
            raise DuplicateTransitionError
        if await self._blueprints.count_transitions(blueprint.id) >= MAX_TRANSITIONS:
            raise TransitionLimitReachedError

        required_fields = await self._validated_required_fields(
            blueprint, values.get("required_fields") or []
        )
        permission = _validated_permission(values.get("required_permission"))

        transition = BlueprintTransition(
            organization_id=blueprint.organization_id,
            blueprint_id=blueprint.id,
            name=str(values.get("name") or f"{from_state} → {to_state}").strip(),
            from_state=from_state,
            to_state=to_state,
            required_fields=required_fields,
            required_permission=permission,
            require_note=bool(values.get("require_note", False)),
            position=int(values.get("position") or 0),
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(transition)
        await self._session.flush()
        await self._record_transition_change(
            blueprint, transition, actor_id=actor_id, action="added"
        )
        return transition

    async def update_transition(
        self,
        blueprint: Blueprint,
        transition: BlueprintTransition,
        *,
        actor_id: uuid.UUID | None,
        values: Mapping[str, Any],
    ) -> BlueprintTransition:
        if "from_state" in values or "to_state" in values:
            merged = {
                "from_state": values.get("from_state", transition.from_state),
                "to_state": values.get("to_state", transition.to_state),
            }
            from_state, to_state = await self._validated_states(blueprint, merged)
            if (from_state, to_state) != (transition.from_state, transition.to_state) and (
                await self._blueprints.transition_exists(
                    blueprint.id, from_state, to_state, excluding=transition.id
                )
            ):
                raise DuplicateTransitionError
            transition.from_state = from_state
            transition.to_state = to_state

        if "required_fields" in values and values["required_fields"] is not None:
            transition.required_fields = await self._validated_required_fields(
                blueprint, values["required_fields"]
            )
        if "required_permission" in values:
            transition.required_permission = _validated_permission(values["required_permission"])
        if values.get("name"):
            transition.name = str(values["name"]).strip()
        if values.get("require_note") is not None:
            transition.require_note = bool(values["require_note"])
        if values.get("position") is not None:
            transition.position = int(values["position"])

        transition.updated_by_id = actor_id
        await self._session.flush()
        await self._record_transition_change(
            blueprint, transition, actor_id=actor_id, action="updated"
        )
        return transition

    async def remove_transition(
        self,
        blueprint: Blueprint,
        transition: BlueprintTransition,
        *,
        actor_id: uuid.UUID | None,
    ) -> None:
        """Soft-delete a rule.

        Removing the *last* rule for a destination stops the blueprint having
        an opinion about that state at all, which reopens it — see
        ``enforcement``. That is the intended way to relax a process, and it is
        why removal is never blocked.
        """
        import datetime as dt

        transition.updated_by_id = actor_id
        transition.deleted_at = dt.datetime.now(dt.UTC)
        await self._session.flush()
        await self._record_transition_change(
            blueprint, transition, actor_id=actor_id, action="removed"
        )

    # --- Validation --------------------------------------------------------

    async def _validate_for_activation(self, blueprint: Blueprint) -> None:
        """Refuse to activate a process that cannot be followed.

        Runs at activation rather than on every edit because a draft is allowed
        to be half-built — an administrator adds transitions one at a time, and
        refusing the first because it is not yet a complete process would make
        the screen unusable. What must not happen is an *active* blueprint that
        blocks a record with no way forward.
        """
        if await self._blueprints.active_for_field_exists(
            blueprint.organization_id, blueprint.field, excluding=blueprint.id
        ):
            raise BlueprintAlreadyActiveError(
                "Another blueprint is already active for that field. Deactivate it first."
            )

        transitions = await self._blueprints.transitions(
            blueprint.organization_id, blueprint.id
        )
        if not transitions:
            raise ValidationFailedError(
                "A blueprint with no moves would constrain nothing. Add at least one "
                "before activating it."
            )

        # Re-checked at activation, not only when each was added: a stage may
        # have been retired, or a custom field deactivated, in between. This is
        # the last moment before the configuration starts refusing people.
        states = {entry["value"] for entry in await self.available_states(
            blueprint.organization_id, blueprint.field
        )}
        stale = sorted(
            {
                state
                for rule in transitions
                for state in (rule.from_state, rule.to_state)
                if state != ANY_STATE and state not in states
            }
        )
        if stale:
            raise ValidationFailedError(
                "These moves name states that no longer exist: " + ", ".join(stale) + ".",
                details={"states": stale},
            )

    async def _validated_states(
        self, blueprint: Blueprint, values: Mapping[str, Any]
    ) -> tuple[str, str]:
        """Check a move is expressible *and* possible.

        Two separate questions. The states have to exist — an enum member, or a
        live stage in this organization. And the move has to be one the built-in
        machine would allow, because a blueprint narrows and never widens: a
        rule for a move the product refuses underneath is a rule that can never
        fire, and an administrator who wrote one would reasonably believe they
        had enabled something.
        """
        from_state = str(values.get("from_state") or ANY_STATE).strip()
        to_state = str(values.get("to_state") or "").strip()
        if not to_state:
            raise ValidationFailedError("A move needs a destination state.")

        states = {
            entry["value"]
            for entry in await self.available_states(blueprint.organization_id, blueprint.field)
        }
        for state in (from_state, to_state):
            if state != ANY_STATE and state not in states:
                raise ValidationFailedError(
                    f"'{state}' is not a state this field can hold.",
                    details={"available": sorted(states)},
                )

        if blueprint.field is BlueprintField.LEAD_STATUS:
            _reject_impossible_lead_move(from_state, to_state)

        return from_state, to_state

    async def _validated_required_fields(
        self, blueprint: Blueprint, submitted: Any
    ) -> list[str]:
        """Check every required field is one the record could actually hold.

        Built-in columns come from the mapper; custom fields from the tenant's
        own definitions. A name matching neither is a rule that can never be
        satisfied, which would make the transition permanently impossible —
        exactly the invalid state this module exists to refuse.
        """
        names = [str(name).strip() for name in (submitted or []) if str(name).strip()]
        if not names:
            return []
        if len(names) > MAX_REQUIRED_FIELDS:
            raise ValidationFailedError(
                f"A move may require at most {MAX_REQUIRED_FIELDS} fields."
            )

        model = _FIELD_MODEL[blueprint.field]
        columns = {attribute.key for attribute in class_mapper(model).column_attrs}
        definitions = await self._custom_fields.for_entity(
            blueprint.organization_id, blueprint.entity_type, include_inactive=False
        )
        custom = {definition.api_name for definition in definitions}

        unknown = sorted(set(names) - columns - custom)
        if unknown:
            raise ValidationFailedError(
                "These are not fields on this record type: " + ", ".join(unknown) + ".",
                details={"fields": unknown},
            )
        # De-duplicated, order preserved: a repeated name is a UI artefact and
        # would otherwise be reported twice in the "fill these in" message.
        return list(dict.fromkeys(names))

    async def _record_transition_change(
        self,
        blueprint: Blueprint,
        transition: BlueprintTransition,
        *,
        actor_id: uuid.UUID | None,
        action: str,
    ) -> None:
        """Append an audit entry for a rule change, under the blueprint's identity.

        On the blueprint rather than the transition so "what happened to this
        process" is one readable history, rather than a scatter of entries about
        rows whose ids mean nothing to the reader.
        """
        from app.platform.audit.service import Action as AuditAction

        await self.audit.record(
            organization_id=blueprint.organization_id,
            action=AuditAction.UPDATED,
            module=self.audit_module,
            entity_type="BLUEPRINT",
            entity_id=blueprint.id,
            entity_label=blueprint.name,
            actor_id=actor_id,
            details={"transition": action, **transition.as_dict()},
        )


def _require_field(value: Any) -> BlueprintField:
    if isinstance(value, BlueprintField):
        return value
    try:
        return BlueprintField(str(value))
    except ValueError as exc:
        raise ValidationFailedError(
            "Unknown field. Expected one of: "
            + ", ".join(member.value for member in BlueprintField)
            + ".",
        ) from exc


def _validated_permission(value: Any) -> str | None:
    """Check a required permission is one that exists.

    A code the catalogue does not contain would be a rule nobody can satisfy —
    ``has_permission`` would answer no for everybody, including an
    administrator holding the wildcard.
    """
    if value is None or not str(value).strip():
        return None
    code = str(value).strip()
    if code not in set(all_permission_codes()):
        raise ValidationFailedError(
            f"'{code}' is not a permission. Use the form module.ACTION, e.g. leads.DELETE.",
        )
    return code


def _reject_impossible_lead_move(from_state: str, to_state: str) -> None:
    """Refuse a lead move the built-in machine would never allow.

    Imported here rather than at module scope to keep the import graph one-way
    at load time: ``leads.service`` reaches into this module for enforcement,
    and a top-level import back would be a cycle.

    ``CONVERTED`` is called out separately because it is the case an
    administrator is most likely to try: it is a real status, so it looks
    configurable, but it is reached only through ``convert`` — which creates the
    account and contact. A blueprint rule for it would be a rule that never
    fires, and its author would reasonably think they had enabled something.
    """
    from app.products.crm.leads.service import LEAD_TRANSITIONS

    if to_state == LeadStatus.CONVERTED.value:
        raise ValidationFailedError(
            "A lead reaches CONVERTED only through conversion, which creates the "
            "account and contact. A blueprint cannot describe that move."
        )
    if from_state == ANY_STATE:
        return

    allowed = LEAD_TRANSITIONS.get(LeadStatus(from_state), frozenset())
    if LeadStatus(to_state) not in allowed:
        raise ValidationFailedError(
            f"A lead cannot move from {from_state} to {to_state}, so a blueprint "
            "cannot allow it — a blueprint narrows what is possible, it does not widen it.",
            details={"allowed": sorted(status.value for status in allowed)},
        )


__all__ = [
    "MODULE",
    "BlueprintAlreadyActiveError",
    "BlueprintService",
    "DuplicateBlueprintError",
    "DuplicateTransitionError",
    "TransitionLimitReachedError",
]
