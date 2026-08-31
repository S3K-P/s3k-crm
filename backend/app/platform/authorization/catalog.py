"""The permission vocabulary and the system role templates that use it.

This module is **data, not logic**: it is the single place that decides which
``module.action`` pairs exist and which of them each built-in role grants. The
seeding migration and the runtime both read it, so the database can never drift
from the code's idea of what a permission is.

Adding a CRM module later means appending to :data:`PERMISSION_MODULES` and
writing a migration that re-runs the seed — no schema change is required.
"""

from __future__ import annotations

from typing import Final

from app.platform.authorization.models import PermissionAction

#: Every module that participates in RBAC. Names match the CRM module folder
#: names and the frontend's permission matrix.
PERMISSION_MODULES: Final[tuple[str, ...]] = (
    # Platform
    "users",
    "organizations",
    "roles",
    "audit",
    #: Team and department administration (B02). A Platform module, not a CRM
    #: one — it is gated separately from the CRM data teams affect.
    "teams",
    #: The AI gateway (ADR-016). Only ``ai.ADMIN`` is meaningful, and no system
    #: role template below grants it, so configuring prompts stays with the
    #: wildcard Admin role.
    "ai",
    # CRM
    "accounts",
    "contacts",
    "leads",
    "lead_sources",
    "opportunities",
    "campaigns",
    "activities",
    "tasks",
    "notes",
    "documents",
    "dashboard",
    #: AI company research (Market Insights). A CRM module: it reads CRM data
    #: and its sessions are owned by the rep who ran them.
    "market_insights",
)

#: Actions available on every module (doc 04 ``PermissionAction``).
PERMISSION_ACTIONS: Final[tuple[PermissionAction, ...]] = tuple(PermissionAction)


def permission_code(module: str, action: PermissionAction | str) -> str:
    """Canonical wire form of a permission, e.g. ``leads.CREATE``."""
    value = action.value if isinstance(action, PermissionAction) else str(action)
    return f"{module}.{value}"


def all_permission_codes() -> tuple[str, ...]:
    """The full catalogue, as stable ``module.ACTION`` strings."""
    return tuple(
        permission_code(module, action)
        for module in PERMISSION_MODULES
        for action in PERMISSION_ACTIONS
    )


# ---------------------------------------------------------------------------
# System role templates
# ---------------------------------------------------------------------------

#: Roles every organization receives. ``ADMIN`` is deliberately expressed as a
#: wildcard rather than an enumerated list so a newly added module cannot
#: silently leave administrators without access to it.
ADMIN_ROLE: Final = "Admin"
MANAGER_ROLE: Final = "Manager"
USER_ROLE: Final = "User"

_CRM_MODULES: Final[tuple[str, ...]] = (
    "accounts",
    "contacts",
    "leads",
    "lead_sources",
    "opportunities",
    "campaigns",
    "activities",
    "tasks",
    "notes",
    "documents",
    "dashboard",
    "market_insights",
)

_MANAGER_ACTIONS: Final = (
    PermissionAction.VIEW,
    #: A manager runs the team's pipeline, so they read across owners.
    PermissionAction.VIEW_ALL,
    PermissionAction.CREATE,
    PermissionAction.EDIT,
    PermissionAction.DELETE,
    PermissionAction.EXPORT,
)

#: Day-to-day sales work. ``VIEW_ALL`` is deliberately absent: a rep reads the
#: records they own, which is what makes ``VIEW`` record-level rather than
#: organization-wide.
_USER_ACTIONS: Final = (
    PermissionAction.VIEW,
    PermissionAction.CREATE,
    PermissionAction.EDIT,
)


def _manager_permissions() -> tuple[str, ...]:
    """Full CRM control plus read-only visibility of platform administration."""
    codes = [
        permission_code(module, action)
        for module in _CRM_MODULES
        for action in _MANAGER_ACTIONS
    ]
    codes.append(permission_code("users", PermissionAction.VIEW))
    codes.append(permission_code("organizations", PermissionAction.VIEW))
    #: A manager reads the org chart but does not restructure it: team
    #: membership decides who can see whose records, so editing it is an
    #: administrative act.
    codes.append(permission_code("teams", PermissionAction.VIEW))
    return tuple(codes)


def _user_permissions() -> tuple[str, ...]:
    """Day-to-day sales work: read, create and edit **own** records, never delete."""
    return tuple(
        permission_code(module, action) for module in _CRM_MODULES for action in _USER_ACTIONS
    )


#: Modules whose rows carry an ``owner_id`` that record-level visibility is
#: resolved against. Everything else is organization-wide reference data or
#: has its own rule (notes enforce author/visibility in their own service).
#:
#: ``activities`` is deliberately absent: an activity is a child of the record
#: it is logged against, and scoping it by its own owner would hide a
#: colleague's call from that record's timeline — which is the opposite of
#: what a shared account history is for.
#:
#: ``market_insights`` is here for a slightly different reason from the rest: a
#: research session is not a shared customer record but one person's working
#: notes, and §13 requires that a colleague cannot read them. Owner-scoping is
#: the mechanism the system already has for that, so a manager holding
#: ``VIEW_ALL`` still sees the team's research and nobody needs a second
#: permission model.
OWNER_SCOPED_MODULES: Final[frozenset[str]] = frozenset(
    {"accounts", "contacts", "leads", "opportunities", "tasks", "market_insights"}
)


#: name -> description, and the permission codes it grants. ``None`` means
#: "every permission in the catalogue" and is resolved at seed time.
SYSTEM_ROLES: Final[dict[str, tuple[str, tuple[str, ...] | None]]] = {
    ADMIN_ROLE: (
        "Full access to the organization, its members and all CRM data.",
        None,
    ),
    MANAGER_ROLE: (
        "Manages CRM data and the sales pipeline; may delete and export records.",
        _manager_permissions(),
    ),
    USER_ROLE: (
        "Works day to day in the CRM: may read, create and edit records.",
        _user_permissions(),
    ),
}


def permissions_for_system_role(name: str) -> tuple[str, ...]:
    """Resolve a system role template to concrete permission codes.

    Raises:
        KeyError: if ``name`` is not a system role.
    """
    _description, codes = SYSTEM_ROLES[name]
    return all_permission_codes() if codes is None else codes


__all__ = [
    "ADMIN_ROLE",
    "MANAGER_ROLE",
    "OWNER_SCOPED_MODULES",
    "PERMISSION_ACTIONS",
    "PERMISSION_MODULES",
    "SYSTEM_ROLES",
    "USER_ROLE",
    "all_permission_codes",
    "permission_code",
    "permissions_for_system_role",
]
