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
)

_MANAGER_ACTIONS: Final = (
    PermissionAction.VIEW,
    PermissionAction.CREATE,
    PermissionAction.EDIT,
    PermissionAction.DELETE,
    PermissionAction.EXPORT,
)

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
    return tuple(codes)


def _user_permissions() -> tuple[str, ...]:
    """Day-to-day sales work: read, create and edit CRM records, never delete."""
    return tuple(
        permission_code(module, action) for module in _CRM_MODULES for action in _USER_ACTIONS
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
    "PERMISSION_ACTIONS",
    "PERMISSION_MODULES",
    "SYSTEM_ROLES",
    "USER_ROLE",
    "all_permission_codes",
    "permission_code",
    "permissions_for_system_role",
]
