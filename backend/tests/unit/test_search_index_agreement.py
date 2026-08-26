"""The search vectors and their indexes have to agree in three places.

A search index fails silently. Nothing errors when a vector expression drifts
from the migration that built it, or when a query stops matching the
expression its index was created on — results just quietly get worse, and the
first person to notice is a user who cannot find a record they know exists.

So the agreements are pinned here rather than left to review:

1. **Model vs migration.** Each ``search_vector`` is declared twice on purpose
   — the migration is the snapshot that built the column, the model is the
   live definition — and a change to one without the other means the code
   describes a column the database does not have.
2. **Query vs trigram index.** ``_display_name`` in the repository must render
   the same expression the index was created on, casts included. This is the
   one that already went wrong once: an index on ``name`` (varchar) never
   matched a query on ``(name)::text``, and the fuzzy branch fell back to a
   sequential scan that no test would have caught.
3. **Coverage.** Every searchable entity has both, and no entity is searched
   without them.

These are string comparisons over generated SQL, which is exactly what
PostgreSQL compares when deciding whether an index applies.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.products.crm.search.repository import _display_name
from app.products.crm.search.schemas import SearchEntityType

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "20260826_0100_crm_search_vectors_and_indexes.py"
)

#: Entity type -> the table its rows live in.
TABLES: dict[SearchEntityType, str] = {
    SearchEntityType.ACCOUNT: "accounts",
    SearchEntityType.CONTACT: "contacts",
    SearchEntityType.LEAD: "leads",
    SearchEntityType.OPPORTUNITY: "opportunities",
}


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location("search_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalise(sql: str) -> str:
    """Collapse whitespace so formatting differences are not failures."""
    return re.sub(r"\s+", " ", sql).strip()


@pytest.fixture(scope="module")
def migration() -> Any:
    return _load_migration()


@pytest.mark.parametrize("entity", list(SearchEntityType))
def test_the_model_vector_matches_the_migration_that_built_it(
    entity: SearchEntityType, migration: Any
) -> None:
    from app.products.crm.search.policies import MODEL_FOR_TYPE

    model = MODEL_FOR_TYPE[entity]
    computed = model.__table__.c.search_vector.computed

    assert computed is not None, f"{entity} has no generated search_vector"
    assert computed.persisted is True, "the vector must be STORED, not VIRTUAL"
    assert _normalise(str(computed.sqltext)) == _normalise(
        migration._VECTORS[TABLES[entity]]
    )


@pytest.mark.parametrize("entity", list(SearchEntityType))
def test_the_fuzzy_query_matches_its_trigram_index_expression(
    entity: SearchEntityType, migration: Any
) -> None:
    """The regression that made the trigram index dead weight.

    Compared after stripping the schema-qualified table prefix, which the
    query carries and ``CREATE INDEX`` does not.
    """
    rendered = str(
        _display_name(entity).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    query_expression = _normalise(re.sub(r"\bcrm\.\w+\.", "", rendered))
    index_expression = _normalise(migration._DISPLAY_NAMES[TABLES[entity]])

    # The index form wraps the whole expression in parentheses and writes the
    # cast as ``name::text``; the query renders ``CAST(name AS TEXT)``. Compare
    # them in one canonical form rather than by eye.
    assert _canonical(query_expression) == _canonical(index_expression), (
        f"{entity}: query renders {query_expression!r} but the index is built "
        f"on {index_expression!r}; PostgreSQL will not match them"
    )


def _canonical(expression: str) -> str:
    """Reduce both cast spellings and stray parentheses to one form."""
    expression = re.sub(
        r"CAST\((\w+) AS TEXT\)", r"\1::text", expression, flags=re.IGNORECASE
    )
    return expression.replace("(", "").replace(")", "").replace(" ", "").lower()


def test_every_searchable_entity_is_covered(migration: Any) -> None:
    """A fifth entity added to the enum without a vector must fail here."""
    assert set(TABLES) == set(SearchEntityType)
    assert set(migration._VECTORS) == set(TABLES.values())
    assert set(migration._DISPLAY_NAMES) == set(TABLES.values())


def test_every_vector_pins_the_text_search_configuration(migration: Any) -> None:
    """``to_tsvector(body)`` is only STABLE and cannot build a stored column.

    More importantly, it would stem according to whoever's session wrote the
    row. Every call must name the configuration explicitly, and it must be the
    one the query uses.
    """
    from app.products.crm.search.repository import TS_CONFIG

    for table, expression in migration._VECTORS.items():
        assert "to_tsvector('english'::regconfig" in expression, table
        assert expression.count("to_tsvector(") == expression.count(
            "to_tsvector('english'::regconfig"
        ), f"{table} has a to_tsvector call with no explicit configuration"
    assert TS_CONFIG == "english"
