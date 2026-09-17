"""Record whether a research turn could search, or only recollect.

Revision ID: 20260901_0100
Revises: 20260831_0300
Create Date: 2026-09-01 01:00:00.000000

Market Insights was built on one provider whose web search is always
available, so "was this answer researched" never needed asking — it always
was. With a second provider that can be entitled to generation but not to
Search grounding (Google's free tier is exactly this), the question becomes
real and the answer has to be stored per turn.

**Why not infer it from the sources list.** An empty source list is ambiguous:
a grounded turn may legitimately decide a question needs no search. Only a turn
that *could not* search is answering from training data, and that is the one the
interface must label as recollection rather than research. Inference cannot
tell the two apart; a column can.

Defaults to TRUE, which is correct for every row that already exists: they were
all produced by the Anthropic provider with web search available. The column is
therefore accurate for history rather than merely permissive about it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260901_0100"
down_revision: str | None = "20260831_0300"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"
TABLE = "market_insight_messages"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "grounded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
            comment=(
                "Whether a web-search tool was available to this turn. False means "
                "the answer came from model training data with nothing to cite."
            ),
        ),
        schema=CRM,
    )


def downgrade() -> None:
    op.drop_column(TABLE, "grounded", schema=CRM)
