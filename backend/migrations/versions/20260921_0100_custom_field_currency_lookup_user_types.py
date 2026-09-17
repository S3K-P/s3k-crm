"""Custom fields: CURRENCY and LOOKUP_USER types (Zoho field/layout parity).

Revision ID: 20260921_0100
Revises: 20260920_0100
Create Date: 2026-09-21 01:00:00.000000

Two new members of ``crm.custom_field_type``. ``CURRENCY`` shares ``DECIMAL``'s
coercion and comparison rules exactly — it exists as its own type only so the
admin field-type picker and the rendered input can label and format it as
money rather than a bare number. ``LOOKUP_USER`` stores an organization
member's id, the way every other custom value is stored: as a string, not a
foreign key — see ``app/products/crm/custom_fields/models.py`` for why.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_0100"
down_revision: str | Sequence[str] | None = "20260920_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Native PostgreSQL enum — ALTER TYPE ... ADD VALUE cannot run inside a
    # transaction block on some versions; Alembic's default transaction is
    # fine on PG 12+ for ADD VALUE IF NOT EXISTS (see 20260818_1900 for the
    # same pattern applied to `lead_status`).
    op.execute(
        sa.text("ALTER TYPE crm.custom_field_type ADD VALUE IF NOT EXISTS 'CURRENCY'")
    )
    op.execute(
        sa.text("ALTER TYPE crm.custom_field_type ADD VALUE IF NOT EXISTS 'LOOKUP_USER'")
    )


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value safely; leave both in place. Any
    # field actually created with one of these types would need to be
    # deactivated by an administrator before a real rollback of this feature.
    pass
