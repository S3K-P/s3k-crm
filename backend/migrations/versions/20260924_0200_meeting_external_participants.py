"""Add an external-participants field to meetings.

Revision ID: 20260924_0200
Revises: 20260924_0100
Create Date: 2026-09-24 02:00:00.000000

``crm.meetings`` already tracks who inside the organization is attending
(``internal_participant_ids``, an array of org-member ids), but has nowhere
to record who from outside it is in the room — the client contacts a meeting
was actually booked with. A plain nullable text column, the same shape as
``location`` or ``agenda`` right next to it: free text rather than a
structured list, because an external attendee is not necessarily a CRM
contact at all (a prospect's colleague who has no record yet, a vendor,
someone CC'd at the last minute), and forcing a lookup against existing
contacts would make the field unusable for exactly the people it is meant to
note.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0200"
down_revision: str | Sequence[str] | None = "20260924_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("external_participants", sa.Text(), nullable=True),
        schema=CRM,
    )


def downgrade() -> None:
    op.drop_column("meetings", "external_participants", schema=CRM)
