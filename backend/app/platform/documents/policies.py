"""Authorization for the documents module (ADR-010, doc 13).

Attaching a file to a CRM record is two permissions, not one, and conflating
them is the mistake this module exists to prevent.

**The module permission** — ``documents.VIEW`` / ``CREATE`` / ``DELETE`` —
answers *may this caller work with attachments at all*. It is checked by the
route, exactly as every other module's routes check theirs.

**Access to the linked record** answers *may this caller see the account this
file is attached to*. That question is a **product** question: the record lives
in a CRM table, its visibility depends on ``owner_id`` and on the caller's
``VIEW_ALL`` grant for that module (``crm.shared.visibility``), and none of
that is knowable from the Platform layer. ARCHITECTURE-BOUNDARIES.md rule 1
forbids reaching for it directly, so it is inverted: this module declares
:class:`EntityAccessVerifier`, the CRM layer implements it, and the composition
root wires the two together.

Both must pass. ``documents.VIEW`` alone would let any user download every file
in the organization, including those attached to a colleague's leads that
record-level visibility hides from them — which would make attachments a way
around the very control the CRM spent a workstream building.

The pairing is deliberate on the write side too: uploading to a record needs
``documents.CREATE`` **and** *write* access to that record, so a caller who can
only read an account cannot bolt a file onto it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from app.platform.auth.dependencies import Principal
from app.platform.authorization.models import PermissionAction

#: The permission module attachments are gated on. Already present in
#: ``PERMISSION_MODULES`` and seeded by revision ``8224845a67ac``, so no
#: migration is needed to start enforcing it.
MODULE: Final = "documents"

VIEW: Final = PermissionAction.VIEW
CREATE: Final = PermissionAction.CREATE
DELETE: Final = PermissionAction.DELETE


@dataclass(frozen=True, slots=True)
class EntityAccess:
    """What a principal may do with one linked record.

    There is deliberately no ``exists`` flag. "No such record", "another
    tenant's record" and "a record record-level visibility hides from you" are
    one outcome here, and the implementation reaches it by applying the
    visibility predicate in SQL so the three are literally the same empty
    result. Separating them would invite a caller to tell them apart by
    watching which ids answer differently, which is how an attachment endpoint
    becomes a way to enumerate a colleague's pipeline.
    """

    can_view: bool
    can_edit: bool
    #: Human-readable name of the record, for the audit trail. ``None`` when
    #: the caller cannot reach it.
    label: str | None = None

    @classmethod
    def denied(cls) -> EntityAccess:
        return cls(can_view=False, can_edit=False)


@runtime_checkable
class EntityAccessVerifier(Protocol):
    """Resolves whether a principal may reach the record a file hangs off.

    Implemented by the product that owns the record — today only CRM. The
    Protocol lives here so the documents module never imports a product, and
    so a second product can register its own resolver without this module
    changing.
    """

    async def resolve(
        self, *, principal: Principal, entity_type: str, entity_id: uuid.UUID
    ) -> EntityAccess:
        """Return what ``principal`` may do with ``entity_type``/``entity_id``.

        Must never raise for an unknown entity type or a missing record:
        both are ordinary conditions and both resolve to
        :meth:`EntityAccess.denied`.
        """
        ...


class DenyAllEntityAccess:
    """Fallback verifier: refuses everything.

    Used when no product registered one — a unit test building an application
    without the CRM router, for instance. Granting access on the assumption
    that "no verifier means no restriction" would turn a wiring mistake into an
    open door, so the default is to deny.
    """

    async def resolve(
        self, *, principal: Principal, entity_type: str, entity_id: uuid.UUID
    ) -> EntityAccess:
        return EntityAccess.denied()


__all__ = [
    "CREATE",
    "DELETE",
    "MODULE",
    "VIEW",
    "DenyAllEntityAccess",
    "EntityAccess",
    "EntityAccessVerifier",
]
