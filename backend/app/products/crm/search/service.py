"""Global CRM search — the module's public interface (`P3-W20-BE-03/04`).

The service does three things and deliberately not a fourth.

1. Decides **which entity types this caller may search**, from the permission
   snapshot on the principal.
2. Resolves **record-level visibility per type**, separately, because a custom
   role may read across owners in one module and only its own in another.
3. Hands both to the repository, which builds one query with all of it inside.

The fourth thing — filtering results after they come back — is absent on
purpose. There is nothing to filter: a row that reached this layer was already
authorized by the query that produced it. Any post-filter added here would be
either dead code or an admission that the query is wrong, and the second is
the failure mode risk R14 describes.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.search.policies import MODEL_FOR_TYPE, MODULE_FOR_TYPE
from app.products.crm.search.repository import SearchRepository
from app.products.crm.search.schemas import (
    SearchEntityType,
    SearchGroup,
    SearchHit,
    SearchResults,
)
from app.products.crm.shared.visibility import RecordVisibility

logger = structlog.get_logger(__name__)

#: Shortest query worth running. One or two characters match most of the
#: database through trigrams and rank meaninglessly, so a palette that fired on
#: the first keystroke would return noise and pay for it in latency.
MIN_QUERY_LENGTH = 2

#: Hard ceiling on rows returned, whatever the caller asks for. Search is a
#: navigation aid, not an export: somebody wanting every matching lead should
#: use the list endpoint, which paginates and is the place export limits are
#: enforced.
MAX_LIMIT = 50
DEFAULT_LIMIT = 20


class SearchService:
    """Cross-entity search, scoped to what the caller may read."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = SearchRepository(session)

    def searchable_types(
        self, principal: Principal, requested: Sequence[SearchEntityType] | None
    ) -> list[SearchEntityType]:
        """Types the caller may search, narrowed by ``requested`` if given.

        Permission is checked against the caller's snapshot, never against the
        request: asking for ``types=lead`` without ``leads.VIEW`` drops leads
        rather than granting them. The intersection is taken in that order —
        permitted first, then the client's preference — so the parameter can
        only ever narrow.
        """
        wanted = set(requested) if requested else set(SearchEntityType)
        return [
            entity
            for entity in SearchEntityType
            if entity in wanted
            and principal.has_permission(MODULE_FOR_TYPE[entity], PermissionAction.VIEW)
        ]

    async def search(
        self,
        principal: Principal,
        *,
        query: str,
        types: Sequence[SearchEntityType] | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> SearchResults:
        """Search the CRM for ``query``.

        Returns an empty result — not an error — for a query too short to be
        meaningful and for a caller who may search nothing. Both are ordinary
        states of a search box, and a 403 on the second would tell an
        unprivileged caller that there is something there to be refused.
        """
        query = query.strip()
        permitted = self.searchable_types(principal, types)

        if len(query) < MIN_QUERY_LENGTH or not permitted:
            return SearchResults(query=query, searched=permitted)

        limit = max(1, min(limit, MAX_LIMIT))

        branches: list[tuple[SearchEntityType, ColumnElement[bool] | None]] = [
            (entity, self._visibility(principal, entity)) for entity in permitted
        ]

        # One more row than asked for, purely to tell "exactly full" from
        # "there is more" without a second COUNT over data the caller may not
        # be able to see anyway.
        rows = await self._repository.search(
            organization_id=principal.organization_id,
            query=query,
            branches=branches,
            limit=limit + 1,
        )

        truncated = len(rows) > limit
        hits = [
            SearchHit(
                type=SearchEntityType(row.type),
                id=uuid.UUID(str(row.id)),
                title=(row.title or "").strip() or "(untitled)",
                subtitle=(row.subtitle or None),
                score=float(row.score),
            )
            for row in rows[:limit]
        ]

        logger.info(
            "crm_search",
            organization_id=str(principal.organization_id),
            types=[entity.value for entity in permitted],
            hits=len(hits),
            truncated=truncated,
        )

        return SearchResults(
            query=query,
            hits=hits,
            groups=_group(hits),
            searched=permitted,
            truncated=truncated,
        )

    @staticmethod
    def _visibility(
        principal: Principal, entity: SearchEntityType
    ) -> ColumnElement[bool] | None:
        """The record-level predicate for one entity type, or ``None``.

        ``None`` means the caller reads across owners, and the repository then
        adds no predicate at all — the same statement it would have built
        before record-level visibility existed.
        """
        visibility = RecordVisibility.for_module(principal, MODULE_FOR_TYPE[entity])
        return visibility.filter_for(MODEL_FOR_TYPE[entity])


def _group(hits: Sequence[SearchHit]) -> list[SearchGroup]:
    """Partition hits by type, preserving rank order within each group.

    Built from the returned hits rather than by a second query, so the grouped
    and flat views cannot disagree — and so grouping costs nothing beyond the
    pass it takes.
    """
    grouped: dict[SearchEntityType, list[SearchHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.type, []).append(hit)
    return [
        SearchGroup(type=entity, hits=grouped[entity])
        for entity in SearchEntityType
        if entity in grouped
    ]


__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "MIN_QUERY_LENGTH", "SearchService"]
