"""Market Insights end to end, against real PostgreSQL and real RBAC.

The AI provider is the one thing stubbed. Everything else — authentication,
the permission catalogue, RLS, record-level visibility, the audit trail — is
the real implementation, because those are the guarantees under test and a
mock of them would prove nothing.

The stub is not a shortcut around the model call: it is what makes these tests
assert on *what was sent* (does the pinned prompt version reach the request?
is CRM context included only when permitted?) rather than on what a model
happened to reply.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import Settings
from app.core.database import DbSession
from app.core.exceptions import AppError
from app.platform.ai.provider import ResearchResult, ResearchSource
from app.platform.ai.service import (
    DEFAULT_MARKET_INSIGHTS_PROMPT,
    AiGatewayService,
    AiPromptService,
)
from app.products.crm.market_insights import router as market_insights_router
from app.products.crm.market_insights.service import MarketInsightService
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration

MARKET_INSIGHTS = "/crm/market-insights"


# ---------------------------------------------------------------------------
# A provider that records what it was asked
# ---------------------------------------------------------------------------


@dataclass
class StubProvider:
    """Stands in for Claude. Records every request; replies from a script."""

    text: str = "## Company Overview\n\nA chemicals manufacturer.\n\n## Competitors\n\nSeveral."
    sources: tuple[ResearchSource, ...] = ()
    truncated: bool = False
    #: When set, ``run`` raises it instead of answering.
    failure: AppError | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def run(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        web_search: bool = True,
    ) -> ResearchResult:
        self.calls.append(
            {"system": system, "messages": [dict(m) for m in messages], "web_search": web_search}
        )
        if self.failure is not None:
            raise self.failure
        return ResearchResult(
            text=self.text,
            sources=self.sources,
            model="claude-opus-5",
            stop_reason="end_turn",
            search_count=len(self.sources),
            truncated=self.truncated,
        )

    @property
    def last_system(self) -> str:
        return self.calls[-1]["system"]


@pytest.fixture
def provider() -> StubProvider:
    return StubProvider()


@pytest.fixture
def api_app(integration_settings: Settings, provider: StubProvider) -> FastAPI:
    """The real application with only the model call replaced.

    Overrides the router's service factory rather than patching a module
    global, so the substitution is scoped to this app instance and every other
    dependency — session, principal, permissions — still resolves normally.
    """
    app = create_app(integration_settings)

    def _service(session: DbSession) -> MarketInsightService:
        return MarketInsightService(
            session,
            gateway=AiGatewayService(
                settings=integration_settings,
                session=session,
                redis=None,
                provider=provider,
            ),
            prompts=AiPromptService(session),
            # The real factory, not a stub: recording a failed turn out of band
            # is behaviour under test, so it has to run against real
            # transactions rather than be substituted away.
            session_factory=app.state.session_factory,
        )

    app.dependency_overrides[market_insights_router.get_service] = _service
    return app


@pytest.fixture
def client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as test_client:
        yield test_client


def _session(client: TestClient, settings: Settings, email: str, org: uuid.UUID) -> ApiSession:
    session = ApiSession(client, settings.api_prefix)
    session.login(email, organization_id=org)
    return session


# The conftest's ``as_alpha_admin`` and ``as_alpha_member`` both log in on the
# *same* ApiSession, so a test that names two of them would silently run as
# whichever authenticated last. Every fixture below is an independent session,
# which is what lets one test hold two identities at once.


@pytest.fixture
def alpha_admin(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> ApiSession:
    return _session(client, integration_settings, alpha.admin.email, alpha.organization_id)


@pytest.fixture
def alpha_manager(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> ApiSession:
    return _session(client, integration_settings, alpha.manager.email, alpha.organization_id)


@pytest.fixture
def alpha_member(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> ApiSession:
    return _session(client, integration_settings, alpha.member.email, alpha.organization_id)


@pytest.fixture
def beta_admin(
    client: TestClient, integration_settings: Settings, beta: Tenant
) -> ApiSession:
    return _session(client, integration_settings, beta.admin.email, beta.organization_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def start(api: ApiSession, company: str, account_id: uuid.UUID | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"company_name": company}
    if account_id is not None:
        payload["account_id"] = str(account_id)
    response = api.post(MARKET_INSIGHTS, json=payload)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def make_account(api: ApiSession, name: str, **fields: Any) -> dict[str, Any]:
    response = api.post("/crm/accounts", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    account: dict[str, Any] = response.json()
    return account


# ---------------------------------------------------------------------------
# Researching a company
# ---------------------------------------------------------------------------


def test_an_external_company_needs_no_crm_record(alpha_member: ApiSession) -> None:
    """§3B: the whole point — research without creating an account first."""
    body = start(alpha_member, "Apcotex Industries")

    assert body["company_name"] == "Apcotex Industries"
    assert body["account_id"] is None
    assert body["status"] == "READY"
    assert body["used_crm_context"] is False


def test_the_report_is_stored_as_the_first_assistant_message(
    alpha_member: ApiSession,
) -> None:
    body = start(alpha_member, "Apcotex Industries")

    roles = [message["role"] for message in body["messages"]]
    assert roles == ["USER", "ASSISTANT"]
    assert "## Company Overview" in body["messages"][1]["content"]


def test_a_crm_account_supplies_context_to_the_research(
    alpha_admin: ApiSession, provider: StubProvider
) -> None:
    """§7: an account's own record reaches the model, labelled as CRM data."""
    account = make_account(alpha_admin, "Zephyr Chemicals", industry="Chemicals")

    body = start(alpha_admin, "Zephyr Chemicals", uuid.UUID(account["id"]))

    assert body["account_id"] == account["id"]
    assert body["used_crm_context"] is True
    assert "Industry: Chemicals" in provider.last_system
    assert "internal CRM data" in provider.last_system


