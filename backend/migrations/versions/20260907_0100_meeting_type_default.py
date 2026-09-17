"""Give ``crm.meetings.meeting_type`` the default its API contract promises.

``MeetingDetail.meeting_type`` has always declared ``MeetingType.VIDEO`` as its
default, but the create route dumps its payload with
``model_dump(exclude_unset=True)`` — correct for PATCH, where it is what
separates "not sent" from "set to null". The consequence on the create path is
that a field the client omits never reaches the service at all, so the declared
default was silently dropped and the INSERT put NULL into a NOT NULL column.
Posting a meeting without ``meeting_type`` returned 500, not the documented
VIDEO.

The column now carries the same default the schema advertises, which is how
every comparable column in this table already behaves:
``internal_participant_ids`` has ``server_default="{}"`` and
``activities.status`` has ``server_default='PLANNED'`` beside the identical
Pydantic default. ``meeting_type`` was simply the one that was missed.

Fixing it here rather than in the router keeps the rule in one place — the
router holds no business rules (ARCHITECTURE-BOUNDARIES.md), and every writer
of this table gets the default, not just the one HTTP route.

No backfill: the column is NOT NULL and has been since it was created, so no
existing row can be missing a value.

Revision ID: 20260907_0100
Revises: 20260905_0100
Create Date: 2026-09-07 01:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260907_0100"
down_revision: str | None = "20260905_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "meetings",
        "meeting_type",
        existing_type=sa.Enum(
            "IN_PERSON", "VIDEO", "PHONE", name="meeting_type", schema="crm"
        ),
        existing_nullable=False,
        server_default="VIDEO",
        schema="crm",
    )


def downgrade() -> None:
    op.alter_column(
        "meetings",
        "meeting_type",
        existing_type=sa.Enum(
            "IN_PERSON", "VIDEO", "PHONE", name="meeting_type", schema="crm"
        ),
        existing_nullable=False,
        server_default=None,
        schema="crm",
    )
