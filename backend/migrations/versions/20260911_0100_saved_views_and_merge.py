"""Saved list views, merge pointers, and the indexes Phase F reads through.

Revision ID: 20260911_0100
Revises: 20260910_0100
Create Date: 2026-09-11 01:00:00.000000

Three things, and the third is the one worth reading carefully.

**1. ``crm.saved_views``.** One tenant-scoped table for a named set of filters,
columns and ordering. A view stores a *question*, never an answer — no row, id
or count — which is what makes one opened a year later show that day's records
rather than a snapshot nobody can tell is stale.

**2. ``merged_into_id`` on accounts, contacts and leads.** A merged record is
soft-deleted like any other, but "deleted" and "became part of that one" are
different facts and only the second can answer the question a stale link asks.
Self-referential and ``ON DELETE SET NULL``: if the survivor is itself somehow
removed the pointer clears, rather than the constraint blocking that removal or
cascading into a record with nothing to do with it. Nullable with no default,
so adding it to populated tables is a catalogue change and not a rewrite.

**3. An index on ``crm.meetings.start_time``.** The calendar asks "which
meetings overlap this window" on every grid render, and the table had no index
on the scheduling column at all — only the primary key and the unique
``activity_id``. That query would have degraded to a scan of the tenant's whole
meeting history, growing with the account rather than with the month on screen.

No index on ``crm.tasks`` here: the other half of the calendar reads
``(organization_id, due_date)``, and revision ``8224845a67ac`` already built
exactly that. It was checked rather than assumed — adding a second index on the
same columns costs write throughput on every task in the product and buys
nothing.

The meetings index is on ``start_time`` alone because that table carries no
tenant column: it is a strict 1:1 extension of an activity, and the join to
``crm.activities`` is what applies the tenant filter.

**No permission-module rows for ``calendar`` or ``merge``**, deliberately, and
this is a decision rather than an omission. The calendar shows meetings and
tasks, and is authorized against ``activities.VIEW`` and ``tasks.VIEW``;
merging is an edit plus a deletion, authorized against the record's own
``EDIT`` *and* ``DELETE``. A module of their own would be a grant that could be
held *without* the ones it is built from — which is to say, a way around them.
``views`` does get one, because a saved view is a real object with its own
lifecycle, and holding ``views.VIEW`` grants sight of no record whatsoever.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260911_0100"
down_revision: str | Sequence[str] | None = "20260910_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: Record types gaining ``merged_into_id``. The three that duplicate in
#: practice — the ones created by imports, web forms, and two reps talking to
#: the same company.
_MERGEABLE: tuple[str, ...] = ("accounts", "contacts", "leads")

#: Pinned snapshot of the action vocabulary as of this revision. Not imported
#: from ``app.platform.authorization.catalog``: a migration is a snapshot of
#: history, and reading live code means a later edit silently rewrites what an
#: old revision does — the failure that broke revision ``8224845a67ac`` on a
#: from-zero run.
_ACTIONS: tuple[str, ...] = (
    "VIEW",
    "VIEW_TEAM",
    "VIEW_ALL",
    "CREATE",
    "EDIT",
    "DELETE",
    "EXPORT",
    "ADMIN",
)

_MANAGER_ACTIONS: tuple[str, ...] = (
    "VIEW",
    "VIEW_ALL",
    "CREATE",
    "EDIT",
    "DELETE",
    "EXPORT",
)

#: Including ``DELETE``, which reads alarming beside the CRM modules where it
#: retires customer records. Here it removes a saved question and touches no
#: record at all, and the service still refuses to let anybody delete a
#: colleague's without ``VIEW_ALL``.
_USER_ACTIONS: tuple[str, ...] = ("VIEW", "CREATE", "EDIT", "DELETE")

_MODULE = "views"

_VISIBILITIES: tuple[str, ...] = ("PRIVATE", "TEAM", "ORGANIZATION")


def _timestamps() -> list[sa.Column[object]]:
    """The mixin columns every CRM table carries, spelled out once."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    connection = op.get_bind()

    # --- Saved views -------------------------------------------------------
    #
    # `crm_entity_type` already exists, so it is referenced with
    # `create_type=False` and never created here.
    sa.Enum(*_VISIBILITIES, name="view_visibility", schema=CRM).create(
        connection, checkfirst=True
    )
    view_visibility = postgresql.ENUM(
        *_VISIBILITIES, name="view_visibility", schema=CRM, create_type=False
    )
    crm_entity_type = postgresql.ENUM(
        "ACCOUNT",
        "CONTACT",
        "LEAD",
        "OPPORTUNITY",
        "CAMPAIGN",
        name="crm_entity_type",
        schema=CRM,
        create_type=False,
    )

    op.create_table(
        "saved_views",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entity_type", crm_entity_type, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        # NOT NULL, unlike `owner_id` elsewhere: an unowned record is a
        # historical artefact, but an unowned *view* could never have been
        # created — and under the visibility rules it would be one nobody could
        # edit and everybody could see.
        sa.Column("owner_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("visibility", view_visibility, nullable=False, server_default="PRIVATE"),
        sa.Column(
            "filters",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "columns",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("sort_by", sa.String(length=80), nullable=True),
        sa.Column("sort_dir", sa.String(length=4), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_timestamps(),
        schema=CRM,
    )
    op.create_index(
        "ix_saved_views_organization_id", "saved_views", ["organization_id"], schema=CRM
    )
    op.create_index("ix_saved_views_deleted_at", "saved_views", ["deleted_at"], schema=CRM)
    # The read behind every list render: "which views may I see on this entity".
    op.create_index(
        "ix_saved_views_organization_id_entity_type",
        "saved_views",
        ["organization_id", "entity_type"],
        schema=CRM,
    )
    # Scoped to the owner, not the organization: two reps each having their own
    # "My hot leads" is normal, and refusing the second would be surprising.
    op.create_index(
        "uq_saved_views_owner_entity_name_live",
        "saved_views",
        ["organization_id", "owner_id", "entity_type", "name"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # At most one default per person per record type. A default is a personal
    # preference — one administrator's choice must not become everybody's.
    op.create_index(
        "uq_saved_views_owner_entity_default",
        "saved_views",
        ["organization_id", "owner_id", "entity_type"],
        unique=True,
        schema=CRM,
        postgresql_where=sa.text("is_default AND deleted_at IS NULL"),
    )

    enable_rls(connection, "saved_views", schema=CRM)

    # --- Merge pointers ----------------------------------------------------

    for table in _MERGEABLE:
        op.add_column(
            table,
            sa.Column("merged_into_id", sa.Uuid(as_uuid=True), nullable=True),
            schema=CRM,
        )
        op.create_foreign_key(
            f"fk_{table}_merged_into_id_{table}",
            table,
            table,
            ["merged_into_id"],
            ["id"],
            source_schema=CRM,
            referent_schema=CRM,
            ondelete="SET NULL",
        )
        # Partial: the overwhelming majority of records were never merged, and
        # the only query that reads this column looks for the ones that were.
        op.create_index(
            f"ix_{table}_merged_into_id",
            table,
            ["merged_into_id"],
            schema=CRM,
            postgresql_where=sa.text("merged_into_id IS NOT NULL"),
        )

    # --- The index the calendar reads meetings through ---------------------
    #
    # `crm.meetings` had no index on its scheduling column, so "which meetings
    # overlap this window" scanned the tenant's whole history on every grid
    # render. On `start_time` alone because the table carries no tenant column:
    # it is a strict 1:1 extension of an activity, and the join to
    # `crm.activities` is what applies the tenant filter.
    #
    # There is deliberately no companion index on `crm.tasks`: the other half
    # of the calendar reads `(organization_id, due_date)`, which revision
    # `8224845a67ac` already built. A second index on the same columns would
    # cost write throughput on every task in the product and buy nothing.
    op.create_index("ix_meetings_start_time", "meetings", ["start_time"], schema=CRM)

    # --- The `views` permission module --------------------------------------

    for action in _ACTIONS:
        connection.execute(
            sa.text(
                "INSERT INTO platform.permissions (module, action, description) "
                "VALUES (:module, CAST(:action AS platform.permission_action), :description) "
                "ON CONFLICT (module, action) DO NOTHING"
            ),
            {
                "module": _MODULE,
                "action": action,
                "description": f"{action} saved list views",
            },
        )

    _grant("Admin", _ACTIONS, connection)
    _grant("Manager", _MANAGER_ACTIONS, connection)
    _grant("User", _USER_ACTIONS, connection)


def _grant(role: str, actions: tuple[str, ...], connection: sa.Connection) -> None:
    """Grant ``views.<action>`` to a system role template.

    Templates are the rows with ``organization_id IS NULL``; every
    organization's memberships reference them, so granting once here reaches
    every existing tenant without a per-organization loop.
    """
    for action in actions:
        connection.execute(
            sa.text(
                "INSERT INTO platform.role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
                "WHERE r.organization_id IS NULL AND r.name = :role "
                "  AND p.module = :module "
                "  AND p.action = CAST(:action AS platform.permission_action) "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"role": role, "module": _MODULE, "action": action},
        )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            "DELETE FROM platform.role_permissions WHERE permission_id IN "
            "(SELECT id FROM platform.permissions WHERE module = :module)"
        ),
        {"module": _MODULE},
    )
    connection.execute(
        sa.text("DELETE FROM platform.permissions WHERE module = :module"),
        {"module": _MODULE},
    )

    op.drop_index("ix_meetings_start_time", table_name="meetings", schema=CRM)

    # Dropping `merged_into_id` discards the record of which duplicates went
    # where. The merges themselves are not undone — the references stay moved
    # and the losers stay retired — so what is lost is the trail from an old id
    # to its survivor. Said out loud because a downgrade usually reverses
    # something, and this one does not.
    for table in reversed(_MERGEABLE):
        op.drop_index(f"ix_{table}_merged_into_id", table_name=table, schema=CRM)
        op.drop_constraint(f"fk_{table}_merged_into_id_{table}", table, schema=CRM)
        op.drop_column(table, "merged_into_id", schema=CRM)

    disable_rls(connection, "saved_views", schema=CRM)
    op.drop_table("saved_views", schema=CRM)

    sa.Enum(name="view_visibility", schema=CRM).drop(connection, checkfirst=True)
