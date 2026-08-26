"""Global CRM search (`P3-W20`), and the leakage it must not permit.

The functional half of this file is small. The security half is not, because
search is the endpoint where an authorization mistake is least visible: the
forbidden record is missing from the results either way, so a post-filtered
implementation looks exactly like a correctly filtered one until you measure
what *else* changed — the count, the ranking, the truncation flag.

So every positive is paired with its negative, and several tests assert on
things a naive implementation gets wrong while still hiding the record:

* ``test_a_hidden_record_does_not_consume_a_result_slot`` — post-filtering
  after ``LIMIT`` returns a short page; filtering inside it does not.
* ``test_ranking_is_unaffected_by_records_the_caller_cannot_see`` — a
  better-matching invisible record must not push a visible one down.
* ``test_truncation_reflects_only_visible_records`` — the "there is more" flag
  must count the caller's rows, not everybody's.

Risk R14. See ``app/products/crm/search/repository.py`` for why.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """A plain ``User`` of alpha: owner-only visibility, no ``VIEW_ALL``."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def other_rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """A second signed-in session, used to create records ``rep`` cannot see."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.manager.email, organization_id=alpha.organization_id)
    return session


def _search(session: ApiSession, query: str, **params: object) -> dict:
    response = session.get("/crm/search", params={"q": query, **params})
    assert response.status_code == 200, response.text
    result: dict = response.json()
    return result


def _titles(payload: dict) -> list[str]:
    return [hit["title"] for hit in payload["hits"]]


def _ids(payload: dict) -> set[str]:
    return {hit["id"] for hit in payload["hits"]}


def _stage_id(session: ApiSession, name: str) -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


# --- It finds things --------------------------------------------------------


def test_an_account_is_found_by_its_name(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Northwind Trading"})

    payload = _search(as_alpha_admin, "northwind")

    assert "Northwind Trading" in _titles(payload)


def test_a_contact_is_found_by_either_name_part(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post(
        "/crm/contacts", json={"first_name": "Priya", "last_name": "Venkatraman"}
    )

    assert "Priya Venkatraman" in _titles(_search(as_alpha_admin, "priya"))
    assert "Priya Venkatraman" in _titles(_search(as_alpha_admin, "venkatraman"))


def test_a_contact_is_found_by_email(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post(
        "/crm/contacts",
        json={"first_name": "Ravi", "last_name": "Menon", "email": "ravi@zephyr.example"},
    )

    assert "Ravi Menon" in _titles(_search(as_alpha_admin, "zephyr"))


def test_a_lead_is_found_by_company(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Ana", "last_name": "Costa", "company": "Halcyon Robotics"},
    )

    assert "Ana Costa" in _titles(_search(as_alpha_admin, "halcyon"))


def test_an_opportunity_is_found_and_labelled_with_its_stage(
    as_alpha_admin: ApiSession,
) -> None:
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Stage Co"}).json()
    as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Quarterly Renewal",
            "account_id": account["id"],
            "stage_id": _stage_id(as_alpha_admin, "Qualification"),
        },
    )

    payload = _search(as_alpha_admin, "renewal")
    hit = next(h for h in payload["hits"] if h["title"] == "Quarterly Renewal")

    assert hit["type"] == "OPPORTUNITY"
    #: The stage, not the account — an account name would answer CR09's open
    #: question about one-hop readability by accident.
    assert hit["subtitle"] == "Qualification"


def test_a_prefix_finds_a_record_full_text_search_alone_would_miss(
    as_alpha_admin: ApiSession,
) -> None:
    """The reason ``pg_trgm`` is here at all (doc 12).

    Lexemes match whole words, so "acm" is not a full-text match for "Acme".
    A command palette that only matched complete words would appear broken for
    every keystroke but the last.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Acme Manufacturing"})

    assert "Acme Manufacturing" in _titles(_search(as_alpha_admin, "acm"))


def test_a_typo_still_finds_the_record(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Cinnabar Logistics"})

    assert "Cinnabar Logistics" in _titles(_search(as_alpha_admin, "cinabar"))


def test_stemming_matches_a_different_inflection(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post(
        "/crm/accounts",
        json={"name": "Vantage Group", "description": "They manufacture turbines."},
    )

    assert "Vantage Group" in _titles(_search(as_alpha_admin, "manufacturing"))


def test_a_name_match_outranks_a_description_match(as_alpha_admin: ApiSession) -> None:
    """Weighting is the whole reason the vector is built with ``setweight``."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Turbine Dynamics"})
    as_alpha_admin.post(
        "/crm/accounts",
        json={"name": "Unrelated Holdings", "description": "A turbine reseller."},
    )

    titles = _titles(_search(as_alpha_admin, "turbine"))

    assert titles.index("Turbine Dynamics") < titles.index("Unrelated Holdings")


