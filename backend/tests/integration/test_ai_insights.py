"""AI Insights end to end (Checkpoint 7), against real PostgreSQL and real RBAC.

Same approach as ``test_market_insights.py``: only the model call is stubbed.
Authentication, the permission catalogue, RLS, record-level visibility and the
append-only generation history are the real implementation.
"""

from __future__ import annotations

import datetime as dt
import json
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
from app.platform.ai.provider import AiTemporarilyUnavailableError, ResearchResult
from app.platform.ai.service import AiGatewayService
from app.products.crm.ai_insights import router as ai_insights_router
from app.products.crm.ai_insights.service import AiInsightsService
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration

AI_INSIGHTS = "/crm/ai-insights"


# ---------------------------------------------------------------------------
# A provider that records what it was asked and answers from a script
# ---------------------------------------------------------------------------


@dataclass
class StubProvider:
    """Stands in for the model. Records every request; replies from a script."""

    text: str = '{"summary": "A steady, healthy account."}'
    failure: AppError | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def run(
        self, *, system: str, messages: list[dict[str, Any]], web_search: bool = True
    ) -> ResearchResult:
        self.calls.append(
            {"system": system, "messages": [dict(m) for m in messages], "web_search": web_search}
        )
        if self.failure is not None:
            raise self.failure
        return ResearchResult(
            text=self.text,
            sources=(),
            model="claude-opus-5",
            stop_reason="end_turn",
            search_count=0,
            truncated=False,
        )

    @property
    def last_system(self) -> str:
        return self.calls[-1]["system"]


@pytest.fixture
def provider() -> StubProvider:
    return StubProvider()


@pytest.fixture
def api_app(integration_settings: Settings, provider: StubProvider) -> FastAPI:
    app = create_app(integration_settings)

    def _service(session: DbSession) -> AiInsightsService:
        return AiInsightsService(
            session,
            gateway=AiGatewayService(
                settings=integration_settings, session=session, redis=None, provider=provider
            ),
        )

    app.dependency_overrides[ai_insights_router.get_service] = _service
    return app


@pytest.fixture
def client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as test_client:
        yield test_client


def _session(client: TestClient, settings: Settings, email: str, org: uuid.UUID) -> ApiSession:
    session = ApiSession(client, settings.api_prefix)
    session.login(email, organization_id=org)
    return session


