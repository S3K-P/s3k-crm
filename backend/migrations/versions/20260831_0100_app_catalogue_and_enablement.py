"""The S3K app catalogue: presentation metadata and administrator enablement.

Revision ID: 20260831_0100
Revises: 20260827_0100
Create Date: 2026-08-31 01:00:00.000000

The platform shell needs to answer two questions the entitlement tables could
not: *what apps does S3K offer* and *which of the ones we hold are switched
on*. Both are added here without moving the ADR-011 boundary.

**Catalogue metadata.** ``platform.products`` gains the fields an app card is
drawn from — summary, description, icon, entry route, sort order. It stays
global reference data with no ``organization_id``, so it stays RLS-exempt.

**``availability``, and why it is not ``status``.** ``status`` already answers
*is this product still sold* (ACTIVE / DEPRECATED / RETIRED). It cannot answer
*has this product been built*, and conflating the two would mean the only way
to list an unbuilt app in the catalogue is to mark it sellable. ``availability``
is the second axis: ``AVAILABLE`` for an app with real functionality behind it,
``COMING_SOON`` for one that exists only as a catalogue entry. The service layer
refuses to grant anything that is not ``AVAILABLE``, so a coming-soon app cannot
be entitled by any path — which is what keeps the launcher from ever opening a
door onto nothing.

**``self_serve``.** Whether a brand-new organization may be entitled to this
product by signing up, as opposed to it being sold. Signup grants only the
self-serve set, so onboarding cannot become a way to license anything.

**``enabled``, and why it is not a second licence.** ``product_entitlements``
gains an administrator-controlled switch, and it can only ever *narrow* the
grant it hangs off. The gate requires the entitlement to be usable **and**
enabled, so switching the CRM off closes it for the whole organization, and
switching it back on restores nothing more than what was already licensed. An
administrator still cannot reach a product their organization was never
granted, so ADR-011 holds: the escalation it forbids is not reachable from
here. It defaults to TRUE precisely so this migration changes no existing
tenant access.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0100"
#: Chained after the AI gateway rather than beside it. Both this and
#: ``20260827_0100`` were written against ``20260826_0200`` on separate
#: branches, which left Alembic with two heads and ``upgrade head`` refusing to
#: run at all. They touch disjoint tables — this one the product catalogue, the
#: other the AI and Market Insights tables — so ordering them is a free choice,
#: and chronological order is the one a reader can predict.
down_revision: str | None = "20260827_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"

#: Pinned, not imported from the models — a migration is a snapshot of history.
CRM_CODE = "s3k-crm"

#: The catalogue as it stands on this date. Only the CRM is AVAILABLE; the rest
#: are listed so "Explore S3K Apps" has honest content, and they are
#: unreachable because nothing may be granted unless it is AVAILABLE.
CATALOGUE: tuple[dict[str, object], ...] = (
    {
        "code": CRM_CODE,
        "name": "S3K CRM",
        "summary": "Customers, leads and sales pipeline",
        "description": (
            "Track accounts, contacts and leads, qualify opportunities through "
            "your pipeline, and keep every call, meeting and note against the "
            "record it belongs to."
        ),
        "icon": "Users",
        # The **frontend** entry point, not the API prefix. The CRM's pages sit
        # at the application root ("/dashboard", "/leads", …) because Next.js
        # route groups like ``(crm)`` add no path segment; only the API is
        # under ``/api/v1/crm``. Confusing the two sends the launcher to a 404.
        "route": "/dashboard",
        "availability": "AVAILABLE",
        "self_serve": True,
        "sort_order": 10,
    },
    {
        "code": "s3k-sales",
        "name": "S3K Sales",
        "summary": "Quotes, orders and revenue",
        "description": "Quotations, sales orders, invoicing and revenue forecasting.",
        "icon": "TrendingUp",
        "route": None,
        "availability": "COMING_SOON",
        "self_serve": False,
        "sort_order": 20,
    },
    {
        "code": "s3k-marketing",
        "name": "S3K Marketing",
        "summary": "Campaigns and audience engagement",
        "description": "Email campaigns, audience segments and attribution reporting.",
        "icon": "Megaphone",
        "route": None,
        "availability": "COMING_SOON",
        "self_serve": False,
        "sort_order": 30,
    },
    {
        "code": "s3k-hr",
        "name": "S3K HR",
        "summary": "People, leave and onboarding",
        "description": "Employee records, leave management, onboarding and reviews.",
        "icon": "UserCog",
        "route": None,
        "availability": "COMING_SOON",
        "self_serve": False,
        "sort_order": 40,
    },
    {
        "code": "s3k-finance",
        "name": "S3K Finance",
        "summary": "Accounting and expenses",
        "description": "Ledgers, expenses, reconciliation and financial reporting.",
        "icon": "Wallet",
        "route": None,
        "availability": "COMING_SOON",
        "self_serve": False,
        "sort_order": 50,
    },
    {
        "code": "s3k-projects",
        "name": "S3K Projects",
        "summary": "Delivery, tasks and timesheets",
        "description": "Project plans, task boards, timesheets and delivery tracking.",
        "icon": "KanbanSquare",
        "route": None,
        "availability": "COMING_SOON",
        "self_serve": False,
        "sort_order": 60,
    },
)

_UPSERT = sa.text(
    "INSERT INTO platform.products "
    "  (code, name, summary, description, icon, route, availability, "
    "   self_serve, sort_order) "
    "VALUES "
    "  (:code, :name, :summary, :description, :icon, :route, "
    "   CAST(:availability AS platform.product_availability), "
    "   :self_serve, :sort_order) "
    "ON CONFLICT (code) DO UPDATE SET "
    "  name = EXCLUDED.name, "
    "  summary = EXCLUDED.summary, "
    "  description = EXCLUDED.description, "
    "  icon = EXCLUDED.icon, "
    "  route = EXCLUDED.route, "
    "  availability = EXCLUDED.availability, "
    "  self_serve = EXCLUDED.self_serve, "
    "  sort_order = EXCLUDED.sort_order"
)


def upgrade() -> None:
    connection = op.get_bind()

    # Built once and thereafter only named — see the note in 20260826_0200 on
    # why ``create_type=False`` is required at the point of use.
    sa.Enum("AVAILABLE", "COMING_SOON", name="product_availability", schema=PLATFORM).create(
        connection, checkfirst=True
    )
    availability = postgresql.ENUM(
        "AVAILABLE",
        "COMING_SOON",
        name="product_availability",
        schema=PLATFORM,
        create_type=False,
    )

    # --- Catalogue metadata -------------------------------------------------
    #
    # Every added column is NOT NULL with a server default, so the CRM row that
    # already exists stays valid for the whole migration and no reader can
    # observe a half-populated catalogue.
    op.add_column(
        "products",
        sa.Column("summary", sa.String(length=200), nullable=False, server_default=""),
        schema=PLATFORM,
    )
    op.add_column(
        "products",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        schema=PLATFORM,
    )
    op.add_column(
        "products",
        sa.Column("icon", sa.String(length=40), nullable=False, server_default="Boxes"),
        schema=PLATFORM,
    )
    # Nullable: a COMING_SOON product has nowhere to open.
    op.add_column(
        "products", sa.Column("route", sa.String(length=120), nullable=True), schema=PLATFORM
    )
    op.add_column(
        "products",
        sa.Column("availability", availability, nullable=False, server_default="COMING_SOON"),
        schema=PLATFORM,
    )
    op.add_column(
        "products",
        sa.Column("self_serve", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=PLATFORM,
    )
    op.add_column(
        "products",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        schema=PLATFORM,
    )

    # --- Administrator enablement ------------------------------------------
    #
    # TRUE by default: every entitlement that exists today is granting access,
    # and this migration must not be the thing that stops it.
    op.add_column(
        "product_entitlements",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        schema=PLATFORM,
    )

    # --- Seed / update the catalogue ---------------------------------------
    #
    # UPSERT rather than INSERT: the CRM row already exists from 20260826_0200
    # and needs its metadata filled in, while the five others are new.
    for entry in CATALOGUE:
        connection.execute(_UPSERT, entry)


def downgrade() -> None:
    connection = op.get_bind()

    # The five catalogue rows added here go with it. The CRM row predates this
    # revision and is left alone — deleting it would cascade into every
    # entitlement that references it.
    connection.execute(
        sa.text("DELETE FROM platform.products WHERE code <> :code"), {"code": CRM_CODE}
    )

    op.drop_column("product_entitlements", "enabled", schema=PLATFORM)
    for column in (
        "sort_order",
        "self_serve",
        "availability",
        "route",
        "icon",
        "description",
        "summary",
    ):
        op.drop_column("products", column, schema=PLATFORM)

    sa.Enum(name="product_availability", schema=PLATFORM).drop(connection, checkfirst=True)