def test_results_are_grouped_by_type_and_agree_with_the_flat_list(
    as_alpha_admin: ApiSession,
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Meridian Systems"})
    as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Meridian", "last_name": "Prospect"},
    )

    payload = _search(as_alpha_admin, "meridian")
    grouped = {hit["id"] for group in payload["groups"] for hit in group["hits"]}

    assert grouped == _ids(payload)
    assert {group["type"] for group in payload["groups"]} <= set(payload["searched"])


# --- It does not find things it should not ----------------------------------


def test_a_soft_deleted_record_is_not_a_result(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post("/crm/accounts", json={"name": "Ephemeral Ltd"}).json()
    assert "Ephemeral Ltd" in _titles(_search(as_alpha_admin, "ephemeral"))

    as_alpha_admin.delete(f"/crm/accounts/{created['id']}")

    assert "Ephemeral Ltd" not in _titles(_search(as_alpha_admin, "ephemeral"))


def test_another_tenants_records_are_never_returned(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    """RLS plus the explicit organization filter, from the caller's side."""
    beta_session = ApiSession(client, integration_settings.api_prefix)
    beta_session.login(beta.admin.email, organization_id=beta.organization_id)
    beta_session.post("/crm/accounts", json={"name": "Betaware Holdings"})

    assert _search(as_alpha_admin, "betaware")["hits"] == []


def test_an_unauthenticated_caller_is_refused(client: TestClient) -> None:
    assert client.get("/api/v1/crm/search", params={"q": "anything"}).status_code == 401


def test_a_query_shorter_than_two_characters_returns_nothing(
    as_alpha_admin: ApiSession,
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Quorum"})

    assert _search(as_alpha_admin, "q")["hits"] == []


def test_punctuation_only_query_is_answered_not_crashed(
    as_alpha_admin: ApiSession,
) -> None:
    """``websearch_to_tsquery`` parses user input, so nothing here can be
    malformed — but an empty tsquery must still produce an empty result rather
    than an error or a match-everything."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Symbol Co"})

    assert _search(as_alpha_admin, "!!!")["hits"] == []


# --- Permission filtering: which entity types are searched at all -----------


def test_searched_reports_the_types_the_caller_holds_view_on(
    rep: ApiSession,
) -> None:
    """A plain ``User`` holds ``VIEW`` on all four, so all four are searched.

    The *narrowing* case — a caller holding ``VIEW`` on some types and not
    others — has no fixture here, because the three seeded roles all hold
    ``VIEW`` on every CRM module and there is no create-role endpoint to build
    a fourth. It is covered where the logic actually lives, in
    ``tests/unit/test_search_permissions.py``, against a synthetic principal.
    """
    payload = _search(rep, "anything")

    assert set(payload["searched"]) == {"ACCOUNT", "CONTACT", "LEAD", "OPPORTUNITY"}


def test_the_types_parameter_can_only_narrow(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Solitary Account"})
    as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Solitary", "last_name": "Lead"}
    )

    payload = _search(as_alpha_admin, "solitary", types=["ACCOUNT"])

    assert payload["searched"] == ["ACCOUNT"]
    assert {hit["type"] for hit in payload["hits"]} == {"ACCOUNT"}


# --- Permission filtering: which rows, within a permitted type --------------


def test_a_rep_does_not_find_a_colleagues_record(
    rep: ApiSession, other_rep: ApiSession
) -> None:
    """The core record-level assertion, through search rather than a list."""
    other_rep.post("/crm/accounts", json={"name": "Sequestered Holdings"})

    assert _search(rep, "sequestered")["hits"] == []


def test_a_rep_finds_their_own_record(rep: ApiSession) -> None:
    """Paired with the test above: proves the query is not simply empty."""
    rep.post("/crm/accounts", json={"name": "Sequestered Holdings"})

    assert "Sequestered Holdings" in _titles(_search(rep, "sequestered"))


def test_a_manager_reading_across_owners_finds_the_same_record(
    rep: ApiSession, other_rep: ApiSession
) -> None:
    """``VIEW_ALL`` widens search exactly as it widens a list."""
    rep.post("/crm/accounts", json={"name": "Sequestered Holdings"})

    assert "Sequestered Holdings" in _titles(_search(other_rep, "sequestered"))


def test_a_partial_term_does_not_reveal_a_record_the_caller_cannot_see(
    rep: ApiSession, other_rep: ApiSession
) -> None:
    """The trigram branch must be filtered too.

    Easy to get wrong: the full-text branch gets the visibility predicate and
    the fuzzy branch, added later, is left as an ``OR`` outside it. Then a
    prefix search walks straight past record-level authorization.
    """
    other_rep.post("/crm/accounts", json={"name": "Palisade Ventures"})

    for fragment in ("pali", "palisad", "palisde"):
        assert _search(rep, fragment)["hits"] == [], fragment


def test_every_entity_type_is_filtered_not_just_accounts(
    rep: ApiSession, other_rep: ApiSession
) -> None:
    """One branch per type means four chances to forget the predicate."""
    account = other_rep.post("/crm/accounts", json={"name": "Covert Holdings"}).json()
    other_rep.post(
        "/crm/contacts",
        json={"first_name": "Covert", "last_name": "Person"},
    )
    other_rep.post("/crm/leads", json={"first_name": "Covert", "last_name": "Lead"})
    other_rep.post(
        "/crm/opportunities",
        json={
            "name": "Covert Deal",
            "account_id": account["id"],
            "stage_id": _stage_id(other_rep, "Qualification"),
        },
    )

    assert _search(rep, "covert")["hits"] == []
    #: Positive control: the same query finds all four for somebody who may
    #: read them, so the assertion above is about permission and not about the
    #: records failing to be indexed.
    assert len(_search(other_rep, "covert")["hits"]) == 4


# --- Leakage through the shape of the response ------------------------------


def test_a_hidden_record_does_not_consume_a_result_slot(
    rep: ApiSession, other_rep: ApiSession
) -> None:
    """Post-filtering after ``LIMIT`` fails this and hides the record anyway.

    Five matches exist; three belong to the caller. Asking for three must
    return three. An implementation that ranks all five, takes three, then
    drops the two it may not show returns one.
    """
    for index in range(2):
        other_rep.post("/crm/accounts", json={"name": f"Cobalt Hidden {index}"})
    for index in range(3):
        rep.post("/crm/accounts", json={"name": f"Cobalt Mine {index}"})

    payload = _search(rep, "cobalt", limit=3)

    assert len(payload["hits"]) == 3
    assert all("Mine" in title for title in _titles(payload))


def test_ranking_is_unaffected_by_records_the_caller_cannot_see(
    rep: ApiSession, other_rep: ApiSession
) -> None:
    """A better-matching invisible record must not displace a visible one.

    The hidden account is an exact name match and would rank first for anyone
    who could see it. For this caller it must not exist at all — not appear,
    and not push their own record down the list.
    """
    other_rep.post("/crm/accounts", json={"name": "Tungsten"})
    rep.post("/crm/accounts", json={"name": "Tungsten Alloys Division"})

    payload = _search(rep, "tungsten")

    assert _titles(payload) == ["Tungsten Alloys Division"]


def test_truncation_reflects_only_visible_records(
    rep: ApiSession, other_rep: ApiSession
) -> None:
    """"There is more" must mean more *for you*.

    Two visible matches under a limit of two is not truncated, however many
    matching records the caller cannot read sit beside them.
    """
    for index in range(4):
        other_rep.post("/crm/accounts", json={"name": f"Basalt Hidden {index}"})
    for index in range(2):
        rep.post("/crm/accounts", json={"name": f"Basalt Visible {index}"})

    payload = _search(rep, "basalt", limit=2)

    assert len(payload["hits"]) == 2
    assert payload["truncated"] is False


def test_truncation_is_reported_when_the_caller_really_has_more(
    rep: ApiSession,
) -> None:
    """Paired with the test above, so ``truncated`` is not simply always
    false."""
    for index in range(4):
        rep.post("/crm/accounts", json={"name": f"Granite Visible {index}"})

    payload = _search(rep, "granite", limit=2)

    assert len(payload["hits"]) == 2
    assert payload["truncated"] is True


def test_the_limit_is_capped_regardless_of_what_is_asked_for(
    as_alpha_admin: ApiSession,
) -> None:
    """Search is navigation, not export."""
    response = as_alpha_admin.get("/crm/search", params={"q": "anything", "limit": 5000})

    assert response.status_code == 422
