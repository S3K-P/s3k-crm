"""Add a call duration to activities (Checkpoint 3, Calls as a proper activity type).

Revision ID: 20260915_0100
Revises: 20260914_0200
Create Date: 2026-09-15 01:00:00.000000

The Checkpoint 3 audit found calls logged only as ``Activity(type=CALL)`` with
a free-text ``outcome`` — everything a call needs except how long it ran.
Direction, the caller and what happened are already covered (``owner_id``,
``related_entity_*``, ``outcome``); duration was the one structured field with
nowhere to live. It is a plain nullable column on ``activities`` rather than a
second one-to-one extension table like ``meetings``: a meeting needs five
scheduling columns and an attendee list, but a call needs exactly one number,
and it is meaningful for a completed call of any type, not only ``CALL``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0100"
down_revision: str | Sequence[str] | None = "20260914_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        schema=CRM,
    )
    op.create_check_constraint(
        "duration_minutes_non_negative",
        "activities",
        "duration_minutes IS NULL OR duration_minutes >= 0",
        schema=CRM,
    )


def downgrade() -> None:
    op.drop_constraint(
        "duration_minutes_non_negative", "activities", schema=CRM, type_="check"
    )
    op.drop_column("activities", "duration_minutes", schema=CRM)
