"""Products and entitlements: the product-access control (ADR-011).

Revision ID: 20260826_0200
Revises: 20260826_0100
Create Date: 2026-08-26 02:00:00.000000

Closes `P1-W08-BE-01` and risk R10 — the one GATE 1 exit criterion still
unmet. Until now every authenticated member of an organization could reach
``/crm/*``, because with one product the distinction cost nothing. ADR-011
draws it anyway: "CRM access is not Books access."

Three things happen here, and the third is the one that must not be forgotten.

**The catalogue.** ``platform.products`` is global reference data — "s3k-crm"
means the same thing to every tenant — so it carries no ``organization_id``
and is RLS-exempt. That exemption is safe precisely because the table holds no
customer data; the entitlements that name customers are a separate table.

**The grants.** ``platform.product_entitlements`` is tenant-scoped, with RLS
enabled *and* FORCEd like every other table naming a customer.

**The backfill.** Every organization that already exists is granted the CRM,
in this same migration. Without it, deploying the gate would lock every
current tenant out of the product they are already using — the migration would
be a silent outage rather than a control. New organizations are entitled at
creation by ``OrganizationService``; this covers the ones that predate it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.core.rls import disable_rls, enable_rls

revision: str = "20260826_0200"
down_revision: str | None = "20260826_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM = "platform"

#: Pinned, not imported from the models. A migration is a snapshot of history;
#: a later rename of the constant must not rewrite what this revision did.
CRM_CODE = "s3k-crm"
CRM_NAME = "S3K CRM"


def upgrade() -> None:
    connection = op.get_bind()

    # Created explicitly, then referenced with ``create_type=False``. Without
    # that flag SQLAlchemy emits CREATE TYPE again from inside create_table
    # and the migration dies on DuplicateObject — the enum has to be built
    # once and then only named.
    sa.Enum(
        "ACTIVE", "DEPRECATED", "RETIRED", name="product_status", schema=PLATFORM
    ).create(connection, checkfirst=True)
    sa.Enum(
        "ACTIVE", "SUSPENDED", "REVOKED", name="entitlement_status", schema=PLATFORM
    ).create(connection, checkfirst=True)

    product_status = postgresql.ENUM(
        "ACTIVE",
        "DEPRECATED",
        "RETIRED",
        name="product_status",
        schema=PLATFORM,
        create_type=False,
    )
    entitlement_status = postgresql.ENUM(
        "ACTIVE",
        "SUSPENDED",
        "REVOKED",
        name="entitlement_status",
        schema=PLATFORM,
        create_type=False,
    )

    # --- Catalogue ---------------------------------------------------------
    op.create_table(
        "products",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column(
            "status",
            product_status,
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        schema=PLATFORM,
    )
    op.create_index("uq_products_code", "products", ["code"], unique=True, schema=PLATFORM)

    # --- Grants ------------------------------------------------------------
    op.create_table(
        "product_entitlements",
        sa.Column(
            "id", sa.Uuid(as_uuid=True), server_default=sa.text("uuidv7()"), nullable=False
        ),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            entitlement_status,
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_entitlements")),
        # RESTRICT: removing a product from the catalogue must not silently
        # drop the record of who was licensed for it. Retire it instead.
        sa.ForeignKeyConstraint(
            ["product_id"],
            [f"{PLATFORM}.products.id"],
            name="fk_product_entitlements_product_id_products",
            ondelete="RESTRICT",
        ),
        schema=PLATFORM,
    )
    op.create_index(
        op.f("ix_product_entitlements_organization_id"),
        "product_entitlements",
        ["organization_id"],
        unique=False,
        schema=PLATFORM,
    )
    op.create_index(
        "uq_product_entitlements_organization_id_product_id",
        "product_entitlements",
        ["organization_id", "product_id"],
        unique=True,
        schema=PLATFORM,
    )

    enable_rls(connection, "product_entitlements", schema=PLATFORM)

    # --- Seed the catalogue ------------------------------------------------
    connection.execute(
        sa.text(
            "INSERT INTO platform.products (code, name) VALUES (:code, :name) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {"code": CRM_CODE, "name": CRM_NAME},
    )

    # --- Backfill every existing organization ------------------------------
    # The step that keeps this migration from being an outage. Without it the
    # gate would refuse every tenant currently using the CRM.
    connection.execute(
        sa.text(
            "INSERT INTO platform.product_entitlements (organization_id, product_id) "
            "SELECT o.id, p.id FROM platform.organizations o, platform.products p "
            "WHERE p.code = :code "
            "ON CONFLICT (organization_id, product_id) DO NOTHING"
        ),
        {"code": CRM_CODE},
    )


def downgrade() -> None:
    connection = op.get_bind()

    disable_rls(connection, "product_entitlements", schema=PLATFORM)
    op.drop_table("product_entitlements", schema=PLATFORM)
    op.drop_table("products", schema=PLATFORM)

    sa.Enum(name="entitlement_status", schema=PLATFORM).drop(connection, checkfirst=True)
    sa.Enum(name="product_status", schema=PLATFORM).drop(connection, checkfirst=True)
