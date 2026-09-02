"""Stage 1: derivations and the automation that needs no scheduler.

Four behaviours, each removing a thing a user would otherwise type or lose:

* lead notes follow the lead into what it became, once, with provenance;
* the pipeline reports a weighted figure a forecast can be built on;
* a new organization starts with lead sources, idempotently;
* entering a stage creates its configured follow-up, and only one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.products.crm.leads.source_service import (
    DEFAULT_LEAD_SOURCES,
    LeadSourceService,
)
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """A second signed-in session for alpha's plain ``User``.

    ``as_alpha_admin`` and ``as_alpha_member`` both return the shared ``api``
    object, so asking for both in one test yields a single session logged in as
    whichever resolved last. Two people signed in at once needs two sessions.
    """
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


def _stage(session: ApiSession, name: str) -> dict[str, object]:
    stages = session.get("/crm/opportunities/stages").json()
    return next(stage for stage in stages if stage["name"] == name)


def _qualified_lead(session: ApiSession, *, company: str = "Note Carry Ltd") -> str:
    created = session.post(
        "/crm/leads",
        json={
            "first_name": "Nora",
            "last_name": "Keeper",
            "company": company,
            "email": f"nora@{company.lower().replace(' ', '')}.example",
        },
    )
    assert created.status_code == 201, created.text
    lead_id = str(created.json()["id"])
    for step in ("CONTACTED", "QUALIFIED"):
        moved = session.post(f"/crm/leads/{lead_id}/status", json={"status": step})
        assert moved.status_code == 200, moved.text
    return lead_id


def _account(session: ApiSession, name: str) -> str:
    created = session.post("/crm/accounts", json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _deal(
    session: ApiSession,
    *,
    name: str,
    account_id: str,
    stage_name: str = "Qualification",
    value: str | None = None,
    probability: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "account_id": account_id,
        "stage_id": str(_stage(session, stage_name)["id"]),
        "expected_close_date": "2026-12-31",
    }
    if value is not None:
        payload["deal_value"] = value
    if probability is not None:
        payload["win_probability"] = probability
    created = session.post("/crm/opportunities", json=payload)
    assert created.status_code == 201, created.text
    return dict(created.json())


# --- Note carry-over ---------------------------------------------------------


def test_lead_notes_move_to_the_opportunity_with_provenance(
    as_alpha_admin: ApiSession,
) -> None:
    """Moved, not copied: one authority, and the origin recorded."""
    lead_id = _qualified_lead(as_alpha_admin)
    note = as_alpha_admin.post(
        "/crm/notes",
        json={
            "content": "Budget signed off by the CFO.",
            "related_entity_type": "LEAD",
            "related_entity_id": lead_id,
        },
    )
    assert note.status_code == 201, note.text
    note_id = str(note.json()["id"])

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})
    assert converted.status_code == 201, converted.text
    opportunity_id = str(converted.json()["opportunity_id"])

    moved = as_alpha_admin.get(f"/crm/notes/{note_id}").json()
    assert moved["related_entity_type"] == "OPPORTUNITY"
    assert str(moved["related_entity_id"]) == opportunity_id
    # Provenance is what moving costs and what these columns buy back.
    assert moved["origin_entity_type"] == "LEAD"
    assert str(moved["origin_entity_id"]) == lead_id


def test_notes_are_not_duplicated_across_the_converted_records(
    as_alpha_admin: ApiSession,
) -> None:
    """Zoho copies to three records; three copies immediately start to drift."""
    lead_id = _qualified_lead(as_alpha_admin, company="Single Copy Ltd")
    for index in range(2):
        created = as_alpha_admin.post(
            "/crm/notes",
            json={
                "content": f"Observation {index}",
                "related_entity_type": "LEAD",
                "related_entity_id": lead_id,
            },
        )
        assert created.status_code == 201, created.text

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})
    assert converted.status_code == 201, converted.text
    body = converted.json()

    listed = as_alpha_admin.get("/crm/notes", params={"page_size": 100}).json()["data"]
    assert len(listed) == 2, "notes were duplicated rather than moved"
    # None of them still points at the lead, and none landed on the account.
    targets = {str(note["related_entity_id"]) for note in listed}
    assert targets == {str(body["opportunity_id"])}


def test_notes_land_on_the_contact_when_no_deal_is_created(
    as_alpha_admin: ApiSession,
) -> None:
    """The contact is the fallback home: it always exists after conversion."""
    lead_id = _qualified_lead(as_alpha_admin, company="No Deal Ltd")
    as_alpha_admin.post(
        "/crm/notes",
        json={
            "content": "Spoke at the trade show.",
            "related_entity_type": "LEAD",
            "related_entity_id": lead_id,
        },
    )

    converted = as_alpha_admin.post(
        f"/crm/leads/{lead_id}/convert", json={"create_opportunity": False}
    )
    assert converted.status_code == 201, converted.text

    listed = as_alpha_admin.get("/crm/notes", params={"page_size": 100}).json()["data"]
    assert len(listed) == 1
    assert listed[0]["related_entity_type"] == "CONTACT"
    assert str(listed[0]["related_entity_id"]) == str(converted.json()["contact_id"])


def test_conversion_without_notes_is_unaffected(as_alpha_admin: ApiSession) -> None:
    """Guards the guard: the carry-over must not require notes to exist."""
    lead_id = _qualified_lead(as_alpha_admin, company="Quiet Lead Ltd")

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert converted.status_code == 201, converted.text


# --- Weighted pipeline -------------------------------------------------------


def test_the_dashboard_reports_a_weighted_pipeline(as_alpha_admin: ApiSession) -> None:
    """A 10% deal and a 90% deal are not worth the same to a forecast."""
    account_id = _account(as_alpha_admin, "Weighted Ltd")
    _deal(
        as_alpha_admin,
        name="Long shot",
        account_id=account_id,
        value="100000.00",
        probability=10,
    )
    _deal(
        as_alpha_admin,
        name="Near certain",
        account_id=account_id,
        value="100000.00",
        probability=90,
    )

    summary = as_alpha_admin.get("/crm/dashboard/summary").json()

    assert float(summary["pipeline_total"]) == pytest.approx(200000.0)
    # 100000*0.10 + 100000*0.90
    assert float(summary["weighted_pipeline_total"]) == pytest.approx(100000.0)
    assert float(summary["kpis"]["weighted_pipeline_value"]) == pytest.approx(100000.0)


def test_weighted_pipeline_excludes_closed_deals(as_alpha_admin: ApiSession) -> None:
    """A won deal is revenue, not pipeline; a lost one is neither."""
    account_id = _account(as_alpha_admin, "Closed Out Ltd")
    deal = _deal(
        as_alpha_admin,
        name="Will be won",
        account_id=account_id,
        value="50000.00",
        probability=50,
    )
    won_stage = str(_stage(as_alpha_admin, "Closed Won")["id"])
    moved = as_alpha_admin.post(
        f"/crm/opportunities/{deal['id']}/stage",
        json={"stage_id": won_stage, "win_reason": "Best fit"},
    )
    assert moved.status_code == 200, moved.text

    summary = as_alpha_admin.get("/crm/dashboard/summary").json()

    assert float(summary["weighted_pipeline_total"]) == pytest.approx(0.0)


def test_a_deal_with_no_probability_contributes_nothing_weighted(
    as_alpha_admin: ApiSession,
) -> None:
    """An unknown probability must not be counted as certainty."""
    account_id = _account(as_alpha_admin, "Unknown Odds Ltd")
    # Probability 0 is the closest the API allows to "unset" on create, since
    # the stage default fills a NULL. Zero contributes zero, which is the same
    # conservative direction a NULL takes.
    _deal(
        as_alpha_admin,
        name="No odds",
        account_id=account_id,
        value="80000.00",
        probability=0,
    )

    summary = as_alpha_admin.get("/crm/dashboard/summary").json()

    assert float(summary["pipeline_total"]) == pytest.approx(80000.0)
    assert float(summary["weighted_pipeline_total"]) == pytest.approx(0.0)


def test_weighted_pipeline_is_reported_per_stage(as_alpha_admin: ApiSession) -> None:
    """The Kanban column needs its own weighted figure, not just the total."""
    account_id = _account(as_alpha_admin, "Per Stage Ltd")
    _deal(
        as_alpha_admin,
        name="In proposal",
        account_id=account_id,
        stage_name="Proposal",
        value="10000.00",
        probability=50,
    )

    summary = as_alpha_admin.get("/crm/dashboard/summary").json()
    proposal = next(row for row in summary["pipeline"] if row["name"] == "Proposal")

    assert float(proposal["value"]) == pytest.approx(10000.0)
    assert float(proposal["weighted_value"]) == pytest.approx(5000.0)


def test_weighted_pipeline_respects_record_visibility(
    as_alpha_admin: ApiSession, rep: ApiSession
) -> None:
    """A rep's forecast must not include deals they cannot open."""
    account_id = _account(as_alpha_admin, "Not Mine Ltd")
    _deal(
        as_alpha_admin,
        name="Admin's deal",
        account_id=account_id,
        value="70000.00",
        probability=50,
    )

    rep_summary = rep.get("/crm/dashboard/summary").json()

    assert float(rep_summary["weighted_pipeline_total"]) == pytest.approx(0.0)


