"""Which entity types a caller may search (`P3-W20-BE-04`, first half).

Search enforces permission twice, and the two halves fail differently.

*Which types are searched at all* is decided here, by
:meth:`SearchService.searchable_types`, from the caller's permission snapshot.
A type the caller cannot ``VIEW`` contributes no branch to the query, so it
cannot influence ranking, the limit, or the truncation flag — it is absent
rather than filtered.

*Which rows within a permitted type* is `RecordVisibility`, applied inside the
query and covered by ``tests/integration/test_search.py`` against real rows.

This half is unit-tested rather than integration-tested for a practical
reason: the three seeded system roles all hold ``VIEW`` on every CRM module,
and there is no create-role endpoint, so the interesting case — ``VIEW`` on
some modules and not others — cannot be built through the API. It is pure
logic over a principal, so a synthetic one proves it exactly.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest

from app.platform.auth.dependencies import Principal
from app.products.crm.search.schemas import SearchEntityType
from app.products.crm.search.service import SearchService

ALL_TYPES = list(SearchEntityType)


def _principal(*permissions: str) -> Principal:
    """A principal holding exactly ``permissions`` and nothing else.

    ``user`` is never dereferenced by ``searchable_types`` — only
    ``has_permission`` is — so a placeholder keeps the test about permissions
    rather than about constructing an ORM object.
    """
    return Principal(
        user=cast("Any", object()),
        organization_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        permissions=frozenset(permissions),
    )


@pytest.fixture
def service() -> SearchService:
    # The session is never touched: ``searchable_types`` runs no query.
    return SearchService(cast("Any", None))


def test_a_caller_with_every_view_searches_every_type(service: SearchService) -> None:
    principal = _principal(
        "accounts.VIEW", "contacts.VIEW", "leads.VIEW", "opportunities.VIEW"
    )

    assert service.searchable_types(principal, None) == ALL_TYPES


def test_a_type_without_view_is_not_searched(service: SearchService) -> None:
    """The case the integration suite cannot build, and the one that matters.

    A caller who may read accounts but not leads must not get a leads branch —
    not an empty one, none — or leads influence the ranking and the limit of a
    result set they are not entitled to.
    """
    principal = _principal("accounts.VIEW", "contacts.VIEW")

    assert service.searchable_types(principal, None) == [
        SearchEntityType.ACCOUNT,
        SearchEntityType.CONTACT,
    ]


def test_a_caller_with_no_crm_view_searches_nothing(service: SearchService) -> None:
    """Empty, not an error: a search box that 403s says something is there."""
    assert service.searchable_types(_principal(), None) == []


def test_another_action_on_the_module_does_not_grant_search(
    service: SearchService,
) -> None:
    """``EDIT`` without ``VIEW`` is a nonsense grant, but roles are data.

    Search must key on ``VIEW`` specifically rather than on "holds anything on
    this module", or a badly-built custom role opens a read path.
    """
    principal = _principal("leads.EDIT", "leads.CREATE", "leads.DELETE")

    assert service.searchable_types(principal, None) == []


def test_view_all_does_not_stand_in_for_view(service: SearchService) -> None:
    """``VIEW_ALL`` widens *which rows*, it does not grant the read itself.

    The seeded roles always grant both, so nothing in production distinguishes
    them — which is exactly why this is pinned: the day a custom role grants
    only ``VIEW_ALL``, search must not treat it as permission to read.
    """
    principal = _principal("accounts.VIEW_ALL", "accounts.VIEW_TEAM")

    assert service.searchable_types(principal, None) == []


@pytest.mark.parametrize(
    ("requested", "expected"),
    [
        ([SearchEntityType.ACCOUNT], [SearchEntityType.ACCOUNT]),
        (
            [SearchEntityType.ACCOUNT, SearchEntityType.LEAD],
            [SearchEntityType.ACCOUNT],
        ),
        ([SearchEntityType.LEAD], []),
        (None, [SearchEntityType.ACCOUNT]),
    ],
)
def test_the_types_parameter_can_only_narrow(
    service: SearchService,
    requested: list[SearchEntityType] | None,
    expected: list[SearchEntityType],
) -> None:
    """Asking for a type you cannot view drops it; it never grants it.

    The client's preference is intersected with the permitted set, in that
    order. Reversed, ``types=LEAD`` would be an instruction rather than a
    filter.
    """
    principal = _principal("accounts.VIEW")

    assert service.searchable_types(principal, requested) == expected


def test_the_result_is_ordered_by_the_enum_not_by_the_request(
    service: SearchService,
) -> None:
    """Stable ordering, so ``searched`` and the response groups agree.

    Echoing the client's ordering back would make two requests differing only
    in parameter order return differently ordered groups for identical data.
    """
    principal = _principal(
        "accounts.VIEW", "contacts.VIEW", "leads.VIEW", "opportunities.VIEW"
    )
    reversed_request = list(reversed(ALL_TYPES))

    assert service.searchable_types(principal, reversed_request) == ALL_TYPES
