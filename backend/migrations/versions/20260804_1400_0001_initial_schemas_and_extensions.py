"""Initial schemas, extensions and the tenant-isolation probe table

Creates the two PostgreSQL schemas the modular monolith is partitioned into
(``platform`` and ``crm`` — one database, ADR-007) and the extensions later
phases depend on.

Also creates ``platform.tenant_isolation_probe``: a deliberately throwaway
table whose only job is to let the Phase 0 integration test prove RLS actually
denies cross-organization reads before any real table exists (P0-W02-BE-05).
It carries no business meaning and is dropped by a later migration once a real
tenant-scoped table takes over that duty.

Revision ID: 0001_initial_schemas
Revises:
Create Date: 2026-08-04

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.rls import disable_rls, enable_rls

revision: str = "0001_initial_schemas"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLATFORM_SCHEMA = "platform"
CRM_SCHEMA = "crm"
PROBE_TABLE = "tenant_isolation_probe"


def upgrade() -> None:
    connection = op.get_bind()

    # --- Schemas (ADR-001: one database, module-owned schemas) -------------
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{PLATFORM_SCHEMA}"'))
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{CRM_SCHEMA}"'))

    # --- Extensions --------------------------------------------------------
    # pgcrypto: gen_random_bytes for token hashing (ADR-009).
    # pg_trgm:  trigram indexes backing CRM fuzzy search (ADR-015).
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    # --- Tenant isolation probe (temporary, Phase 0 only) ------------------
    op.create_table(
        PROBE_TABLE,
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuidv7()"),
        ),
        sa.Column(
            "organization_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema=PLATFORM_SCHEMA,
        comment=(
            "Phase 0 RLS verification probe. Carries no business data and is "
            "dropped once a real tenant-scoped table exists."
        ),
    )
    op.create_index(
        f"ix_{PROBE_TABLE}_organization_id",
        PROBE_TABLE,
        ["organization_id"],
        schema=PLATFORM_SCHEMA,
    )

    enable_rls(connection, PROBE_TABLE, schema=PLATFORM_SCHEMA)


def downgrade() -> None:
    connection = op.get_bind()

    disable_rls(connection, PROBE_TABLE, schema=PLATFORM_SCHEMA)
    op.drop_index(f"ix_{PROBE_TABLE}_organization_id", PROBE_TABLE, schema=PLATFORM_SCHEMA)
    op.drop_table(PROBE_TABLE, schema=PLATFORM_SCHEMA)

    # Extensions and schemas are left in place on downgrade: dropping a schema
    # would cascade into anything a later migration added, and dropping a
    # shared extension can break unrelated objects. Both are idempotent to
    # re-create, so this is the safe asymmetry.
