"""SQLAlchemy models for blueprints (Phase G).

A blueprint is a tenant's own process laid over a state field a record already
has — a lead's ``status``, an opportunity's ``stage_id``. It names the moves
that organization allows and what must be true before each one.

**It narrows; it never widens.** This is the single most important property in
the module and everything else follows from it. The built-in state machines
(``LEAD_TRANSITIONS``, the pipeline's won/lost flags) encode rules that the rest
of the product depends on — conversion goes through ``convert`` so an account
is actually created, a closed deal stays closed. If a blueprint could *permit*
a move, an administrator could quietly disable those, and the failure would
appear somewhere else entirely: a lead marked CONVERTED with no account behind
it. So a blueprint's transitions are an additional filter applied after the
built-in check, and a configuration that "allows" an illegal move simply has no
effect.

**Two tables, and no third for "states".** A state is not blueprint data — it
is the enum the record's column already holds, or a pipeline stage row. Copying
them into a blueprint table would create a second list to drift from the first,
and a blueprint referring to a state that no longer exists. Transitions
therefore store state *values* as text, and an unrecognised one constrains
nothing rather than breaking the record (see :mod:`.service`).
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, CrmEntityType

#: Upper bound on transitions in one blueprint.
#:
#: Every one is loaded to evaluate a single state change, and the whole set is
#: rendered on the configuration screen. A lifecycle with more moves than this
#: is not a process anybody can follow.
MAX_TRANSITIONS = 200

#: Upper bound on fields one transition may require.
MAX_REQUIRED_FIELDS = 40


class BlueprintField(enum.StrEnum):
    """Which state column a blueprint governs.

    Closed and short on purpose: each member names a real column with a real
    state machine behind it, and adding one means teaching
    :mod:`.enforcement` how that column's moves are checked. A free-text column
    name would let an administrator configure a process over a field with no
    lifecycle at all.
    """

    #: ``crm.leads.status`` — the ``LeadStatus`` enum.
    LEAD_STATUS = "LEAD_STATUS"
    #: ``crm.opportunities.stage_id`` — a pipeline stage id.
    OPPORTUNITY_STAGE = "OPPORTUNITY_STAGE"


#: Which record type each governed field belongs to.
#:
#: Derived here rather than stored on the row: the pairing is a fact about the
#: schema, not a tenant's choice, and storing it would allow a blueprint
#: claiming to govern a lead's status on an opportunity.
FIELD_ENTITY: dict[BlueprintField, CrmEntityType] = {
    BlueprintField.LEAD_STATUS: CrmEntityType.LEAD,
    BlueprintField.OPPORTUNITY_STAGE: CrmEntityType.OPPORTUNITY,
}

#: ``from_state`` value meaning "from anywhere".
#:
#: A literal rather than NULL, so the partial unique index below can treat it
#: like any other origin — NULL is not equal to NULL in a unique index, which
#: would let an administrator create the same wildcard transition twice.
ANY_STATE = "*"


class Blueprint(Base, CrmEntityMixin):
    """One tenant-configured process over one state field."""

    __tablename__ = "blueprints"
    __table_args__ = (
        Index(
            "uq_blueprints_organization_id_name_live",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # **At most one active blueprint per field.** Two active processes over
        # one column is not a configuration with a meaning: a move would be
        # allowed by one and refused by the other, and which won would depend on
        # row order. The database refuses it outright rather than the service
        # having to pick.
        Index(
            "uq_blueprints_organization_id_field_active",
            "organization_id",
            "field",
            unique=True,
            postgresql_where=text("is_active AND deleted_at IS NULL"),
        ),
        Index("ix_blueprints_organization_id_field", "organization_id", "field"),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    field: Mapped[BlueprintField] = mapped_column(
        Enum(BlueprintField, name="blueprint_field", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    #: Denormalized from :data:`FIELD_ENTITY` so a query can filter by record
    #: type without decoding the field. Kept in step by the service, which is
    #: the only writer, and checked by the same CHECK constraint the migration
    #: builds.
    entity_type: Mapped[CrmEntityType] = mapped_column(
        Enum(CrmEntityType, name="crm_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )

    #: An inactive blueprint constrains nothing. Deactivating is how a process
    #: is suspended without losing its definition, and — because enforcement
    #: reads only the active one — it is also the escape hatch when a
    #: configuration turns out to block work that has to happen.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class BlueprintTransition(Base, CrmEntityMixin):
    """One move a blueprint permits, and what it requires."""

    __tablename__ = "blueprint_transitions"
    __table_args__ = (
        # One rule per origin/destination pair. Two rules for the same move
        # would mean two different sets of requirements with no way to say
        # which applies.
        Index(
            "uq_blueprint_transitions_from_to_live",
            "blueprint_id",
            "from_state",
            "to_state",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_blueprint_transitions_organization_id_blueprint_id",
            "organization_id",
            "blueprint_id",
        ),
        {"schema": CRM_SCHEMA},
    )

    blueprint_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        # CASCADE: a transition has no meaning without its blueprint. The
        # blueprint is soft-deleted through the API, so this only fires for a
        # hard delete no API path performs.
        ForeignKey(f"{CRM_SCHEMA}.blueprints.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: The state a record must be in, or :data:`ANY_STATE`. Stored as text
    #: because the two governed fields hold different things — an enum member
    #: and a stage id — and because a state a blueprint no longer recognises
    #: must leave the record alone rather than trap it.
    from_state: Mapped[str] = mapped_column(String(64), nullable=False)
    to_state: Mapped[str] = mapped_column(String(64), nullable=False)

    #: Columns that must hold a value before this move is allowed, by name.
    #: Validated against the entity's real columns at configuration time, so a
    #: typo is a 422 on the admin screen rather than a rule that silently never
    #: fires — or, worse, one that can never be satisfied.
    required_fields: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    #: A ``module.ACTION`` code the mover must hold, beyond the permission the
    #: endpoint already requires. ``None`` means no extra requirement.
    required_permission: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: Whether the mover must say why. The note is recorded by the module's own
    #: audit entry; the blueprint only insists that one is supplied.
    require_note: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    def matches(self, from_state: str, to_state: str) -> bool:
        """Whether this rule governs a move from ``from_state`` to ``to_state``."""
        return self.to_state == to_state and self.from_state in (from_state, ANY_STATE)

    def as_dict(self) -> dict[str, Any]:
        """The rule, for an audit payload."""
        return {
            "name": self.name,
            "from": self.from_state,
            "to": self.to_state,
            "required_fields": list(self.required_fields or []),
            "required_permission": self.required_permission,
            "require_note": self.require_note,
        }


__all__ = [
    "ANY_STATE",
    "FIELD_ENTITY",
    "MAX_REQUIRED_FIELDS",
    "MAX_TRANSITIONS",
    "Blueprint",
    "BlueprintField",
    "BlueprintTransition",
]