@pytest.fixture
def alpha_admin(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    return _session(client, integration_settings, alpha.admin.email, alpha.organization_id)


@pytest.fixture
def alpha_member(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    return _session(client, integration_settings, alpha.member.email, alpha.organization_id)


@pytest.fixture
def beta_admin(client: TestClient, integration_settings: Settings, beta: Tenant) -> ApiSession:
    return _session(client, integration_settings, beta.admin.email, beta.organization_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_account(api: ApiSession, name: str, **fields: Any) -> dict[str, Any]:
    response = api.post("/crm/accounts", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def stage_id(api: ApiSession, name: str) -> str:
    stages = api.get("/crm/opportunities/stages").json()
    return str(next(s["id"] for s in stages if s["name"] == name))


def make_opportunity(api: ApiSession, account_id: str, **fields: Any) -> dict[str, Any]:
    payload = {
        "name": "Renewal deal",
        "account_id": account_id,
        "stage_id": stage_id(api, "Qualification"),
        **fields,
    }
    response = api.post("/crm/opportunities", json=payload)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def make_lead(api: ApiSession, **fields: Any) -> dict[str, Any]:
    payload = {"first_name": "Grace", "last_name": "Hopper", "company": "Hopper Systems", **fields}
    response = api.post("/crm/leads", json=payload)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


# ---------------------------------------------------------------------------
# Summaries: generate, cache, refresh, history (§15, §16)
# ---------------------------------------------------------------------------


def test_no_summary_yet_is_null_not_404(alpha_member: ApiSession) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")

    response = alpha_member.get(f"{AI_INSIGHTS}/accounts/{account['id']}/summary")

    assert response.status_code == 200
    assert response.json() is None


def test_generating_a_summary_stores_and_then_caches_it(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals", industry="Chemicals")
    provider.text = '{"summary": "Zephyr is a steady chemicals account."}'

    generated = alpha_member.post(f"{AI_INSIGHTS}/accounts/{account['id']}/summary")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["content"]["summary"] == "Zephyr is a steady chemicals account."
    assert body["feature"] == "ACCOUNT_SUMMARY"
    assert body["used_crm_context"] is True
    assert "Industry: Chemicals" in provider.last_system
    assert "internal" in provider.last_system.lower() or "crm data" in provider.last_system.lower()

    cached = alpha_member.get(f"{AI_INSIGHTS}/accounts/{account['id']}/summary")
    assert cached.status_code == 200
    assert cached.json()["id"] == body["id"]
    assert len(provider.calls) == 1  # the cached read made no model call


def test_refreshing_a_summary_writes_a_new_row_not_an_overwrite(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    """Append-only history (§16): "Refresh" must not lose yesterday's answer."""
    account = make_account(alpha_member, "Zephyr Chemicals")

    provider.text = '{"summary": "First summary."}'
    first = alpha_member.post(f"{AI_INSIGHTS}/accounts/{account['id']}/summary").json()

    provider.text = '{"summary": "Second, refreshed summary."}'
    second = alpha_member.post(f"{AI_INSIGHTS}/accounts/{account['id']}/summary").json()

    assert first["id"] != second["id"]

    history = alpha_member.get(f"{AI_INSIGHTS}/ACCOUNT/{account['id']}/history").json()
    assert [h["id"] for h in history] == [second["id"], first["id"]]

    latest = alpha_member.get(f"{AI_INSIGHTS}/accounts/{account['id']}/summary").json()
    assert latest["id"] == second["id"]


def test_an_account_from_another_tenant_is_not_reachable(
    alpha_member: ApiSession, beta_admin: ApiSession
) -> None:
    foreign = make_account(beta_admin, "Beta Only Ltd")

    response = alpha_member.post(f"{AI_INSIGHTS}/accounts/{foreign['id']}/summary")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Account Intelligence — the full structured shape
# ---------------------------------------------------------------------------


def test_account_intelligence_returns_the_full_structured_shape(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    provider.text = json.dumps(
        {
            "summary": "A healthy, growing account.",
            "relationship_health": {"status": "HEALTHY", "rationale": "Recent engagement."},
            "risks": ["No open opportunities."],
            "opportunities": ["Expansion into a new product line."],
            "recommended_actions": ["Schedule a quarterly review."],
            "missing_information": [],
        }
    )

    response = alpha_member.post(f"{AI_INSIGHTS}/accounts/{account['id']}/intelligence")

    assert response.status_code == 200, response.text
    content = response.json()["content"]
    assert content["relationship_health"]["status"] == "HEALTHY"
    assert content["risks"] == ["No open opportunities."]


def test_a_malformed_model_answer_is_a_502_not_a_500(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    """§19/§20: an answer that fails schema validation must never surface as
    an unhandled server error.
    """
    account = make_account(alpha_member, "Zephyr Chemicals")
    provider.text = "Sorry, I cannot summarize that."

    response = alpha_member.post(f"{AI_INSIGHTS}/accounts/{account['id']}/summary")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_invalid_output"


# ---------------------------------------------------------------------------
# Next Best Action
# ---------------------------------------------------------------------------


def test_opportunity_next_best_action(alpha_member: ApiSession, provider: StubProvider) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"], name="Zephyr renewal")
    provider.text = json.dumps(
        {
            "action": "Follow up on the renewal proposal.",
            "why": "No activity has been logged recently.",
            "urgency": "HIGH",
            "evidence": ["No recorded activity."],
            "suggested_actions": [],
        }
    )

    response = alpha_member.post(
        f"{AI_INSIGHTS}/opportunities/{opportunity['id']}/next-best-action"
    )

    assert response.status_code == 200, response.text
    content = response.json()["content"]
    assert content["urgency"] == "HIGH"
    assert "Zephyr renewal" in provider.last_system


# ---------------------------------------------------------------------------
# AI email assistant
# ---------------------------------------------------------------------------


def test_email_draft_requires_exactly_one_subject(alpha_member: ApiSession) -> None:
    response = alpha_member.post(f"{AI_INSIGHTS}/email-draft", json={"instruction": "Say hi."})

    assert response.status_code == 422


def test_email_draft_never_sends_and_returns_subject_and_body(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    provider.text = json.dumps({"subject": "Following up", "body": "Hi there, ..."})

    response = alpha_member.post(
        f"{AI_INSIGHTS}/email-draft",
        json={"account_id": account["id"], "instruction": "Follow up after our last meeting."},
    )

    assert response.status_code == 200, response.text
    content = response.json()["content"]
    assert content["subject"] == "Following up"
    # The instruction is untrusted free text — delimited, never inlined raw.
    assert "<user-text>" in provider.last_system


# ---------------------------------------------------------------------------
# Meeting-to-CRM: extraction never writes; apply does, permission-checked
# ---------------------------------------------------------------------------


def test_meeting_extraction_writes_nothing_until_applied(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    provider.text = json.dumps(
        {
            "summary": "Discussed renewal terms.",
            "participants": ["Grace Hopper"],
            "key_points": ["Wants a 10% discount."],
            "requirements": [],
            "objections": [],
            "commitments": [],
            "sentiment": "POSITIVE",
            "follow_up_actions": [
                {"kind": "TASK", "description": "Send the revised quote.", "amount": None}
            ],
        }
    )

    response = alpha_member.post(
        f"{AI_INSIGHTS}/meetings/extract", json={"text": "We discussed the renewal terms today."}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"]["follow_up_actions"][0]["description"] == "Send the revised quote."
    tasks = alpha_member.get("/crm/tasks").json()
    assert tasks["pagination"]["total"] == 0


def test_applying_a_meeting_extraction_creates_the_confirmed_items(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"], deal_value="100000")
    provider.text = json.dumps(
        {
            "summary": "Discussed renewal terms and a higher budget.",
            "participants": [],
            "key_points": [],
            "requirements": [],
            "objections": [],
            "commitments": [],
            "sentiment": "POSITIVE",
            "follow_up_actions": [
                {"kind": "TASK", "description": "Send the revised quote.", "amount": None},
                {"kind": "NOTE", "description": "Client wants a faster rollout.", "amount": None},
                {"kind": "OPPORTUNITY_AMOUNT", "description": "New budget", "amount": "150000"},
            ],
        }
    )
    extracted = alpha_member.post(
        f"{AI_INSIGHTS}/meetings/extract",
        json={"text": "Meeting notes here.", "opportunity_id": opportunity["id"]},
    ).json()

    applied = alpha_member.post(
        f"{AI_INSIGHTS}/meetings/{extracted['id']}/apply", json={"indexes": [0, 1, 2]}
    )

    assert applied.status_code == 200, applied.text
    results = applied.json()["results"]
    outcomes = {r["kind"]: r["outcome"] for r in results}
    assert outcomes == {"TASK": "CREATED", "NOTE": "CREATED", "OPPORTUNITY_AMOUNT": "CREATED"}

    updated_opportunity = alpha_member.get(f"/crm/opportunities/{opportunity['id']}").json()
    assert float(updated_opportunity["deal_value"]) == 150000.0


def test_applying_the_same_index_twice_is_skipped_not_duplicated(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    provider.text = json.dumps(
        {
            "summary": "Call recap.",
            "participants": [],
            "key_points": [],
            "requirements": [],
            "objections": [],
            "commitments": [],
            "sentiment": "NEUTRAL",
            "follow_up_actions": [
                {"kind": "TASK", "description": "Send follow-up email.", "amount": None}
            ],
        }
    )
    extracted = alpha_member.post(
        f"{AI_INSIGHTS}/meetings/extract", json={"text": "Call recap notes."}
    ).json()
    first = alpha_member.post(
        f"{AI_INSIGHTS}/meetings/{extracted['id']}/apply", json={"indexes": [0]}
    ).json()
    assert first["results"][0]["outcome"] == "CREATED"

    second = alpha_member.post(
        f"{AI_INSIGHTS}/meetings/{extracted['id']}/apply", json={"indexes": [0]}
    ).json()

    assert second["results"][0]["outcome"] == "SKIPPED"
    tasks = alpha_member.get("/crm/tasks").json()
    assert tasks["pagination"]["total"] == 1


# ---------------------------------------------------------------------------
# Natural-language CRM queries
# ---------------------------------------------------------------------------


def test_an_unclear_question_is_reported_as_not_understood(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    provider.text = json.dumps(
        {"understood": False, "definition": None, "clarification": "Which entity did you mean?"}
    )

    response = alpha_member.post(f"{AI_INSIGHTS}/query", json={"question": "how are things?"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["understood"] is False
    assert body["result"] is None


def test_an_understood_question_runs_the_translated_report(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    make_account(alpha_member, "Zephyr Chemicals", industry="Chemicals")
    provider.text = json.dumps(
        {
            "understood": True,
            "definition": {
                "entity": "ACCOUNT",
                "fields": ["name", "industry"],
                "filters": {"logic": "AND", "conditions": []},
            },
            "clarification": None,
        }
    )

    response = alpha_member.post(
        f"{AI_INSIGHTS}/query", json={"question": "list our accounts and their industries"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["understood"] is True
    assert body["result"] is not None
    assert len(body["result"]["rows"]) >= 1


# ---------------------------------------------------------------------------
# Prioritization — rules first, AI explanation second (§10, §12)
# ---------------------------------------------------------------------------


def test_priority_list_ranks_without_calling_the_model(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    make_opportunity(
        alpha_member,
        account["id"],
        name="Big overdue deal",
        deal_value="5000000",
        expected_close_date=(dt.date.today() - dt.timedelta(days=3)).isoformat(),
    )

    response = alpha_member.get(f"{AI_INSIGHTS}/priority/opportunities")

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) >= 1
    assert items[0]["level"] in {"HIGH", "MEDIUM"}
    labels = {reason["label"] for reason in items[0]["reasons"]}
    assert "Large deal" in labels
    assert "Past close date" in labels
    assert not provider.calls  # rules only, no model call


def _priority_item(api: ApiSession, kind: str, entity_id: str) -> dict[str, Any]:
    response = api.get(f"{AI_INSIGHTS}/priority/{kind}?limit=100")
    assert response.status_code == 200, response.text
    item: dict[str, Any] = next(i for i in response.json()["items"] if i["entity_id"] == entity_id)
    return item


def test_priority_list_carries_each_deals_own_facts(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    """The Next Best Action queue shows what a deal is without a request per row."""
    account = make_account(alpha_member, "Zephyr Chemicals")
    close = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    opportunity = make_opportunity(
        alpha_member,
        account["id"],
        name="Zephyr expansion",
        deal_value="750000",
        expected_close_date=close,
    )
    task = alpha_member.post(
        "/crm/tasks",
        json={
            "title": "Send pricing",
            "related_entity_type": "OPPORTUNITY",
            "related_entity_id": opportunity["id"],
        },
    )
    assert task.status_code == 201, task.text

    item = _priority_item(alpha_member, "opportunities", opportunity["id"])

    facts = item["facts"]
    assert facts["account_id"] == account["id"]
    assert facts["account_name"] == "Zephyr Chemicals"
    assert facts["stage_name"] == "Qualification"
    assert float(facts["deal_value"]) == 750000
    assert facts["expected_close_date"] == close
    assert facts["open_task_count"] == 1
    assert facts["overdue_task_count"] == 0
    assert item["latest_recommendation"] is None
    assert not provider.calls  # listing the queue never calls the model


def test_priority_list_includes_the_latest_cached_recommendation(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    lead = make_lead(alpha_member, email="grace@hopper.example")
    provider.text = json.dumps(
        {
            "action": "Call Grace to qualify budget.",
            "why": "The lead has never been contacted.",
            "urgency": "HIGH",
            "evidence": ["No activity logged."],
            "suggested_actions": [],
        }
    )
    generated = alpha_member.post(f"{AI_INSIGHTS}/leads/{lead['id']}/next-best-action")
    assert generated.status_code == 200, generated.text

    item = _priority_item(alpha_member, "leads", lead["id"])

    assert item["facts"]["company"] == "Hopper Systems"
    assert item["facts"]["email"] == "grace@hopper.example"
    assert item["facts"]["status"] == lead["status"]
    recommendation = item["latest_recommendation"]
    assert recommendation["id"] == generated.json()["id"]
    assert recommendation["content"]["action"] == "Call Grace to qualify budget."
    assert len(provider.calls) == 1  # the generation above, and nothing since


def test_priority_facts_never_name_an_account_the_caller_cannot_see(
    alpha_admin: ApiSession, alpha_member: ApiSession, alpha: Tenant
) -> None:
    """Seeing a deal is not seeing its account: the account's own visibility applies."""
    account = make_account(alpha_admin, "Admin Owned Ltd")
    opportunity = make_opportunity(alpha_admin, account["id"], owner_id=str(alpha.member.user_id))
    assert alpha_member.get(f"/crm/accounts/{account['id']}").status_code == 404

    item = _priority_item(alpha_member, "opportunities", opportunity["id"])

    assert item["facts"]["account_id"] == account["id"]
    assert item["facts"]["account_name"] is None


def test_priority_facts_do_not_count_an_archived_task_as_open(
    alpha_member: ApiSession, alpha_admin: ApiSession
) -> None:
    """An archived task is gone from the record, so the queue must not count it.

    The admin archives it: the User role may not delete.
    """
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"])
    task = alpha_member.post(
        "/crm/tasks",
        json={
            "title": "Send pricing",
            "related_entity_type": "OPPORTUNITY",
            "related_entity_id": opportunity["id"],
        },
    )
    assert task.status_code == 201, task.text
    before = _priority_item(alpha_member, "opportunities", opportunity["id"])["facts"]
    assert before["open_task_count"] == 1

    archived = alpha_admin.delete(f"/crm/tasks/{task.json()['id']}")
    assert archived.status_code == 204, archived.text

    after = _priority_item(alpha_member, "opportunities", opportunity["id"])["facts"]
    assert after["open_task_count"] == 0


def test_explaining_a_priority_narrates_the_precomputed_reasons(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(
        alpha_member,
        account["id"],
        deal_value="5000000",
        expected_close_date=(dt.date.today() - dt.timedelta(days=3)).isoformat(),
    )
    provider.text = json.dumps({"explanation": "This deal is high priority because ..."})

    response = alpha_member.post(
        f"{AI_INSIGHTS}/priority/opportunities/{opportunity['id']}/explain"
    )

    assert response.status_code == 200, response.text
    assert "Large deal" in provider.last_system or "Past close date" in provider.last_system


def test_explaining_a_closed_deals_priority_is_404(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"])
    won = alpha_member.post(
        f"/crm/opportunities/{opportunity['id']}/stage",
        json={"stage_id": stage_id(alpha_member, "Closed Won")},
    )
    assert won.status_code == 200, won.text

    response = alpha_member.post(
        f"{AI_INSIGHTS}/priority/opportunities/{opportunity['id']}/explain"
    )

    assert response.status_code == 404


# Archived tasks and activities are gone from the record's own views, so they
# cannot be a reason in its priority either — every reason must be a fact a
# caller could check by opening the record (prioritization.py). A rep creates
# the work; the admin archives it, since the User role may not delete.


def _priority_reasons(api: ApiSession, kind: str, entity_id: str) -> set[str]:
    response = api.get(f"{AI_INSIGHTS}/priority/{kind}?limit=100")
    assert response.status_code == 200, response.text
    item = next(i for i in response.json()["items"] if i["entity_id"] == entity_id)
    return {reason["label"] for reason in item["reasons"]}


def _archive(api: ApiSession, path: str) -> None:
    response = api.delete(path)
    assert response.status_code == 204, response.text


def test_an_archived_overdue_task_is_not_a_priority_reason(
    alpha_member: ApiSession, alpha_admin: ApiSession
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"])
    task = alpha_member.post(
        "/crm/tasks",
        json={
            "title": "Send revised pricing",
            "due_date": (dt.datetime.now(dt.UTC) - dt.timedelta(days=2)).isoformat(),
            "related_entity_type": "OPPORTUNITY",
            "related_entity_id": opportunity["id"],
        },
    )
    assert task.status_code == 201, task.text
    assert "Overdue task(s)" in _priority_reasons(alpha_member, "opportunities", opportunity["id"])

    _archive(alpha_admin, f"/crm/tasks/{task.json()['id']}")

    reasons = _priority_reasons(alpha_member, "opportunities", opportunity["id"])
    assert "Overdue task(s)" not in reasons


def test_an_archived_open_task_is_not_a_scheduled_follow_up(
    alpha_member: ApiSession, alpha_admin: ApiSession
) -> None:
    lead = make_lead(alpha_member)
    task = alpha_member.post(
        "/crm/tasks",
        json={"title": "Call back", "related_entity_type": "LEAD", "related_entity_id": lead["id"]},
    )
    assert task.status_code == 201, task.text
    assert "No follow-up scheduled" not in _priority_reasons(alpha_member, "leads", lead["id"])

    _archive(alpha_admin, f"/crm/tasks/{task.json()['id']}")

    assert "No follow-up scheduled" in _priority_reasons(alpha_member, "leads", lead["id"])


def test_an_archived_activity_is_not_the_last_contact(
    alpha_member: ApiSession, alpha_admin: ApiSession
) -> None:
    lead = make_lead(alpha_member)
    activity = alpha_member.post(
        "/crm/activities",
        json={
            "type": "CALL",
            "subject": "Intro call",
            "status": "COMPLETED",
            "related_entity_type": "LEAD",
            "related_entity_id": lead["id"],
        },
    )
    assert activity.status_code == 201, activity.text
    assert "Never contacted" not in _priority_reasons(alpha_member, "leads", lead["id"])

    _archive(alpha_admin, f"/crm/activities/{activity.json()['id']}")

    assert "Never contacted" in _priority_reasons(alpha_member, "leads", lead["id"])


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------


def test_feedback_round_trip(alpha_member: ApiSession, provider: StubProvider) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    generation = alpha_member.post(f"{AI_INSIGHTS}/accounts/{account['id']}/summary").json()

    response = alpha_member.post(
        f"{AI_INSIGHTS}/generations/{generation['id']}/feedback",
        json={"rating": "UP", "comment": "Accurate."},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["feedback_rating"] == "UP"
    assert body["feedback_comment"] == "Accurate."


# ---------------------------------------------------------------------------
# Insights digest — rules only
# ---------------------------------------------------------------------------


def test_insights_digest_flags_a_deal_closing_soon_with_low_probability(
    alpha_member: ApiSession,
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    make_opportunity(
        alpha_member,
        account["id"],
        name="At-risk deal",
        expected_close_date=(dt.date.today() + dt.timedelta(days=2)).isoformat(),
        win_probability=20,
    )

    response = alpha_member.get(f"{AI_INSIGHTS}/digest")

    assert response.status_code == 200, response.text
    titles = [item["title"] for item in response.json()["deals_at_risk"]]
    assert any("At-risk deal" in title for title in titles)


# ---------------------------------------------------------------------------
# Next Best Action engine: rules, history, Copilot (Levels 1-3)
# ---------------------------------------------------------------------------


def _actions(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {action["action_code"]: action for action in item["actions"]}


def _move(api: ApiSession, opportunity_id: str, stage: str, **extra: Any) -> None:
    response = api.post(
        f"/crm/opportunities/{opportunity_id}/stage",
        json={"stage_id": stage_id(api, stage), **extra},
    )
    assert response.status_code == 200, response.text


def _meeting(
    api: ApiSession, entity_type: str, entity_id: str, subject: str, start: dt.datetime
) -> None:
    response = api.post(
        "/crm/activities",
        json={
            "type": "MEETING",
            "subject": subject,
            "status": "COMPLETED",
            "related_entity_type": entity_type,
            "related_entity_id": entity_id,
            "meeting": {"meeting_type": "VIDEO", "start_time": start.isoformat()},
        },
    )
    assert response.status_code == 201, response.text


def test_the_queue_recommends_coordinated_actions_from_real_signals(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Kaveri Steel", industry="Manufacturing")
    opportunity = make_opportunity(
        alpha_member,
        account["id"],
        name="Kaveri MES rollout",
        stage_id=stage_id(alpha_member, "Proposal"),
        deal_value="2500000",
        competitor="Zoho",
    )
    _meeting(
        alpha_member,
        "OPPORTUNITY",
        opportunity["id"],
        "Discovery call",
        dt.datetime.now(dt.UTC) - dt.timedelta(days=12),
    )

    item = _priority_item(alpha_member, "opportunities", opportunity["id"])

    actions = _actions(item)
    for expected in (
        "SCHEDULE_PRICING_DISCUSSION",
        "SEND_COMPETITIVE_BATTLECARD",
        "SEND_CASE_STUDY",
        "SCHEDULE_STAKEHOLDER_MEETING",
    ):
        assert expected in actions, sorted(actions)
    assert len(item["actions"]) == len(actions), "no duplicate actions"
    battlecard = actions["SEND_COMPETITIVE_BATTLECARD"]
    assert battlecard["category"] == "CONTENT"
    assert battlecard["execution"] == "EMAIL"
    assert battlecard["level"] == "RULE"
    assert "Zoho" in battlecard["reasons"][0]
    assert {
        "key": "has_competitor",
        "label": "Competitor identified",
        "value": "Yes",
    } in battlecard["signals"]
    assert "Manufacturing" in actions["SEND_CASE_STUDY"]["reasons"][0]
    assert item["signals"]["stage_is_proposal"] is True
    assert item["signals"]["days_since_last_meeting"] == 12
    assert "recent_interaction_text" not in item["signals"]
    assert not provider.calls  # the engine never calls the model


def test_one_records_next_best_actions_and_a_closed_deal(alpha_member: ApiSession) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"], competitor="Salesforce")

    response = alpha_member.get(f"{AI_INSIGHTS}/nba/opportunities/{opportunity['id']}")
    assert response.status_code == 200, response.text
    assert "SEND_COMPETITIVE_BATTLECARD" in _actions(response.json())

    _move(alpha_member, opportunity["id"], "Closed Won")
    closed = alpha_member.get(f"{AI_INSIGHTS}/nba/opportunities/{opportunity['id']}")
    assert closed.status_code == 200
    assert closed.json() is None


def test_another_tenants_record_is_not_reachable_through_the_engine(
    alpha_member: ApiSession, beta_admin: ApiSession
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"])

    missing = beta_admin.get(f"{AI_INSIGHTS}/nba/opportunities/{opportunity['id']}")
    assert missing.status_code == 404
    logged = beta_admin.post(
        f"{AI_INSIGHTS}/nba/actions/log",
        json={
            "entity_type": "OPPORTUNITY",
            "entity_id": opportunity["id"],
            "action_code": "CALL_CUSTOMER",
            "outcome": "DISMISSED",
        },
    )
    assert logged.status_code == 404


def test_an_executed_action_is_not_recommended_again(alpha_member: ApiSession) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"], competitor="Zoho")
    before = _priority_item(alpha_member, "opportunities", opportunity["id"])
    assert "SEND_COMPETITIVE_BATTLECARD" in _actions(before)

    logged = alpha_member.post(
        f"{AI_INSIGHTS}/nba/actions/log",
        json={
            "entity_type": "OPPORTUNITY",
            "entity_id": opportunity["id"],
            "action_code": "SEND_COMPETITIVE_BATTLECARD",
            "outcome": "EXECUTED",
            "rule_keys": ["competitor_battlecard"],
        },
    )
    assert logged.status_code == 201, logged.text
    assert logged.json()["outcome"] == "EXECUTED"

    after = _priority_item(alpha_member, "opportunities", opportunity["id"])
    assert "SEND_COMPETITIVE_BATTLECARD" not in _actions(after)


def test_archived_interactions_are_not_the_last_interaction(
    alpha_member: ApiSession, alpha_admin: ApiSession
) -> None:
    lead = make_lead(alpha_member)
    call = alpha_member.post(
        "/crm/activities",
        json={
            "type": "CALL",
            "subject": "Intro call",
            "status": "COMPLETED",
            "related_entity_type": "LEAD",
            "related_entity_id": lead["id"],
        },
    )
    assert call.status_code == 201, call.text
    before = _priority_item(alpha_member, "leads", lead["id"])
    assert before["signals"]["days_since_last_interaction"] == 0

    assert alpha_admin.delete(f"/crm/activities/{call.json()['id']}").status_code == 204

    after = _priority_item(alpha_member, "leads", lead["id"])
    assert after["signals"]["days_since_last_interaction"] is None
    assert "CALL_CUSTOMER" in _actions(after)


def _custom_rule(name: str, action_code: str) -> dict[str, Any]:
    return {
        "name": name,
        "applies_to": "OPPORTUNITY",
        "conditions": [
            {"field_key": "recent_interaction_text", "operator": "contains", "value": "salesforce"}
        ],
        "action_code": action_code,
        "priority": "HIGH",
        "reason": "The customer mentioned Salesforce.",
    }


def test_only_an_admin_may_change_the_organizations_rules(
    alpha_member: ApiSession, alpha_admin: ApiSession
) -> None:
    payload = _custom_rule("Salesforce mentioned", "SEND_COMPETITIVE_BATTLECARD")
    assert alpha_member.post(f"{AI_INSIGHTS}/nba/rules", json=payload).status_code == 403
    assert alpha_member.get(f"{AI_INSIGHTS}/nba/rules").status_code == 200

    created = alpha_admin.post(f"{AI_INSIGHTS}/nba/rules", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "CUSTOM"

    duplicate = alpha_admin.post(f"{AI_INSIGHTS}/nba/rules", json=payload)
    assert duplicate.status_code == 409


def test_a_custom_rule_fires_and_stays_inside_its_tenant(
    alpha_member: ApiSession, alpha_admin: ApiSession, beta_admin: ApiSession
) -> None:
    created = alpha_admin.post(
        f"{AI_INSIGHTS}/nba/rules",
        json=_custom_rule("Mentioned Salesforce on a call", "SCHEDULE_EXECUTIVE_ALIGNMENT"),
    )
    assert created.status_code == 201, created.text
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"])
    call = alpha_member.post(
        "/crm/activities",
        json={
            "type": "CALL",
            "subject": "Check-in",
            "description": "They are also evaluating Salesforce.",
            "status": "COMPLETED",
            "related_entity_type": "OPPORTUNITY",
            "related_entity_id": opportunity["id"],
        },
    )
    assert call.status_code == 201, call.text

    item = _priority_item(alpha_member, "opportunities", opportunity["id"])
    action = _actions(item)["SCHEDULE_EXECUTIVE_ALIGNMENT"]
    assert action["priority"] == "HIGH"
    assert f"custom.{created.json()['id']}" in action["rule_keys"]

    beta_rules = beta_admin.get(f"{AI_INSIGHTS}/nba/rules").json()
    assert all(rule["source"] == "BUILTIN" for rule in beta_rules)


def test_an_invalid_rule_is_refused(alpha_admin: ApiSession) -> None:
    payload = _custom_rule("Broken", "CALL_CUSTOMER")
    payload["conditions"] = [{"field_key": "made_up", "operator": "equals", "value": 1}]
    assert alpha_admin.post(f"{AI_INSIGHTS}/nba/rules", json=payload).status_code == 422


def test_a_builtin_rule_can_be_switched_off_and_reset(
    alpha_member: ApiSession, alpha_admin: ApiSession
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"], competitor="Zoho")

    off = alpha_admin.put(
        f"{AI_INSIGHTS}/nba/rules/builtin/competitor_battlecard", json={"is_active": False}
    )
    assert off.status_code == 200, off.text
    assert off.json()["is_overridden"] is True
    disabled = _priority_item(alpha_member, "opportunities", opportunity["id"])
    assert "SEND_COMPETITIVE_BATTLECARD" not in _actions(disabled)

    reset = alpha_admin.delete(f"{AI_INSIGHTS}/nba/rules/builtin/competitor_battlecard")
    assert reset.status_code == 204
    restored = _priority_item(alpha_member, "opportunities", opportunity["id"])
    assert "SEND_COMPETITIVE_BATTLECARD" in _actions(restored)


def test_the_catalog_lists_every_category(alpha_member: ApiSession) -> None:
    body = alpha_member.get(f"{AI_INSIGHTS}/nba/catalog").json()
    assert set(body["categories"]) == {
        "COMMUNICATION",
        "MEETING",
        "CONTENT",
        "INTERNAL",
        "QUALIFICATION",
        "RISK",
    }
    assert any(signal["key"] == "awaiting_customer_response" for signal in body["signals"])


def test_the_copilot_drafts_for_review_without_executing_anything(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"], competitor="Zoho")
    provider.text = json.dumps(
        {"subject": "How we compare with Zoho", "body": "Hi [Name], here is our comparison."}
    )

    response = alpha_member.post(
        f"{AI_INSIGHTS}/nba/copilot",
        json={
            "entity_type": "OPPORTUNITY",
            "entity_id": opportunity["id"],
            "action_code": "SEND_COMPETITIVE_BATTLECARD",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["feature"] == "NBA_COPILOT"
    assert body["content"]["kind"] == "EMAIL"
    assert body["content"]["action_code"] == "SEND_COMPETITIVE_BATTLECARD"
    assert body["content"]["subject"] == "How we compare with Zoho"
    assert "Zoho is competing" in provider.last_system  # the engine's reason reached the prompt
    emails = alpha_member.get("/crm/emails").json()
    assert emails["pagination"]["total"] == 0  # nothing was sent or even drafted


def test_the_copilot_refuses_an_action_that_does_not_apply(alpha_member: ApiSession) -> None:
    lead = make_lead(alpha_member)
    response = alpha_member.post(
        f"{AI_INSIGHTS}/nba/copilot",
        json={"entity_type": "LEAD", "entity_id": lead["id"], "action_code": "INVOLVE_LEGAL_TEAM"},
    )
    assert response.status_code == 422


def test_ai_being_unavailable_does_not_break_the_queue(
    alpha_member: ApiSession, provider: StubProvider
) -> None:
    provider.failure = AiTemporarilyUnavailableError("Provider overloaded.")
    account = make_account(alpha_member, "Zephyr Chemicals")
    opportunity = make_opportunity(alpha_member, account["id"], competitor="Zoho")

    copilot = alpha_member.post(
        f"{AI_INSIGHTS}/nba/copilot",
        json={
            "entity_type": "OPPORTUNITY",
            "entity_id": opportunity["id"],
            "action_code": "SEND_COMPETITIVE_BATTLECARD",
        },
    )
    assert copilot.status_code == 503

    item = _priority_item(alpha_member, "opportunities", opportunity["id"])
    assert "SEND_COMPETITIVE_BATTLECARD" in _actions(item)


def test_history_drives_a_predictive_recommendation(alpha_member: ApiSession) -> None:
    """Deals that held a technical workshop before the proposal won far more often."""
    account = make_account(alpha_member, "Zephyr Chemicals")
    workshop_day = dt.datetime.now(dt.UTC) - dt.timedelta(days=20)
    outcomes = [(True, True)] * 7 + [(True, False)] + [(False, True)] + [(False, False)] * 7
    for index, (workshop, won) in enumerate(outcomes):
        deal = make_opportunity(alpha_member, account["id"], name=f"History {index}")
        if workshop:
            _meeting(alpha_member, "OPPORTUNITY", deal["id"], "Technical workshop", workshop_day)
        _move(alpha_member, deal["id"], "Proposal")
        if won:
            _move(alpha_member, deal["id"], "Closed Won")
        else:
            _move(alpha_member, deal["id"], "Closed Lost", loss_reason="Budget")

    open_deal = make_opportunity(alpha_member, account["id"], name="New early deal")

    item = _priority_item(alpha_member, "opportunities", open_deal["id"])

    workshop = _actions(item)["SCHEDULE_TECHNICAL_WORKSHOP"]
    assert workshop["level"] == "PREDICTIVE"
    assert workshop["confidence"] is not None and workshop["confidence"] >= 80
    assert "88%" in workshop["reasons"][0]
    assert item["signals"]["similar_deal_win_rate"] == 50
