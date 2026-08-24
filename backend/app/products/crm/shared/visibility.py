"""Record-level visibility for CRM entities (ADR-010).

Tenant isolation answers *which organization's rows may I touch*. This module
answers the next question down: *within my organization, which rows are mine
to see?* Both are needed. RLS alone would let every rep in an organization
read every other rep's pipeline.

The rule is deliberately tiny and lives in one place, and reads as three
widening rungs:

* a caller holding ``<module>.VIEW_ALL`` reads across owners;
* a caller holding ``<module>.VIEW_TEAM`` reads records owned by anyone on a
  team they share (B02, closing CR07);
* everybody else reads the records they own, plus records with no owner.

``VIEW_ALL`` wins outright when both are held — it is the wider grant, and
resolving it first means the team query's result cannot narrow anything.
A ``VIEW_TEAM`` holder who is on no team falls back to owner-only, which is the
safe direction: an empty peer set must never read as "no restriction".

Unowned rows stay visible on purpose. ``owner_id`` is nullable and predates
this rule, so narrowing to a strict ``owner_id = me`` would make historical
and imported records invisible to everyone but an administrator — data loss
in everything but name. New records get an owner at creation
(:meth:`TenantScopedService.create`), so the unowned case shrinks to rows that
existed before this shipped.

The predicate is applied inside :class:`TenantScopedRepository`, at the single
point every read of a CRM table goes through, so a new endpoint cannot forget
it — the same reasoning that puts ``organization_id`` there.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, or_

from app.platform.auth.dependencies import Principal
from app.platform.authorization.catalog import OWNER_SCOPED_MODULES
from app.platform.authorization.service import Action as PermissionAction


@dataclass(frozen=True, slots=True)
class RecordVisibility:
    """How much of a module's data one principal may read.

    ``viewer_id`` is ``None`` when the caller may read everything, which is
    also what reference-data modules (lead sources, pipelines) always get.
    """

    viewer_id: uuid.UUID | None
    #: Team-mates whose records are also readable. Only ever non-empty when
    #: ``viewer_id`` is set — an unrestricted visibility has nothing to widen.
    peer_ids: frozenset[uuid.UUID] = frozenset()

    @property
    def is_unrestricted(self) -> bool:
        return self.viewer_id is None

    @classmethod
    def unrestricted(cls) -> RecordVisibility:
        return cls(viewer_id=None)

    @classmethod
    def for_module(cls, principal: Principal, module: str) -> RecordVisibility:
        """Resolve what ``principal`` may see in ``module``.

        A module outside :data:`OWNER_SCOPED_MODULES` is organization-wide by
        definition — reference data, or an entity with its own rule such as
        notes — so it resolves to unrestricted without consulting permissions.

        ``VIEW_ALL`` is checked before ``VIEW_TEAM`` because it is the wider
        grant; a caller holding both is unrestricted, not team-scoped.
        """
        if module not in OWNER_SCOPED_MODULES:
            return cls.unrestricted()
        if principal.has_permission(module, PermissionAction.VIEW_ALL):
            return cls.unrestricted()
        if principal.has_permission(module, PermissionAction.VIEW_TEAM):
            # ``team_peer_ids`` was resolved once by ``require_permission``.
            # Empty means "on no team", which correctly leaves the predicate
            # equal to the owner-only one rather than widening it.
            return cls(viewer_id=principal.user_id, peer_ids=principal.team_peer_ids)
        return cls(viewer_id=principal.user_id)

    def filter_for(self, model: type[Any]) -> ColumnElement[bool] | None:
        """The SQL predicate, or ``None`` when nothing should be narrowed.

        Returns ``None`` rather than a tautology so the caller can skip
        touching the query at all — an unrestricted read produces exactly the
        statement it produced before record-level visibility existed.
        """
        if self.viewer_id is None:
            return None
        owner = getattr(model, "owner_id", None)
        if owner is None:
            # A module listed as owner-scoped but whose model has no owner
            # column is a configuration mistake, not a reason to leak rows.
            raise TypeError(
                f"{model.__name__} has no owner_id column but is owner-scoped; "
                "remove it from OWNER_SCOPED_MODULES or add the column."
            )
        if self.peer_ids:
            # ``IN`` over the caller plus their team-mates. Built from the
            # viewer's own id union the peers rather than from the peer set
            # alone, so a stale or empty peer set can only ever narrow this to
            # owner-only — it can never drop the owner's own records, and it
            # can never widen past the team.
            return or_(
                owner.in_({self.viewer_id, *self.peer_ids}), owner.is_(None)
            )
        return or_(owner == self.viewer_id, owner.is_(None))


@dataclass(frozen=True, slots=True)
class DashboardScope:
    """The visibilities a cross-module read model needs, resolved together.

    The dashboard aggregates over three owner-scoped modules at once, and a
    custom role may hold ``VIEW_ALL`` on one and not another. Resolving each
    separately — rather than picking one and applying it to all three — is
    what keeps each KPI equal to the count of rows behind the list it links
    to.
    """

    leads: RecordVisibility
    opportunities: RecordVisibility
    tasks: RecordVisibility

    @classmethod
    def unrestricted(cls) -> DashboardScope:
        unrestricted = RecordVisibility.unrestricted()
        return cls(leads=unrestricted, opportunities=unrestricted, tasks=unrestricted)

    @classmethod
    def for_principal(cls, principal: Principal) -> DashboardScope:
        return cls(
            leads=RecordVisibility.for_module(principal, "leads"),
            opportunities=RecordVisibility.for_module(principal, "opportunities"),
            tasks=RecordVisibility.for_module(principal, "tasks"),
        )


__all__ = ["DashboardScope", "RecordVisibility"]
