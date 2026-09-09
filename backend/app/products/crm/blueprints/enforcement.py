"""Applying a blueprint to one attempted state change.

Called from the lead and opportunity services, immediately after their own
state machine has approved the move and before anything is written.

**The order is the design.** The built-in check runs first and a blueprint runs
second, so a blueprint can only ever *remove* a move from the set the product
allows. Reversing them — or letting a blueprint's transitions stand in for the
built-in ones — would let an administrator configure their way past rules the
rest of the system depends on: that a lead reaches CONVERTED only through
``convert``, so an account actually exists; that a closed deal stays closed. The
failure would surface far from its cause, as a CONVERTED lead with nothing
behind it.

**Three ways a blueprint declines to constrain**, all deliberate, all so a
configuration cannot strand work that has to happen:

* No active blueprint for the field — the overwhelming common case, and it
  costs one indexed query that returns nothing.
* An active blueprint with **no transition mentioning the destination state**.
  This is the compatibility rule for existing records: an administrator who
  describes half their process has described half their process, not a wall
  around the rest of it. A blueprint that blocked everything it did not mention
  would freeze every record in the tenant the moment it was activated.
* A transition whose ``from_state`` does not match, where **some other rule for
  that destination does**. Then the move genuinely is refused — the process says
  how this state is reached and the record is not coming from there.

Put together: a blueprint constrains a destination only once it has an opinion
about that destination, and then it constrains it completely.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationFailedError
from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.blueprints.models import (
    ANY_STATE,
    BlueprintField,
    BlueprintTransition,
)
from app.products.crm.blueprints.repository import BlueprintRepository


class BlueprintTransitionBlockedError(ValidationFailedError):
    """The organization's process does not allow this move, or not yet.

    A 422 rather than a 403: the caller has permission to change the record and
    the move is refused by the tenant's own configuration, which they can
    usually satisfy by filling something in. The ``details`` say which.
    """

    code = "blueprint_transition_blocked"
    message = "Your organization's process does not allow this change."


class BlueprintGuard:
    """Evaluates one state change against the tenant's active blueprint."""

    def __init__(self, session: AsyncSession) -> None:
        self._blueprints = BlueprintRepository(session)

    async def check(
        self,
        *,
        organization_id: uuid.UUID,
        field: BlueprintField,
        record: Any,
        from_state: str,
        to_state: str,
        principal: Principal | None,
        note: str | None = None,
    ) -> BlueprintTransition | None:
        """Raise if the tenant's process refuses this move; return the rule applied.

        Args:
            organization_id: the tenant whose blueprint applies.
            field: which state column is moving.
            record: the record being moved, read for ``required_fields``.
            from_state: the state it is in, as text.
            to_state: the state it is moving to, as text.
            principal: the mover, for ``required_permission``. ``None`` for an
                internal caller with no request behind it — a background job or
                a data migration — which skips only the permission requirement,
                never the field or note ones. Those are about the *record*
                being complete and hold however the change arrived.
            note: what the mover said, for ``require_note``.

        Returns:
            The transition that authorized the move, or ``None`` when no
            blueprint had an opinion. Returned rather than discarded so the
            caller can record *which rule* let a change through — the question
            an audit reader asks when a process is later disputed.

        Raises:
            BlueprintTransitionBlockedError: the move is not in the process, or
                its requirements are not met.
        """
        blueprint = await self._blueprints.active_for_field(organization_id, field)
        if blueprint is None:
            return None

        transitions = await self._blueprints.transitions(organization_id, blueprint.id)
        governing = [rule for rule in transitions if rule.to_state == to_state]
        if not governing:
            # The blueprint has no opinion about this destination. See the
            # module docstring: a half-described process is not a wall.
            return None

        rule = next(
            (candidate for candidate in governing if candidate.matches(from_state, to_state)),
            None,
        )
        if rule is None:
            raise BlueprintTransitionBlockedError(
                f"'{blueprint.name}' does not allow this record to reach that state "
                "from where it is now.",
                details={
                    "blueprint": blueprint.name,
                    "from": from_state,
                    "to": to_state,
                    "allowed_from": sorted(
                        candidate.from_state
                        for candidate in governing
                        if candidate.from_state != ANY_STATE
                    ),
                },
            )

        missing = _missing_fields(record, rule.required_fields or [])
        if missing:
            raise BlueprintTransitionBlockedError(
                f"'{rule.name}' needs these fields filled in first: "
                + ", ".join(missing)
                + ".",
                details={"blueprint": blueprint.name, "transition": rule.name, "fields": missing},
            )

        if rule.require_note and not (note or "").strip():
            raise BlueprintTransitionBlockedError(
                f"'{rule.name}' needs a note explaining the change.",
                details={"blueprint": blueprint.name, "transition": rule.name, "note": "required"},
            )

        if rule.required_permission and principal is not None:
            module, _, action = rule.required_permission.partition(".")
            if not _holds(principal, module, action):
                raise BlueprintTransitionBlockedError(
                    f"'{rule.name}' may only be performed by someone with "
                    f"{rule.required_permission}.",
                    details={
                        "blueprint": blueprint.name,
                        "transition": rule.name,
                        "required_permission": rule.required_permission,
                    },
                )

        return rule


def _missing_fields(record: Any, required: Sequence[str]) -> list[str]:
    """Which required fields the record does not hold a value for.

    Reads built-in columns and, through ``custom_fields``, tenant-defined ones —
    a process that says "the region must be set before this deal is won" is
    exactly what a custom field is for, and it would be strange for a blueprint
    to see only half the record.

    ``0`` and ``False`` count as values. A truthiness test here would block a
    move because a deal amount is zero or a flag is "no", which are answers.
    """
    custom: Mapping[str, Any] = getattr(record, "custom_fields", None) or {}
    missing: list[str] = []
    for name in required:
        # A custom field wins the name if both exist, which cannot happen: the
        # custom-field module reserves every built-in column name.
        value = custom[name] if name in custom else getattr(record, name, None)
        if _is_blank(value):
            missing.append(name)
    return missing


def _is_blank(value: Any) -> bool:
    """Whether a field holds nothing a person would call a value.

    ``0`` and ``False`` are values, not blanks. A truthiness test here would
    block a move because a deal amount is zero or a flag is "no", which are
    answers — and the person filling the form in would have no way to satisfy
    a rule that refuses their answer.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return isinstance(value, list | dict | tuple | set) and not value


def _holds(principal: Principal, module: str, action: str) -> bool:
    """Whether the principal holds ``module.action``.

    An action the vocabulary does not contain returns ``False`` rather than
    raising: a blueprint configured against a permission that was later removed
    should block the transition — which an administrator will notice and fix —
    rather than 500 on every attempt to move a record.
    """
    try:
        parsed = PermissionAction(action)
    except ValueError:
        return False
    return principal.has_permission(module, parsed)


__all__ = ["BlueprintGuard", "BlueprintTransitionBlockedError"]
