"""Full-text search vectors and indexes for the four searchable CRM entities.

Revision ID: 20260826_0100
Revises: 20260824_0100
Create Date: 2026-08-26 01:00:00.000000

Opens W20 (`P3-W20-BE-01`, `BE-02`, `BE-05`). Adds a `search_vector` to
`crm.accounts`, `crm.contacts`, `crm.leads` and `crm.opportunities`, the GIN
indexes that make it searchable, and the `pg_trgm` indexes doc 12 specifies for
fuzzy name matching.

**Generated columns, not triggers (CR16).** `P3-W20-BE-01` says "maintain via
triggers". A stored generated column is used instead, for one reason: a trigger
is a thing you can forget. It has to be created per table, re-created if the
table is rebuilt, and it silently stops reflecting a column that somebody adds
to the entity later — leaving a vector that is subtly stale rather than
obviously broken, which is the worst failure mode a search index has. A
generated column is part of the table definition; PostgreSQL maintains it or
the write fails.

The expression must be IMMUTABLE, which is why every `to_tsvector` call below
passes `'english'::regconfig` explicitly rather than relying on
`default_text_search_config` — the one-argument form is only STABLE, because
the default is a session setting, and PostgreSQL refuses it here. That refusal
is a feature: it is the database declining to build an index whose contents
would depend on who happened to write the row.

**`P3-W20-BE-05` is satisfied by this migration rather than by a second one.**
Adding a stored generated column computes it for every existing row as part of
the `ALTER TABLE` rewrite, so there is no window in which old rows are
unsearchable and nothing to backfill afterwards. A separate backfill migration
would have had no rows left to find.

**Weighting.** `A` is what somebody types when they know what they are looking
for — a name. `B` is the next-best identifier (email, company, industry). `C`
and `D` are context that should match but never outrank a name. `ts_rank`
weights these 1.0 / 0.4 / 0.2 / 0.1 by default, so "Acme" the account name
beats "acme" mentioned in another record's notes without any tie-breaking in
the query.

Deleted rows keep their vectors: the partial indexes below exclude
`deleted_at IS NOT NULL`, so a soft-deleted record costs index space but is
never returned. Filtering in the index rather than in the vector means undelete
needs no reindex.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260826_0100"
down_revision: str | None = "20260824_0100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CRM = "crm"

#: The searchable text of an ``email`` column: the whole address, plus its
#: local part and first domain label as separate words.
#:
#: PostgreSQL's parser treats an address as a single token, so a vector built
#: from ``email`` alone matches "ravi@zephyr.example" but never "zephyr" —
#: which is how people actually search for everyone at a company. Taking the
#: first domain *label* rather than the whole domain stops short of indexing
#: the TLD, which would make "com" a lexeme matching most of the table.
_EMAIL_TERMS = (
    "coalesce(email, '') || ' ' || "
    "split_part(coalesce(email, ''), '@', 1) || ' ' || "
    "split_part(split_part(coalesce(email, ''), '@', 2), '.', 1)"
)

#: table -> the weighted tsvector expression for that entity.
#:
#: Pinned here rather than imported from the models, for the same reason the
#: B02 migration pins its module list: a migration is a snapshot of history,
#: and a later model edit must not silently rewrite what an old revision did.
_VECTORS: dict[str, str] = {
    "accounts": (
        "setweight(to_tsvector('english'::regconfig, coalesce(name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(industry, '')), 'B') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(website, '')), 'B') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(city, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(country, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(description, '')), 'D')"
    ),
    "contacts": (
        "setweight(to_tsvector('english'::regconfig, coalesce(first_name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(last_name, '')), 'A') || "
        f"setweight(to_tsvector('english'::regconfig, {_EMAIL_TERMS}), 'B') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(job_title, '')), 'B') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(department, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(city, '')), 'C')"
    ),
    "leads": (
        "setweight(to_tsvector('english'::regconfig, coalesce(first_name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(last_name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(company, '')), 'B') || "
        f"setweight(to_tsvector('english'::regconfig, {_EMAIL_TERMS}), 'B') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(industry, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(product_interest, '')), 'C')"
    ),
    "opportunities": (
        "setweight(to_tsvector('english'::regconfig, coalesce(name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(forecast_category, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(competitor, '')), 'C') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(notes, '')), 'D')"
    ),
}

#: table -> the expression a fuzzy name match runs against, which is also the
#: expression the trigram index is built on. The two must stay identical or the
#: index is dead weight: PostgreSQL matches an expression index by the
#: expression, not by intent.
#:
#: **The ``::text`` casts are load-bearing.** ``name`` is ``varchar(255)``, but
#: ``gin_trgm_ops`` is a ``text`` operator class, so the operator that reaches
#: the planner is ``%>(text, text)`` over ``(name)::text``. An index declared
#: on the bare ``varchar`` column does not match that expression, and the
#: result is a perfectly valid index that is never chosen — verified with
#: ``EXPLAIN`` over 20 000 rows, where the un-cast form fell back to a full
#: scan even with ``enable_seqscan = off``.
_DISPLAY_NAMES: dict[str, str] = {
    "accounts": "(name::text)",
    "contacts": "(first_name::text || ' ' || last_name::text)",
    "leads": "(first_name::text || ' ' || last_name::text)",
    "opportunities": "(name::text)",
}


def upgrade() -> None:
    for table, expression in _VECTORS.items():
        op.execute(
            sa.text(
                f"ALTER TABLE {CRM}.{table} "
                f"ADD COLUMN search_vector tsvector "
                f"GENERATED ALWAYS AS ({expression}) STORED"
            )
        )
        # Partial: a soft-deleted record must never be a search result, and
        # excluding it here keeps it out of every query by construction rather
        # than by every caller remembering the predicate.
        op.execute(
            sa.text(
                f"CREATE INDEX ix_{table}_search_vector ON {CRM}.{table} "
                f"USING GIN (search_vector) WHERE deleted_at IS NULL"
            )
        )
        op.execute(
            sa.text(
                f"CREATE INDEX ix_{table}_display_name_trgm ON {CRM}.{table} "
                f"USING GIN (({_DISPLAY_NAMES[table]}) gin_trgm_ops) "
                f"WHERE deleted_at IS NULL"
            )
        )


def downgrade() -> None:
    for table in _VECTORS:
        op.execute(sa.text(f"DROP INDEX IF EXISTS {CRM}.ix_{table}_display_name_trgm"))
        op.execute(sa.text(f"DROP INDEX IF EXISTS {CRM}.ix_{table}_search_vector"))
        # The column goes with the index; a generated column cannot outlive
        # the expression that defines it in any useful way.
        op.execute(sa.text(f"ALTER TABLE {CRM}.{table} DROP COLUMN IF EXISTS search_vector"))
