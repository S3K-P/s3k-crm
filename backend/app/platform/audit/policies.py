"""Authorization policy for the audit module (ADR-010).

The trail is the most sensitive read in the system: it names who signed in from
where, whose account was locked, and which records an administrator touched.
Three rules govern it, and they are stated here so the router cannot quietly
drift from them.

**Reading requires ``audit.VIEW``.** Of the seeded system roles only *Admin*
holds it — ``Admin`` is a wildcard over the whole catalogue, while *Manager*
receives the CRM modules plus ``users.VIEW`` and ``organizations.VIEW``, and
*User* receives CRM only (``authorization/catalog.py``). So an audit reader is
an administrator, or a tenant-defined role somebody deliberately granted
``audit.VIEW`` to — which is exactly the "auditor" case, without inventing a
second authorization mechanism to express it.

**Reading is scoped to the caller's own organization, always.** There is no
parameter, header or role that widens it. The service filters on
``organization_id`` and RLS filters again underneath
(``app.platform.audit.repository``).

**Nothing writes through the API.** There is no create, update or delete route,
and there never should be: records are appended by the services that perform
the audited actions, and ``platform.audit_logs`` carries a trigger that rejects
UPDATE and DELETE outright. A caller cannot edit the trail because there is no
endpoint to try, *and* because the database would refuse.
"""

from __future__ import annotations

from typing import Final

from app.platform.authorization.models import PermissionAction

#: The permission module this trail is gated on. Present in
#: ``PERMISSION_MODULES`` and seeded by revision ``8224845a67ac``, so the
#: permission rows already exist — no migration is needed to start enforcing it.
MODULE: Final = "audit"

#: Reading the trail.
VIEW: Final = PermissionAction.VIEW

#: Reserved for CSV/PDF extraction (`P3-W22-BE-03`). No route uses it yet;
#: naming it here keeps the eventual export gated on its own permission rather
#: than riding in on VIEW.
EXPORT: Final = PermissionAction.EXPORT


def may_read_trail(permissions: frozenset[str]) -> bool:
    """Whether a resolved permission set allows reading the audit trail.

    A read of an already-made decision, mirroring ``Principal.has_permission``:
    the set was loaded while authorizing the route. Provided so a handler can
    ask the question a second time (to decide what to render) without a second
    database round trip — never as a substitute for the route's own dependency.
    """
    return f"{MODULE}.{VIEW.value}" in permissions


__all__ = ["EXPORT", "MODULE", "VIEW", "may_read_trail"]
