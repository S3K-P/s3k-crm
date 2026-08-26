"""The search query. One statement, four branches, every filter inside it.

**Why this file is written the way it is (risk R14).**

The tempting shape for a cross-entity search is: rank everything, take the top
N, then drop the rows the caller may not see. That is wrong in a way that is
invisible in testing, because the results *look* correct — the forbidden rows
are gone. What leaks is everything around them:

* a search that returns three hits out of a limit of twenty tells the caller
  there were seventeen records they cannot read;
* ranking positions shift depending on records the caller cannot see, so
  probing a term and watching a known record move up or down reveals whether a
  better match exists;
* with a limit, post-filtering can return an empty page while matches exist
  further down, which turns a permission boundary into an availability bug.

So every predicate — tenant, soft deletion, entity-type permission and
record-level visibility — is part of the SQL that ranks and limits. The result
set is *already* the caller's; there is nothing left to filter afterwards, and
:mod:`app.products.crm.search.service` does not try.

**Shape.** One ``UNION ALL`` branch per permitted entity type, each projecting
the same five columns, ordered and limited once over the union. Branches for
types the caller cannot ``VIEW`` are never added, so those tables are not
merely filtered to nothing — they are not in the query at all, and cannot
affect ranking or the limit.

**Matching.** Two ways in, OR-ed:

* the stored ``search_vector`` against ``websearch_to_tsquery``, which handles
  stemming, phrases in quotes and ``-exclusions`` — and, being user input
  parsed by PostgreSQL rather than by us, cannot become a malformed tsquery;
* trigram word-similarity against the entity's display name, which is what
  makes "acm" find Acme and "Sharam" find Sharma. Full-text search alone
  cannot: lexemes match whole words, so a prefix or a typo finds nothing.

**Scoring.** ``GREATEST`` of the two, so a hit is as good as its best reason
for matching. ``ts_rank`` values are not comparable across tables with
different vector sizes, so they are not compared: the union is ordered by this
combined score, with the entity type and id as deterministic tie-breakers so
identical scores do not reorder between identical requests.

**On importing four sibling modules' models.** ARCHITECTURE-BOUNDARIES.md
rule 6 allows exactly this: cross-module reads go through the other module's
service "or a dedicated read model", and a read model is what this is. The
alternative — four service calls fanned out and merged in Python — cannot rank
across entity types, cannot apply one limit, and would have to post-filter,
which is the thing this module exists not to do. The CRM dashboard
(`dashboard/repository.py`) is the same shape for the same reason. What the
rule still forbids, and what is not done here, is *writing* through another
module's tables.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy import ColumnElement, Select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.products.crm.accounts.models import Account
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.search.schemas import SearchEntityType

#: The text-search configuration every vector was built with. It must match
#: revision ``20260826_0100`` exactly: querying with a different configuration
#: stems the query differently from the stored lexemes, and matches silently
#: stop happening for exactly the words that need stemming.
TS_CONFIG = "english"

#: Below this, a trigram match is noise rather than a near-miss. PostgreSQL's
#: own default for the ``%>`` operator is 0.6; this is stated explicitly so the
#: behaviour does not depend on a server setting that differs between a
#: developer's database and production.
WORD_SIMILARITY_FLOOR = 0.6


def _display_name(entity: SearchEntityType) -> ColumnElement[str]:
    """The expression a fuzzy match runs against, per entity.

    **Must stay equivalent to the trigram index expression** in revision
    ``20260826_0100``. PostgreSQL matches an expression index by comparing
    expression trees, so ``first_name::text || ' ' || last_name::text`` uses
    the index while ``concat_ws(' ', first_name, last_name)`` — same result,
    same intent — does not, and degrades silently to a sequential scan.

    The explicit ``::text`` casts are part of that equivalence, not
    decoration: these columns are ``varchar`` and ``gin_trgm_ops`` is a
    ``text`` operator class, so the cast appears in the plan whether or not it
    is written here. Writing it makes the index match it.
    """
    text = sa.Text()
    match entity:
        case SearchEntityType.ACCOUNT:
            return sa.cast(Account.name, text)
        case SearchEntityType.CONTACT:
            return sa.cast(Contact.first_name, text) + " " + sa.cast(Contact.last_name, text)
        case SearchEntityType.LEAD:
            return sa.cast(Lead.first_name, text) + " " + sa.cast(Lead.last_name, text)
        case SearchEntityType.OPPORTUNITY:
            return sa.cast(Opportunity.name, text)


def _subtitle(entity: SearchEntityType) -> InstrumentedAttribute[Any]:
    """One line of context beneath the title.

    Every expression here reads a column of the matched record itself, with one
    exception: an opportunity's stage name, joined from ``pipeline_stages``.
    That is safe where an account name would not be — stages are organization
    -wide reference data that any holder of the module permission can already
    list, whereas an account is an owned record whose readability is exactly
    the open question in CR09. Search must not answer that question by
    accident.
    """
    match entity:
        case SearchEntityType.ACCOUNT:
            return Account.industry
        case SearchEntityType.CONTACT:
            return Contact.email
        case SearchEntityType.LEAD:
            return Lead.company
        case SearchEntityType.OPPORTUNITY:
            return PipelineStage.name


class SearchRepository:
    """Builds and runs the one statement global search is."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _branch(
        self,
        entity: SearchEntityType,
        *,
        organization_id: uuid.UUID,
        query: str,
        visibility: ColumnElement[bool] | None,
    ) -> Select[Any]:
        """One entity type's contribution to the union.

        ``visibility`` is the predicate from ``RecordVisibility.filter_for`` —
        ``None`` when the caller reads across owners. It is applied here, in
        the same ``WHERE`` as the match, which is the entire point of this
        module.
        """
        model = _MODEL[entity]
        tsquery = sa.func.websearch_to_tsquery(TS_CONFIG, query)
        display = _display_name(entity)

        # ``word_similarity(needle, haystack)`` — argument order matters and is
        # the reverse of what reads naturally.
        similarity = sa.func.word_similarity(query, display)
        rank = sa.func.ts_rank(model.search_vector, tsquery)

        statement = sa.select(
            sa.literal(entity.value).label("type"),
            model.id.label("id"),
            sa.cast(display, sa.Text).label("title"),
            sa.cast(_subtitle(entity), sa.Text).label("subtitle"),
            sa.func.greatest(rank, similarity).label("score"),
        )

        if entity is SearchEntityType.OPPORTUNITY:
            # LEFT so an opportunity whose stage was deleted still appears —
            # a dangling reference must not make a record unfindable.
            statement = statement.outerjoin(
                PipelineStage, PipelineStage.id == Opportunity.stage_id
            )

        # Two conditions for one idea, and both are needed.
        #
        # ``%>`` is the *indexable* form: ``gin_trgm_ops`` supports the
        # operator and cannot support a ``word_similarity(...) >= x`` function
        # call, which is why the explicit-threshold version of this predicate
        # scanned 20 000 rows in 109 ms and this one does not.
        #
        # The comparison beside it then pins the threshold. ``%>`` uses the
        # server's ``pg_trgm.word_similarity_threshold`` — a GUC, and therefore
        # something a database could be configured with differently from the
        # one this was tested against. The operator narrows using the index;
        # this decides. As long as the GUC is no stricter than the floor, the
        # results are exactly what the floor says they are.
        fuzzy = sa.and_(
            display.op("%>")(sa.literal(query)),
            similarity >= WORD_SIMILARITY_FLOOR,
        )

        statement = statement.where(
            model.organization_id == organization_id,
            model.deleted_at.is_(None),
            sa.or_(model.search_vector.op("@@")(tsquery), fuzzy),
        )

        if visibility is not None:
            statement = statement.where(visibility)

        return statement

    async def search(
        self,
        *,
        organization_id: uuid.UUID,
        query: str,
        branches: Sequence[tuple[SearchEntityType, ColumnElement[bool] | None]],
        limit: int,
    ) -> Sequence[sa.Row[Any]]:
        """Run the union and return ranked rows.

        ``branches`` pairs each *permitted* entity type with the visibility
        predicate for that type — resolved separately per type, because a
        custom role may hold ``VIEW_ALL`` on leads and owner-only on accounts.
        Passing one predicate for all four would silently widen or narrow three
        of them.

        An empty ``branches`` means the caller may search nothing, and no
        statement is executed at all.
        """
        if not branches:
            return ()

        selects = [
            self._branch(
                entity,
                organization_id=organization_id,
                query=query,
                visibility=visibility,
            )
            for entity, visibility in branches
        ]

        union = selects[0] if len(selects) == 1 else sa.union_all(*selects)
        combined = union.subquery("hits")

        statement = (
            sa.select(combined)
            # Type and id after score so two equally-ranked rows keep a stable
            # order between identical requests. Without them PostgreSQL is free
            # to return ties in any order, and a palette that reshuffles on
            # every keystroke feels broken even though it is correct.
            .order_by(
                sa.desc(combined.c.score),
                combined.c.type,
                combined.c.id,
            )
            .limit(limit)
        )

        result = await self._session.execute(statement)
        return result.all()


#: Entity type -> model, resolved here rather than imported from ``policies``
#: to keep this module free of the permission layer: the repository decides how
#: to search, never whether.
_MODEL: dict[SearchEntityType, Any] = {
    SearchEntityType.ACCOUNT: Account,
    SearchEntityType.CONTACT: Contact,
    SearchEntityType.LEAD: Lead,
    SearchEntityType.OPPORTUNITY: Opportunity,
}


__all__ = ["TS_CONFIG", "WORD_SIMILARITY_FLOOR", "SearchRepository"]
