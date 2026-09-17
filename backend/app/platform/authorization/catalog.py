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
    #: The saved-report library: folders and saved report definitions.
    #:
    #: *Running* a report is not gated here and never was — that is authorized
    #: against the module the report reads, because reading a report is reading
    #: the records it aggregates (see ``products/crm/reports/policies.py``).
    #: What this module governs is the saved object: may you name a report,
    #: file it in a folder, share it with colleagues, delete somebody's. Those
    #: are a lifecycle of their own, and holding ``reports.CREATE`` grants no
    #: sight of a single record — a caller who saves a lead report and lacks
    #: ``leads.VIEW`` still gets 403 when they run it.
    "reports",
    #: AI company research (Market Insights). A CRM module: it reads CRM data
    #: and its sessions are owned by the rep who ran them.
    "market_insights",
    #: User-authored mail and the templates it is composed from.
    #:
    #: One module for both, rather than ``emails`` and ``email_templates``.
    #: The two are the same act to a user — you pick a template inside the
    #: composer — and a role that could send mail but not read the templates
    #: it offers would be a role nobody would deliberately create.
    "emails",
    #: Tenant-defined fields and the picklists they draw options from.
    #:
    #: One module for both, for the reason ``emails`` is one module for
    #: messages and templates: a picklist exists to be a field's option set,
    #: and a role that could define a field but not the list it offers would be
    #: a role nobody would deliberately create.
    #:
    #: ``VIEW`` here is unusual in being granted to *every* system role, User
    #: included, and it is worth saying why that is not a widening. Reading the
    #: definitions is what makes a record form drawable at all — a rep who
    #: cannot see that "Leads have a Region field" gets a form missing half its
    #: inputs. It grants sight of the tenant's own configuration and of nothing
    #: else: a record's custom *values* live in the record and stay behind that
    #: record's module permission and record-level visibility.
    "custom_fields",
    #: Saved list views: a named set of filters, columns and ordering.
    #:
    #: What this module governs is the saved *question*, not its answer.
    #: Holding ``views.VIEW`` grants sight of no record whatsoever — running a
    #: view goes through the record type's own list endpoint, behind that
    #: module's permission and record-level visibility, so two colleagues
    #: opening one shared view legitimately see different rows.
    #:
    #: ``VIEW_ALL`` has a second meaning here beyond the usual one: it is what
    #: lets a manager edit or delete a view somebody else owns. Reusing the
    #: existing grant rather than inventing a ``views.MANAGE`` that nobody
    #: would think to grant.
    #:
    #: There is deliberately no ``calendar`` or ``merge`` module. The calendar
    #: shows meetings and tasks and is authorized against ``activities.VIEW``
    #: and ``tasks.VIEW``; merging is an edit plus a deletion and is authorized
    #: against the record's own ``EDIT`` *and* ``DELETE``. A permission of
    #: their own would in both cases be a grant that could be held *without*
    #: the ones it is built from — which is to say, a way around them.
    "views",
    #: Tenant-configured processes over a record's state field (Phase G).
    #:
    #: Configuring one is administration in the strongest sense the product
    #: has: a blueprint decides what everybody *else* in the organization may
    #: do with a record, which is a wider power than editing any single one. So
    #: only Admin holds anything but ``VIEW``.
    #:
    #: ``VIEW`` goes to every role for the same reason ``custom_fields.VIEW``
    #: does: a rep whose move was refused has to be able to see the rule that
    #: stopped them and what would unblock it. Hiding it turns a clear 422 into
    #: a mystery, and it grants sight of no record.
    #:
    #: A transition's ``required_permission`` is checked *in addition to* the
    #: endpoint's own, so a blueprint can only ever narrow who may make a move
    #: — never grant somebody one they could not otherwise make.
    "blueprints",
    #: Trigger -> conditions -> actions automation over CRM records and tasks
    #: (Checkpoint 6). Same reasoning as ``blueprints``, restated for the same
    #: kind of module: a workflow decides what happens to *every* matching
    #: record in the organization — updating fields, creating tasks, sending
    #: mail — which is administration in the strongest sense the product has.
    #: ``VIEW`` goes to every role for the same reason ``blueprints.VIEW``
    #: does: whoever's record a workflow touched has to be able to see which
    #: rule did it and what it did, in the execution history. It grants sight
    #: of no record beyond what the run history itself already names.
    "workflows",
    #: The admin form/layout builder (Checkpoint 4): sections, field placement
    #: and conditional rules for one entity type's create/edit form.
    #:
    #: Same shape as ``blueprints`` and for the same reason: publishing a
    #: layout changes what every rep's form looks like and, through a rule's
    #: ``effect_required``, what is demanded of them — a wider power than
    #: editing any single record. ``VIEW`` goes to every role because a rep's
    #: own form has to fetch the published layout to render against, and a
    #: rule that hid a field has to be visible to whoever is filling in the
    #: rest of the form.
    "record_layouts",
    #: AI intelligence built on real CRM data (Checkpoint 7): account/deal/lead
    #: summaries, account intelligence, next-best-action, AI email drafting,
    #: meeting-to-CRM extraction, natural-language queries and prioritization
    #: explanations. Gates *requesting* an AI feature — not the underlying
    #: data it reads or the records a confirmed action writes, both of which
    #: stay behind their own module's permission and record-level visibility
    #: exactly as they do for a human doing the same thing by hand (the
    #: context builder checks ``accounts.VIEW``/``opportunities.VIEW``/etc.
    #: per section, and a meeting-extraction action a user confirms is
    #: created through that entity's own service, e.g. ``TaskService``, which
    #: enforces its own permission independently). Same reasoning as
    #: ``market_insights`` for why this is its own module rather than reusing
    #: ``ai`` (ADR-016's ``ai.ADMIN`` governs the gateway itself, not a
    #: product feature built on it) — a distinct module keeps "may this
    #: caller ask the AI for X" separate from "may this caller configure the
    #: AI provider".
    "ai_insights",
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
    "reports",
    "market_insights",
    #: Day-to-day AI features (Checkpoint 7). Same tier as ``market_insights``:
    #: a rep may ask for a summary or a next-best-action on a record they can
    #: already see; deleting one's AI history follows the manager/user split
    #: every other CRM module uses.
    "ai_insights",
    "emails",
    #: Every role may keep its own views. Sharing one is a decision made per
    #: view through its ``visibility``, not a permission an administrator
    #: hands out — a rep who cannot save a list view of their own pipeline is
    #: a rep the feature does not exist for.
    "views",
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
        permission_code(module, action) for module in _CRM_MODULES for action in _MANAGER_ACTIONS
    ]
    codes.append(permission_code("users", PermissionAction.VIEW))
    codes.append(permission_code("organizations", PermissionAction.VIEW))
    #: A manager reads the org chart but does not restructure it: team
    #: membership decides who can see whose records, so editing it is an
    #: administrative act.
    codes.append(permission_code("teams", PermissionAction.VIEW))
    codes.append(permission_code("custom_fields", PermissionAction.VIEW))
    codes.append(permission_code("blueprints", PermissionAction.VIEW))
    codes.append(permission_code("record_layouts", PermissionAction.VIEW))
    codes.append(permission_code("workflows", PermissionAction.VIEW))
    return tuple(codes)


