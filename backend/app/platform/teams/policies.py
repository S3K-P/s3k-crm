"""Authorization for the teams module (ADR-010).

Two distinct things are gated here and conflating them would be a mistake.

**Administering teams** — creating one, renaming it, moving somebody onto it —
is gated on the ``teams`` permission module, seeded by the B02 migration.
Editing team membership changes *who can read whose records*, so it is
deliberately an administrative act rather than something a rep can do to widen
their own reach.

**Being on a team** is not a permission at all. It is data, read by
:meth:`~app.platform.teams.service.TeamService.peer_user_ids` when the CRM
resolves record-level visibility. A user with no ``teams`` permission still has
their team membership honoured — otherwise the visibility rule would apply only
to the administrators who least need it.

The pairing with ``VIEW_TEAM`` matters. ``teams.VIEW`` answers *may this caller
see the org chart*; ``<module>.VIEW_TEAM`` answers *may they read their
team-mates' leads*. They are granted independently: a rep gets the second
without the first.
"""

from __future__ import annotations

from typing import Final

from app.platform.authorization.models import PermissionAction

#: The permission module team administration is gated on. Seeded by the B02
#: migration; it is not present in earlier revisions.
MODULE: Final = "teams"

VIEW: Final = PermissionAction.VIEW
CREATE: Final = PermissionAction.CREATE
EDIT: Final = PermissionAction.EDIT
DELETE: Final = PermissionAction.DELETE


__all__ = ["CREATE", "DELETE", "EDIT", "MODULE", "VIEW"]
