"""Full-text search vector and indexes for activities (Checkpoint 5).

Revision ID: 20260917_0300
Revises: 20260917_0200
Create Date: 2026-09-17 03:00:00.000000

The fifth entity global search covers, added the same way revision
``20260826_0100`` added the first four — a stored generated ``search_vector``
column (never a trigger; see that revision's own docstring for why), a
partial GIN index over it, and a trigram index for fuzzy matching, all scoped
to live rows only.

``subject`` is weighted ``A`` as the record's name-equivalent; ``outcome``
(what happened) is ``C``; ``description`` (what was planned) is ``D``. A
meeting's own ``location``/``agenda`` live on the separate ``meetings`` table
and are not folded in — see ``activities/models.py`` for why a generated
column cannot reach across tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0300"
down_revision: str | Sequence[str] | None = "20260917_0200"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"
TABLE = "activities"

_VECTOR_EXPRESSION = (
    "setweight(to_tsvector('english'::regconfig, coalesce(subject, '')), 'A') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(outcome, '')), 'C') || "
    "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'D')"
)
_DISPLAY_NAME = "(subject::text)"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"ALTER TABLE {CRM}.{TABLE} "
            f"ADD COLUMN search_vector tsvector "
            f"GENERATED ALWAYS AS ({_VECTOR_EXPRESSION}) STORED"
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX ix_{TABLE}_search_vector ON {CRM}.{TABLE} "
            f"USING GIN (search_vector) WHERE deleted_at IS NULL"
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX ix_{TABLE}_display_name_trgm ON {CRM}.{TABLE} "
            f"USING GIN (({_DISPLAY_NAME}) gin_trgm_ops) "
            f"WHERE deleted_at IS NULL"
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS {CRM}.ix_{TABLE}_display_name_trgm"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS {CRM}.ix_{TABLE}_search_vector"))
    op.execute(sa.text(f"ALTER TABLE {CRM}.{TABLE} DROP COLUMN IF EXISTS search_vector"))
