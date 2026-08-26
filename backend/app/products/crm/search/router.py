"""HTTP route for global CRM search (doc 11: ``GET /crm/search?q=``).

**This is the one CRM route not gated by ``require_permission``, and the
reason matters.** Doc 11 specifies "authenticated + entity permissions":
search spans four modules, and which of them a caller may search is the
*answer*, not the precondition. Gating on any single module's ``VIEW`` would
either lock out a caller who can legitimately search the other three, or —
worse — let one unrelated grant open the endpoint for someone who then relies
on the query to keep them out.

**On the ``types`` parameter.** Doc 10 illustrates it as
``types=account,contact``. It is implemented as a repeated parameter of
upper-case enum values — ``?types=ACCOUNT&types=CONTACT`` — which is what
FastAPI parses into a list natively, and what every other enum on this API
already looks like on the wire (``status=QUALIFIED``,
``entity_type=ACCOUNT``). A comma-joined string would arrive as one
unparseable value. The doc's snippet is illustrative rather than a contract;
no client exists that sends the other form.

So it takes :data:`~app.platform.auth.dependencies.PermissionedPrincipal`,
which proves authentication and organization membership and loads the
permission snapshot without asserting any part of it. The authorization
decision moves into the query, where
:class:`~app.products.crm.search.repository.SearchRepository` makes it — which
is only safe because the service actually makes one. Wiring this dependency to
a handler that reads without consulting the snapshot would be an unauthenticated
read wearing a login.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.database import DbSession
from app.platform.auth.dependencies import PermissionedPrincipal
from app.products.crm.search.schemas import SearchEntityType, SearchResults
from app.products.crm.search.service import DEFAULT_LIMIT, MAX_LIMIT, SearchService

router = APIRouter()


def get_service(session: DbSession) -> SearchService:
    return SearchService(session)


ServiceDep = Annotated[SearchService, Depends(get_service)]


@router.get("", response_model=SearchResults)
async def search_crm(
    principal: PermissionedPrincipal,
    service: ServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=255, description="Search text")],
    types: Annotated[
        list[SearchEntityType] | None,
        Query(description="Entity types to search. Omit to search everything permitted."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> SearchResults:
    """Search accounts, contacts, leads and opportunities at once.

    Results contain only records the caller is authorized to open, and the
    filtering happens inside the ranking query rather than after it — so the
    ranking, the count and the truncation flag are all computed over the
    caller's own slice of the data. A record they cannot see does not displace
    one they can.

    An empty result is returned for a query shorter than two characters and
    for a caller holding no CRM ``VIEW`` permission at all. Neither is an
    error: a search box that 403s tells the person there is something there.
    """
    return await service.search(principal, query=q, types=types, limit=limit)


__all__ = ["router"]