def _user_permissions() -> tuple[str, ...]:
    """Day-to-day sales work: read, create and edit **own** records, never delete."""
    codes = [permission_code(module, action) for module in _CRM_MODULES for action in _USER_ACTIONS]
    #: Read-only, and read-only for both non-admin roles: defining a field is
    #: administration, but *seeing* which fields exist is what makes a lead
    #: form renderable. Without it every rep's form would be missing whatever
    #: their own administrator added.
    codes.append(permission_code("custom_fields", PermissionAction.VIEW))
    codes.append(permission_code("blueprints", PermissionAction.VIEW))
    codes.append(permission_code("record_layouts", PermissionAction.VIEW))
    codes.append(permission_code("workflows", PermissionAction.VIEW))
    #: A rep deletes their own saved views. ``views.DELETE`` reads alarming
    #: beside the CRM modules, where it retires customer records — here it
    #: removes a saved question and touches no record at all, and the service
    #: still refuses to let anyone delete a colleague's without ``VIEW_ALL``.
    codes.append(permission_code("views", PermissionAction.DELETE))
    return tuple(codes)


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
#:
#: ``emails`` is deliberately absent, for the reason ``activities`` is. A
#: message sent to a customer is part of that customer's history, and scoping
#: it by its sender would hide a colleague's correspondence from the account
#: timeline — which is the opposite of what a shared account history is for,
#: and the specific failure that makes a rep re-introduce themselves to a
#: customer their colleague emailed last week. The two genuinely private
#: things here are narrower than a module and are enforced where they belong:
#: an unsent draft is its author's, and a blind-copy list is its sender's
#: (``emails/policies.py``).
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