def test_weighted_pipeline_does_not_leak_across_tenants(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """The aggregate is scoped like every other read."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    account_id = _account(api, "Alpha Only Ltd")
    _deal(api, name="Alpha deal", account_id=account_id, value="90000.00", probability=50)

    api.login(beta.admin.email, organization_id=beta.organization_id)
    beta_summary = api.get("/crm/dashboard/summary").json()

    assert float(beta_summary["weighted_pipeline_total"]) == pytest.approx(0.0)


# --- Lead source seeding -----------------------------------------------------


async def test_provisioning_seeds_lead_sources_idempotently(
    session_factory: async_sessionmaker[AsyncSession],
    as_alpha_admin: ApiSession,
    alpha: Tenant,
) -> None:
    """An empty dropdown on the first lead form teaches people to skip the field.

    Seeded here rather than in the shared fixture: putting six sources into
    every tenant changes name availability for tests that are not about
    attribution at all.
    """
    async with session_factory() as session, session.begin():
        first = await LeadSourceService(session).ensure_default_sources(
            alpha.organization_id
        )
    assert len(first) == len(DEFAULT_LEAD_SOURCES)

    names = {
        source["name"]
        for source in as_alpha_admin.get(
            "/crm/lead-sources", params={"page_size": 100}
        ).json()["data"]
    }
    assert {"Website", "Referral", "Email Campaign"} <= names

    # Idempotent per source: a second run creates nothing and does not collide
    # with the partial unique index.
    async with session_factory() as session, session.begin():
        second = await LeadSourceService(session).ensure_default_sources(
            alpha.organization_id
        )
    assert second == []


# --- Stage follow-up tasks ---------------------------------------------------


def test_entering_a_stage_creates_its_configured_follow_up(
    as_alpha_admin: ApiSession,
) -> None:
    """Declarative automation: the stage row names the task, entry creates it."""
    account_id = _account(as_alpha_admin, "Follow Up Ltd")
    deal = _deal(as_alpha_admin, name="Chase me", account_id=account_id)
    proposal = _stage(as_alpha_admin, "Proposal")
    assert proposal["follow_up_task_title"] == "Follow up on proposal"

    moved = as_alpha_admin.post(
        f"/crm/opportunities/{deal['id']}/stage", json={"stage_id": str(proposal["id"])}
    )
    assert moved.status_code == 200, moved.text

    tasks = as_alpha_admin.get(
        "/crm/tasks",
        params={"related_entity_type": "OPPORTUNITY", "related_entity_id": deal["id"]},
    ).json()["data"]
    titles = [task["title"] for task in tasks]
    assert "Follow up on proposal" in titles
    created = next(task for task in tasks if task["title"] == "Follow up on proposal")
    assert created["due_date"] is not None


def test_revisiting_a_stage_does_not_create_a_second_open_task(
    as_alpha_admin: ApiSession,
) -> None:
    """A rep moving a deal back and forward must not mint duplicate chores."""
    account_id = _account(as_alpha_admin, "Back And Forth Ltd")
    deal = _deal(as_alpha_admin, name="Yo-yo", account_id=account_id)
    proposal = str(_stage(as_alpha_admin, "Proposal")["id"])
    discovery = str(_stage(as_alpha_admin, "Discovery")["id"])

    for stage_id in (proposal, discovery, proposal):
        moved = as_alpha_admin.post(
            f"/crm/opportunities/{deal['id']}/stage", json={"stage_id": stage_id}
        )
        assert moved.status_code == 200, moved.text

    tasks = as_alpha_admin.get(
        "/crm/tasks",
        params={"related_entity_type": "OPPORTUNITY", "related_entity_id": deal["id"]},
    ).json()["data"]
    proposal_tasks = [t for t in tasks if t["title"] == "Follow up on proposal"]
    assert len(proposal_tasks) == 1


def test_a_stage_without_a_configured_follow_up_creates_nothing(
    as_alpha_admin: ApiSession,
) -> None:
    """Guards the guard: automation must be opt-in per stage."""
    account_id = _account(as_alpha_admin, "No Automation Ltd")
    qualification = _stage(as_alpha_admin, "Qualification")
    assert qualification["follow_up_task_title"] is None

    deal = _deal(as_alpha_admin, name="Quiet deal", account_id=account_id)

    tasks = as_alpha_admin.get(
        "/crm/tasks",
        params={"related_entity_type": "OPPORTUNITY", "related_entity_id": deal["id"]},
    ).json()["data"]
    assert tasks == []


def test_the_follow_up_belongs_to_the_deal_owner_not_the_mover(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """A manager advancing a rep's deal is not volunteering to do the chasing."""
    account_id = _account(as_alpha_admin, "Ownership Ltd")
    deal = _deal(as_alpha_admin, name="Owned deal", account_id=account_id)
    reassigned = as_alpha_admin.patch(
        f"/crm/opportunities/{deal['id']}",
        json={"owner_id": str(alpha.member.user_id)},
    )
    assert reassigned.status_code == 200, reassigned.text

    moved = as_alpha_admin.post(
        f"/crm/opportunities/{deal['id']}/stage",
        json={"stage_id": str(_stage(as_alpha_admin, "Proposal")["id"])},
    )
    assert moved.status_code == 200, moved.text

    tasks = as_alpha_admin.get(
        "/crm/tasks",
        params={"related_entity_type": "OPPORTUNITY", "related_entity_id": deal["id"]},
    ).json()["data"]
    created = next(task for task in tasks if task["title"] == "Follow up on proposal")
    assert str(created["assigned_to_id"]) == str(alpha.member.user_id)