def test_an_account_from_another_tenant_is_not_reachable(
    alpha_member: ApiSession, beta_admin: ApiSession
) -> None:
    """Insecure direct object reference: another tenant's id must 404."""
    foreign = make_account(beta_admin, "Beta Only Ltd")

    response = alpha_member.post(
        MARKET_INSIGHTS,
        json={"company_name": "Beta Only Ltd", "account_id": foreign["id"]},
    )

    assert response.status_code == 404


def test_sources_are_persisted_with_their_retrieval_date(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    """§17: what is shown as evidence is what the tool returned."""
    provider.sources = (
        ResearchSource(title="Annual report", url="https://a.example/ar", cited=True),
        ResearchSource(title="News", url="https://b.example/news", page_age="3 days ago"),
    )

    body = start(alpha_member, "Apcotex Industries")

    urls = {source["url"] for source in body["sources"]}
    assert urls == {"https://a.example/ar", "https://b.example/news"}
    assert any(source["cited"] for source in body["sources"])
    assert all(source["retrieved_at"] for source in body["sources"])


def test_a_provider_failure_is_kept_in_history_with_its_reason(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    """§15 "research failure": the attempt survives so it can be retried."""
    from app.platform.ai.provider import AiTemporarilyUnavailableError

    provider.failure = AiTemporarilyUnavailableError()

    response = alpha_member.post(
        MARKET_INSIGHTS, json={"company_name": "Doomed Industries"}
    )
    assert response.status_code == 503

    listing = alpha_member.get(MARKET_INSIGHTS)
    rows = listing.json()["data"]
    assert [row["company_name"] for row in rows] == ["Doomed Industries"]
    assert rows[0]["status"] == "FAILED"
    assert rows[0]["error_code"] == "ai_temporarily_unavailable"


@pytest.mark.parametrize("blank", ["", "   ", "!!!", "---"])
def test_a_name_with_no_letters_or_digits_is_rejected(
    alpha_member: ApiSession, blank: str
) -> None:
    """§20 "invalid company name" / "empty search"."""
    response = alpha_member.post(MARKET_INSIGHTS, json={"company_name": blank})

    assert response.status_code == 422


def test_a_very_long_company_name_is_rejected_rather_than_truncated(
    alpha_member: ApiSession,
) -> None:
    """§20 "very long company names" — bounded at the contract, not the column."""
    response = alpha_member.post(MARKET_INSIGHTS, json={"company_name": "A" * 500})

    assert response.status_code == 422


def test_whitespace_in_a_company_name_is_collapsed(alpha_member: ApiSession) -> None:
    body = start(alpha_member, "  Apcotex   Industries \n Ltd  ")

    assert body["company_name"] == "Apcotex Industries Ltd"


# ---------------------------------------------------------------------------
# Continuing the conversation (§6)
# ---------------------------------------------------------------------------


def test_a_follow_up_keeps_the_company_without_it_being_restated(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    session = start(alpha_member, "Apcotex Industries")

    response = alpha_member.post(
        f"{MARKET_INSIGHTS}/{session['id']}/messages",
        json={"question": "Who are their biggest competitors?"},
    )
    assert response.status_code == 200, response.text

    # The company reaches the model from the session, not from the question —
    # which is what lets the user stop repeating it (§6).
    assert "Apcotex Industries" in provider.last_system

    replayed = provider.calls[-1]["messages"]
    assert replayed[-1]["content"] == "Who are their biggest competitors?"
    # The opening report is replayed too, so the follow-up answers from the
    # research rather than from nothing.
    assert any("## Company Overview" in str(turn["content"]) for turn in replayed)


def test_a_follow_up_is_appended_to_the_stored_conversation(
    alpha_member: ApiSession,
) -> None:
    session = start(alpha_member, "Apcotex Industries")

    body = alpha_member.post(
        f"{MARKET_INSIGHTS}/{session['id']}/messages",
        json={"question": "Summarise this in 5 points."},
    ).json()

    assert [m["role"] for m in body["messages"]] == [
        "USER",
        "ASSISTANT",
        "USER",
        "ASSISTANT",
    ]
    assert [m["sequence"] for m in body["messages"]] == [1, 2, 3, 4]


def test_a_source_already_seen_is_not_stored_twice(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    """A follow-up commonly re-reads a page the report already cited."""
    provider.sources = (ResearchSource(title="Annual report", url="https://a.example/ar"),)
    session = start(alpha_member, "Apcotex Industries")

    body = alpha_member.post(
        f"{MARKET_INSIGHTS}/{session['id']}/messages",
        json={"question": "Anything else?"},
    ).json()

    assert len(body["sources"]) == 1


def test_an_empty_question_is_rejected(alpha_member: ApiSession) -> None:
    session = start(alpha_member, "Apcotex Industries")

    response = alpha_member.post(
        f"{MARKET_INSIGHTS}/{session['id']}/messages", json={"question": "   "}
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# History (§9, §10)
# ---------------------------------------------------------------------------


def test_reopening_a_session_restores_the_conversation_rather_than_restarting(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    """§10: opening history must not start a fresh conversation."""
    session = start(alpha_member, "Apcotex Industries")
    alpha_member.post(
        f"{MARKET_INSIGHTS}/{session['id']}/messages", json={"question": "And competitors?"}
    )
    calls_before = len(provider.calls)

    reopened = alpha_member.get(f"{MARKET_INSIGHTS}/{session['id']}")

    assert reopened.status_code == 200
    assert len(reopened.json()["messages"]) == 4
    # No model call was made just to read it back.
    assert len(provider.calls) == calls_before


def test_history_can_be_searched_by_company_and_by_title(
    alpha_member: ApiSession,
) -> None:
    start(alpha_member, "Apcotex Industries")
    tata = start(alpha_member, "Tata Chemicals")
    alpha_member.patch(
        f"{MARKET_INSIGHTS}/{tata['id']}", json={"title": "Competitive Analysis"}
    )

    by_company = alpha_member.get(f"{MARKET_INSIGHTS}?search=apcotex").json()["data"]
    by_title = alpha_member.get(f"{MARKET_INSIGHTS}?search=competitive").json()["data"]

    assert [row["company_name"] for row in by_company] == ["Apcotex Industries"]
    assert [row["company_name"] for row in by_title] == ["Tata Chemicals"]


def test_a_session_can_be_renamed_without_changing_the_company(
    alpha_member: ApiSession,
) -> None:
    session = start(alpha_member, "Apcotex Industries")

    renamed = alpha_member.patch(
        f"{MARKET_INSIGHTS}/{session['id']}", json={"title": "Market Research"}
    ).json()

    assert renamed["title"] == "Market Research"
    assert renamed["company_name"] == "Apcotex Industries"


def test_an_archived_session_leaves_the_list(alpha_manager: ApiSession) -> None:
    session = start(alpha_manager, "Apcotex Industries")

    assert alpha_manager.delete(f"{MARKET_INSIGHTS}/{session['id']}").status_code == 204
    assert alpha_manager.get(MARKET_INSIGHTS).json()["data"] == []
    assert alpha_manager.get(f"{MARKET_INSIGHTS}/{session['id']}").status_code == 404


def test_a_plain_user_cannot_archive_research(alpha_member: ApiSession) -> None:
    """``User`` holds VIEW/CREATE/EDIT and not DELETE, as in every CRM module.

    Worth pinning rather than assuming: research is the one module where
    "it is mine, so I can delete it" would have been a tempting exception.
    """
    session = start(alpha_member, "Apcotex Industries")

    assert alpha_member.delete(f"{MARKET_INSIGHTS}/{session['id']}").status_code == 403


# ---------------------------------------------------------------------------
# Adding an external company to the CRM (§8)
# ---------------------------------------------------------------------------


def test_linking_an_account_preserves_the_research(alpha_admin: ApiSession) -> None:
    session = start(alpha_admin, "Newco Industries")
    account = make_account(alpha_admin, "Newco Industries")

    linked = alpha_admin.post(
        f"{MARKET_INSIGHTS}/{session['id']}/account", json={"account_id": account["id"]}
    )
    assert linked.status_code == 200

    reopened = alpha_admin.get(f"{MARKET_INSIGHTS}/{session['id']}").json()
    assert reopened["account_id"] == account["id"]
    assert len(reopened["messages"]) == 2


def test_a_session_cannot_be_relinked_to_a_second_account(
    alpha_admin: ApiSession,
) -> None:
    session = start(alpha_admin, "Newco Industries")
    first = make_account(alpha_admin, "Newco Industries")
    second = make_account(alpha_admin, "Newco Holdings")

    alpha_admin.post(
        f"{MARKET_INSIGHTS}/{session['id']}/account", json={"account_id": first["id"]}
    )
    response = alpha_admin.post(
        f"{MARKET_INSIGHTS}/{session['id']}/account", json={"account_id": second["id"]}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_already_linked"


def test_linking_to_another_tenants_account_is_a_404(
    alpha_admin: ApiSession, beta_admin: ApiSession
) -> None:
    session = start(alpha_admin, "Newco Industries")
    foreign = make_account(beta_admin, "Beta Newco")

    response = alpha_admin.post(
        f"{MARKET_INSIGHTS}/{session['id']}/account", json={"account_id": foreign["id"]}
    )

    assert response.status_code == 404


def test_the_duplicate_account_warning_still_applies_to_this_flow(
    alpha_admin: ApiSession,
) -> None:
    """§8 "respect existing validation and duplicate detection".

    Add-to-CRM goes through the ordinary accounts endpoint, so it inherits the
    duplicate-name warning rather than bypassing it.
    """
    make_account(alpha_admin, "Newco Industries")

    response = alpha_admin.post("/crm/accounts", json={"name": "Newco Industries"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "duplicate_account"


# ---------------------------------------------------------------------------
# Prompt configuration and versioning (§11, §12)
# ---------------------------------------------------------------------------


def test_the_configured_prompt_is_what_new_research_runs_under(
    alpha_admin: ApiSession, provider: StubProvider
) -> None:
    alpha_admin.put(
        "/ai/prompts/market_insights",
        json={"prompt": "ONLY-REGULATORY-RISK", "change_note": "narrowed"},
    )

    start(alpha_admin, "Apcotex Industries")

    assert "ONLY-REGULATORY-RISK" in provider.last_system


def test_editing_the_prompt_does_not_alter_completed_research(
    alpha_admin: ApiSession, provider: StubProvider
) -> None:
    """§12, the property the whole version table exists for."""
    first = start(alpha_admin, "Apcotex Industries")
    original_report = first["messages"][1]["content"]
    original_version = first["prompt_version"]

    alpha_admin.put(
        "/ai/prompts/market_insights", json={"prompt": "COMPLETELY-DIFFERENT-BRIEF"}
    )

    reopened = alpha_admin.get(f"{MARKET_INSIGHTS}/{first['id']}").json()
    assert reopened["messages"][1]["content"] == original_report
    assert reopened["prompt_version"] == original_version

    second = start(alpha_admin, "Tata Chemicals")
    assert second["prompt_version"] == original_version + 1
    assert "COMPLETELY-DIFFERENT-BRIEF" in provider.last_system


def test_a_follow_up_on_old_research_uses_the_prompt_it_ran_under(
    alpha_admin: ApiSession, provider: StubProvider
) -> None:
    """A historical session stays continuable *and* internally consistent."""
    session = start(alpha_admin, "Apcotex Industries")
    alpha_admin.put("/ai/prompts/market_insights", json={"prompt": "NEW-BRIEF"})

    alpha_admin.post(
        f"{MARKET_INSIGHTS}/{session['id']}/messages", json={"question": "And competitors?"}
    )

    assert "NEW-BRIEF" not in provider.last_system


def test_publishing_appends_a_version_rather_than_overwriting(
    alpha_admin: ApiSession,
) -> None:
    alpha_admin.get("/ai/prompts/market_insights")
    alpha_admin.put("/ai/prompts/market_insights", json={"prompt": "Second"})
    body = alpha_admin.put("/ai/prompts/market_insights", json={"prompt": "Third"}).json()

    assert body["active"]["version"] == 3
    assert body["active"]["prompt"] == "Third"
    assert [version["version"] for version in body["history"]] == [3, 2, 1]
    assert sum(1 for version in body["history"] if version["is_active"]) == 1


def test_the_default_prompt_is_published_on_first_read(alpha_admin: ApiSession) -> None:
    body = alpha_admin.get("/ai/prompts/market_insights").json()

    assert body["active"]["version"] == 1
    # Compared against the constant rather than against a phrase inside it: the
    # brief's wording is meant to be edited, and a test that names one of its
    # section headings fails on every rewrite while proving nothing about the
    # seeding this test is actually for.
    assert body["active"]["prompt"] == DEFAULT_MARKET_INSIGHTS_PROMPT.strip()


def test_an_unknown_prompt_key_is_a_404(alpha_admin: ApiSession) -> None:
    assert alpha_admin.get("/ai/prompts/not_a_prompt").status_code == 404


def test_an_empty_prompt_is_rejected(alpha_admin: ApiSession) -> None:
    response = alpha_admin.put("/ai/prompts/market_insights", json={"prompt": "   "})

    assert response.status_code == 422


def test_prompt_versions_do_not_leak_across_tenants(
    alpha_admin: ApiSession, beta_admin: ApiSession
) -> None:
    alpha_admin.put("/ai/prompts/market_insights", json={"prompt": "ALPHA-ONLY"})

    beta = beta_admin.get("/ai/prompts/market_insights").json()

    assert "ALPHA-ONLY" not in beta["active"]["prompt"]
    assert beta["active"]["version"] == 1


# ---------------------------------------------------------------------------
# Permissions and isolation (§13)
# ---------------------------------------------------------------------------


def test_prompt_configuration_is_administrator_only(alpha_member: ApiSession) -> None:
    """A sales user may research but may not reword what research does."""
    assert alpha_member.get("/ai/prompts/market_insights").status_code == 403
    assert (
        alpha_member.put(
            "/ai/prompts/market_insights", json={"prompt": "mine now"}
        ).status_code
        == 403
    )


def test_a_manager_cannot_configure_the_prompt_either(
    alpha_manager: ApiSession,
) -> None:
    """Manager holds every CRM permission and still does not hold ``ai.ADMIN``."""
    assert alpha_manager.get("/ai/prompts/market_insights").status_code == 403


def test_ai_status_is_readable_by_any_member(alpha_member: ApiSession) -> None:
    """The AI section needs it to choose between the feature and the empty state."""
    response = alpha_member.get("/ai/status")

    assert response.status_code == 200
    assert set(response.json()) == {"configured", "model"}


def test_ai_status_never_reveals_the_credential(alpha_admin: ApiSession) -> None:
    body = alpha_admin.get("/ai/status").text

    assert "sk-" not in body
    assert "api_key" not in body


def test_a_user_cannot_read_another_users_research(
    alpha_member: ApiSession, alpha_admin: ApiSession
) -> None:
    """§13: one person's research is not another's to read.

    A plain User holds ``market_insights.VIEW`` but not ``VIEW_ALL``, and the
    module is owner-scoped, so the Admin's session is invisible to them — on
    the list *and* on a direct fetch, which is what stops an id being guessed.
    """
    mine = start(alpha_member, "Member Research")
    theirs = start(alpha_admin, "Admin Research")

    ids = {row["id"] for row in alpha_member.get(MARKET_INSIGHTS).json()["data"]}

    assert mine["id"] in ids
    assert theirs["id"] not in ids
    assert alpha_member.get(f"{MARKET_INSIGHTS}/{theirs['id']}").status_code == 404


def test_a_manager_with_view_all_sees_the_teams_research(
    alpha_member: ApiSession, alpha_manager: ApiSession
) -> None:
    """The other half of the same rule: oversight still works.

    Manager holds ``market_insights.VIEW_ALL`` from the migration's grant, so
    the same owner scoping that hides a colleague's research from a rep does
    not hide it from their manager.
    """
    theirs = start(alpha_member, "Member Research")

    visible = alpha_manager.get(MARKET_INSIGHTS).json()["data"]

    assert theirs["id"] in {row["id"] for row in visible}


def test_research_does_not_cross_tenants(
    alpha_member: ApiSession, beta_admin: ApiSession
) -> None:
    alpha_session = start(alpha_member, "Apcotex Industries")

    assert beta_admin.get(MARKET_INSIGHTS).json()["data"] == []
    assert beta_admin.get(f"{MARKET_INSIGHTS}/{alpha_session['id']}").status_code == 404


def test_an_unauthenticated_request_is_rejected(client: TestClient) -> None:
    response = client.get(f"/api/v1{MARKET_INSIGHTS}")

    assert response.status_code == 401


def test_crm_context_is_limited_to_what_the_caller_may_read(
    alpha_admin: ApiSession, alpha_member: ApiSession, provider: StubProvider
) -> None:
    """§7 "existing contacts where permitted".

    The member owns the account, so they can research it. The *contact* on it
    is owned by the Admin, and the member holds ``contacts.VIEW`` without
    ``VIEW_ALL`` — so it is outside their record visibility and must not reach
    the model just because they asked the AI instead of opening the record.
    """
    account = make_account(alpha_member, "Zephyr Chemicals")
    created = alpha_admin.post(
        "/crm/contacts",
        json={
            "first_name": "Ravi",
            "last_name": "AdminOwned",
            "account_id": account["id"],
        },
    )
    assert created.status_code == 201, created.text

    start(alpha_member, "Zephyr Chemicals", uuid.UUID(account["id"]))

    assert "AdminOwned" not in provider.last_system


def test_crm_context_includes_a_contact_the_caller_may_read(
    alpha_admin: ApiSession, provider: StubProvider
) -> None:
    """The other half: when the caller may read it, it is used (§7)."""
    account = make_account(alpha_admin, "Zephyr Chemicals")
    alpha_admin.post(
        "/crm/contacts",
        json={
            "first_name": "Ravi",
            "last_name": "Visible",
            "job_title": "Head of Procurement",
            "account_id": account["id"],
        },
    )

    start(alpha_admin, "Zephyr Chemicals", uuid.UUID(account["id"]))

    assert "Ravi Visible" in provider.last_system
    assert "Head of Procurement" in provider.last_system


def test_crm_context_never_carries_contact_email_or_phone(
    alpha_admin: ApiSession, provider: StubProvider
) -> None:
    """Personal contact details are not sent to a third-party API.

    The model does not need them to reason about an account, so they are left
    out — proximity is not a reason to transmit someone's phone number.
    """
    account = make_account(alpha_admin, "Zephyr Chemicals")
    alpha_admin.post(
        "/crm/contacts",
        json={
            "first_name": "Ravi",
            "last_name": "Visible",
            "email": "ravi@zephyr.example",
            "phone": "+441234567890",
            "account_id": account["id"],
        },
    )

    start(alpha_admin, "Zephyr Chemicals", uuid.UUID(account["id"]))

    assert "ravi@zephyr.example" not in provider.last_system
    assert "+441234567890" not in provider.last_system
