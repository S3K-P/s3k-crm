"""Workflow automation (Checkpoint 6): trigger -> conditions -> actions.

Real PostgreSQL and the real outbox dispatcher, for the same reason
``test_outbox.py`` gives: every guarantee this module makes — idempotency,
loop protection, "a rule's action goes through the same validated service a
person's click would" — is a database or a transaction guarantee, and a fake
would only assert this suite's own idea of them.

Grouped by what each set proves:

**Configuration** — CRUD, validation, permissions, tenant isolation. The same
shape ``test_blueprints.py`` uses, since ``workflows`` is authorized exactly
like ``blueprints``.

**End-to-end automation** — a record change through the real API, drained
through the real outbox, and the action's effect (a field, a task, a
notification) checked through the real API of *that* module. This is the
proof no automation-only bypass exists: the assertions are the same ones a
human-driven test of tasks/notifications would make.

**Reliability** — idempotency (the same event redelivered), loop protection
(two workflows that would retrigger each other for ever), and that a
blueprint-refused action fails the run without failing the record's own
already-committed write.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.database import apply_tenant_context
from app.core.tenant import TenantContext
from app.platform.events.models import OutboxEvent
from app.platform.events.service import EventDispatcher, registered_handlers
from app.products.crm.workflows.service import scan_scheduled_workflows
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def as_alpha_rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def as_beta_admin(client: TestClient, integration_settings: Settings, beta: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(beta.admin.email, organization_id=beta.organization_id)
    return session


@pytest_asyncio.fixture
async def outbox(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[None]:
    """Empty the (RLS-exempt, cross-tenant) outbox around each test."""
    async with session_factory() as session:
        await session.execute(text("DELETE FROM platform.outbox_events"))
        await session.commit()
    yield
    async with session_factory() as session:
        await session.execute(text("DELETE FROM platform.outbox_events"))
        await session.commit()


def _dispatcher(session_factory: async_sessionmaker[AsyncSession]) -> EventDispatcher:
    return EventDispatcher(session_factory, batch_size=50, stall_after_seconds=300)


async def _drain(session_factory: async_sessionmaker[AsyncSession], *, passes: int = 1) -> None:
    """Drain the outbox ``passes`` times — a chained workflow action enqueues
    a *new* event that only the next pass will see."""
    dispatcher = _dispatcher(session_factory)
    for _ in range(passes):
        await dispatcher.drain_once()


def _make_workflow(session: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "name": "Test workflow",
        "entity_type": "LEAD",
        "trigger_type": "RECORD_CREATED",
        "conditions": [],
        "actions": [],
    }
    payload.update(overrides)
    response = session.post("/crm/workflows", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _activate(session: ApiSession, workflow_id: str) -> dict:
    response = session.patch(f"/crm/workflows/{workflow_id}", json={"is_active": True})
    assert response.status_code == 200, response.text
    return response.json()


def _stage_id(session: ApiSession, name: str) -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return next(stage["id"] for stage in stages if stage["name"] == name)


def _make_opportunity(session: ApiSession, **overrides: object) -> str:
    account = session.post("/crm/accounts", json={"name": "Deal Co"}).json()
    payload: dict[str, object] = {
        "name": "Deal Co — Platform",
        "account_id": account["id"],
        "stage_id": _stage_id(session, "Qualification"),
        "deal_value": "50000.00",
    }
    payload.update(overrides)
    response = session.post("/crm/opportunities", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- Configuration: CRUD, validation, permissions, tenant isolation --------


def test_a_workflow_is_created_inactive(as_alpha_admin: ApiSession) -> None:
    workflow = _make_workflow(as_alpha_admin, actions=[{"type": "SEND_NOTIFICATION"}])
    assert workflow["is_active"] is False


def test_crud_round_trip(as_alpha_admin: ApiSession) -> None:
    workflow = _make_workflow(as_alpha_admin, name="Round trip")
    workflow_id = workflow["id"]

    fetched = as_alpha_admin.get(f"/crm/workflows/{workflow_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Round trip"

    patched = as_alpha_admin.patch(
        f"/crm/workflows/{workflow_id}", json={"description": "Updated"}
    )
    assert patched.json()["description"] == "Updated"

    assert as_alpha_admin.delete(f"/crm/workflows/{workflow_id}").status_code == 204
    assert as_alpha_admin.get(f"/crm/workflows/{workflow_id}").status_code == 404


def test_duplicate_name_is_refused(as_alpha_admin: ApiSession) -> None:
    _make_workflow(as_alpha_admin, name="Only one of me")
    dupe = as_alpha_admin.post(
        "/crm/workflows",
        json={
            "name": "Only one of me",
            "entity_type": "LEAD",
            "trigger_type": "RECORD_CREATED",
        },
    )
    assert dupe.status_code == 422
    assert dupe.json()["error"]["code"] == "workflow_name_taken"


def test_duplicate_workflow_endpoint_makes_a_deactivated_copy(as_alpha_admin: ApiSession) -> None:
    original = _make_workflow(as_alpha_admin, name="Original")
    _activate(as_alpha_admin, original["id"])

    copy = as_alpha_admin.post(f"/crm/workflows/{original['id']}/duplicate")

    assert copy.status_code == 201
    assert copy.json()["name"] == "Original (Copy)"
    assert copy.json()["is_active"] is False


def test_an_unsupported_condition_operator_is_refused(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/crm/workflows",
        json={
            "name": "Bad operator",
            "entity_type": "LEAD",
            "trigger_type": "RECORD_CREATED",
            "conditions": [{"field_key": "company", "operator": "matches_regex", "value": "x"}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_workflow_configuration"


def test_field_changed_trigger_needs_a_real_column(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/crm/workflows",
        json={
            "name": "Bad field",
            "entity_type": "LEAD",
            "trigger_type": "FIELD_CHANGED",
            "trigger_config": {"field": "not_a_real_column"},
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_workflow_configuration"


def test_change_stage_action_is_refused_off_an_opportunity(as_alpha_admin: ApiSession) -> None:
    """Never a bypass: CHANGE_STAGE only makes sense where a stage exists."""
    response = as_alpha_admin.post(
        "/crm/workflows",
        json={
            "name": "Wrong entity",
            "entity_type": "LEAD",
            "trigger_type": "RECORD_CREATED",
            "actions": [{"type": "CHANGE_STAGE", "stage_name": "Proposal"}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_workflow_configuration"


def test_update_field_cannot_target_a_blueprint_guarded_column(as_alpha_admin: ApiSession) -> None:
    """A workflow must reach ``status`` only through CHANGE_STATUS, never PATCH."""
    response = as_alpha_admin.post(
        "/crm/workflows",
        json={
            "name": "Sneaky status write",
            "entity_type": "LEAD",
            "trigger_type": "RECORD_CREATED",
            "actions": [{"type": "UPDATE_FIELD", "field": "status", "value": "CONVERTED"}],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_workflow_configuration"


def test_a_rep_may_read_workflows_but_not_change_them(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    _make_workflow(as_alpha_admin)
    assert as_alpha_rep.get("/crm/workflows").status_code == 200
    created = as_alpha_rep.post(
        "/crm/workflows",
        json={"name": "Sneaky", "entity_type": "LEAD", "trigger_type": "RECORD_CREATED"},
    )
    assert created.status_code == 403


def test_another_tenants_workflow_cannot_be_read_or_changed(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    workflow = _make_workflow(as_alpha_admin)
    workflow_id = workflow["id"]

    assert as_beta_admin.get(f"/crm/workflows/{workflow_id}").status_code == 404
    assert (
        as_beta_admin.patch(f"/crm/workflows/{workflow_id}", json={"name": "Hijacked"}).status_code
        == 404
    )
    assert as_beta_admin.delete(f"/crm/workflows/{workflow_id}").status_code == 404
    assert as_beta_admin.get("/crm/workflows").json()["data"] == []


# --- End-to-end automation ---------------------------------------------------


async def test_record_created_sends_a_notification(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Welcome new leads",
        trigger_type="RECORD_CREATED",
        # Lead offers `record.full_name`, not `record.name` (see
        # `emails.variables._FIELDS`) — asserted against the resolved text
        # below, not merely a substring an unresolved placeholder would also
        # satisfy.
        actions=[{"type": "SEND_NOTIFICATION", "title": "New lead: {{record.full_name}}"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    created = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Ada", "last_name": "Lovelace", "company": "Analytical Engines"},
    )
    assert created.status_code == 201

    await _drain(session_factory)

    notifications = as_alpha_admin.get("/notifications").json()["data"]
    assert any(item["title"] == "New lead: Ada Lovelace" for item in notifications), notifications

    runs = as_alpha_admin.get(f"/crm/workflows/{workflow['id']}/runs").json()["data"]
    assert len(runs) == 1
    assert runs[0]["status"] == "SUCCEEDED"
    assert runs[0]["trigger"] == "created"


async def test_field_changed_with_a_condition_updates_another_field(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Escalate enterprise leads",
        trigger_type="FIELD_CHANGED",
        trigger_config={"field": "company_size", "to": "ENTERPRISE"},
        conditions=[{"field_key": "industry", "operator": "equals", "value": "Finance"}],
        actions=[{"type": "UPDATE_FIELD", "field": "priority", "value": "HIGH"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    lead = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "company": "Big Bank",
            "industry": "Finance",
            "company_size": "SMB",
        },
    ).json()

    updated = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"company_size": "ENTERPRISE"}
    )
    assert updated.status_code == 200

    await _drain(session_factory)

    refreshed = as_alpha_admin.get(f"/crm/leads/{lead['id']}").json()
    assert refreshed["priority"] == "HIGH"


async def test_field_changed_on_a_numeric_field_matches_regardless_of_formatting(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    """A ``Decimal`` column re-serializes without trailing zeros (``deal_value``
    75000.00 -> JSON ``75000``); the trigger config's ``"75000.00"`` must still
    match it. Found via manual browser verification — see
    ``test_workflow_conditions.py``'s equivalent unit test for the root cause.
    """
    workflow = _make_workflow(
        as_alpha_admin,
        name="Flag large deals",
        entity_type="OPPORTUNITY",
        trigger_type="FIELD_CHANGED",
        trigger_config={"field": "deal_value", "to": "75000.00"},
        actions=[{"type": "UPDATE_FIELD", "field": "forecast_category", "value": "LARGE"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    opportunity_id = _make_opportunity(as_alpha_admin, deal_value="50000.00")
    updated = as_alpha_admin.patch(
        f"/crm/opportunities/{opportunity_id}", json={"deal_value": "75000.00"}
    )
    assert updated.status_code == 200

    await _drain(session_factory)

    refreshed = as_alpha_admin.get(f"/crm/opportunities/{opportunity_id}").json()
    assert refreshed["forecast_category"] == "LARGE"


async def test_field_changed_condition_not_met_does_not_fire(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Escalate enterprise leads (unmet)",
        trigger_type="FIELD_CHANGED",
        trigger_config={"field": "company_size", "to": "ENTERPRISE"},
        conditions=[{"field_key": "industry", "operator": "equals", "value": "Finance"}],
        actions=[{"type": "UPDATE_FIELD", "field": "priority", "value": "HIGH"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    lead = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "company": "Retailer",
            "industry": "Retail",
            "company_size": "SMB",
        },
    ).json()
    as_alpha_admin.patch(f"/crm/leads/{lead['id']}", json={"company_size": "ENTERPRISE"})

    await _drain(session_factory)

    refreshed = as_alpha_admin.get(f"/crm/leads/{lead['id']}").json()
    assert refreshed["priority"] != "HIGH"
    assert as_alpha_admin.get(f"/crm/workflows/{workflow['id']}/runs").json()["data"] == []


async def test_status_changed_creates_a_follow_up_task(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Follow up on qualified leads",
        trigger_type="STATUS_CHANGED",
        trigger_config={"to": "QUALIFIED"},
        actions=[
            {
                # Lead offers `record.full_name`, not `record.name` — Lead has
                # no `name` column, only first_name/last_name (see
                # `emails.variables._FIELDS`). Using the wrong placeholder
                # here once passed silently (an unresolved `{{record.name}}`
                # still contains the literal text "Follow up with"), which is
                # exactly the class of bug this test now asserts against.
                "type": "CREATE_TASK",
                "title": "Follow up with {{record.full_name}}",
                "priority": "HIGH",
            }
        ],
    )
    _activate(as_alpha_admin, workflow["id"])

    lead = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Grace", "last_name": "Hopper", "company": "Hopper Systems"},
    ).json()
    as_alpha_admin.post(f"/crm/leads/{lead['id']}/status", json={"status": "CONTACTED"})
    as_alpha_admin.post(f"/crm/leads/{lead['id']}/status", json={"status": "QUALIFIED"})

    await _drain(session_factory)

    tasks = as_alpha_admin.get("/crm/tasks").json()["data"]
    matching = [t for t in tasks if t["title"] == "Follow up with Grace Hopper"]
    assert len(matching) == 1, f"variable substitution did not resolve: {tasks}"
    assert matching[0]["priority"] == "HIGH"
    assert matching[0]["related_entity_id"] == lead["id"]


async def test_record_created_adds_a_note(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Note new leads",
        trigger_type="RECORD_CREATED",
        actions=[{"type": "CREATE_NOTE", "body": "Auto-created for {{record.full_name}}"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    lead = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Note", "last_name": "Taker", "company": "Acme"}
    ).json()

    await _drain(session_factory)

    notes = as_alpha_admin.get(
        f"/crm/notes?related_entity_type=LEAD&related_entity_id={lead['id']}"
    ).json()["data"]
    assert len(notes) == 1, notes
    assert notes[0]["content"] == "Auto-created for Note Taker"


async def test_record_created_logs_an_activity(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Log activity for new leads",
        trigger_type="RECORD_CREATED",
        actions=[
            {
                "type": "CREATE_ACTIVITY",
                "activity_type": "CALL",
                "subject": "Introductory call with {{record.full_name}}",
            }
        ],
    )
    _activate(as_alpha_admin, workflow["id"])

    lead = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Call", "last_name": "Target", "company": "Acme"}
    ).json()

    await _drain(session_factory)

    activities = as_alpha_admin.get(
        f"/crm/activities?related_entity_type=LEAD&related_entity_id={lead['id']}"
    ).json()["data"]
    assert len(activities) == 1, activities
    assert activities[0]["subject"] == "Introductory call with Call Target"
    assert activities[0]["type"] == "CALL"


async def test_record_created_assigns_a_different_owner(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Reassign new leads",
        trigger_type="RECORD_CREATED",
        actions=[{"type": "ASSIGN_OWNER", "owner_id": str(alpha.member.user_id)}],
    )
    _activate(as_alpha_admin, workflow["id"])

    lead = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Re", "last_name": "Assigned", "company": "Acme"}
    ).json()
    assert lead["owner_id"] != str(alpha.member.user_id), "starts owned by its creator, the admin"

    await _drain(session_factory)

    refreshed = as_alpha_admin.get(f"/crm/leads/{lead['id']}").json()
    assert refreshed["owner_id"] == str(alpha.member.user_id)


async def test_record_created_sends_an_email(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    """SEND_EMAIL queues a real ``EmailMessage`` through the outbox — the same
    path a person's own Send button uses (`EmailService.create_message`,
    ``send=True``). Actual SMTP delivery is a separate, already-tested outbox
    event (`test_email_delivery.py`) and is not re-proven here; this asserts
    the message was composed and queued correctly against the triggering
    record."""
    workflow = _make_workflow(
        as_alpha_admin,
        name="Email new leads",
        trigger_type="RECORD_CREATED",
        actions=[
            {
                "type": "SEND_EMAIL",
                "recipient": {"kind": "OWNER"},
                "subject": "Welcome, {{record.full_name}}",
                "body_text": "Thanks for your interest, {{record.first_name}}.",
            }
        ],
    )
    _activate(as_alpha_admin, workflow["id"])

    lead = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Mail", "last_name": "Recipient", "company": "Acme"}
    ).json()

    await _drain(session_factory)

    messages = as_alpha_admin.get(
        f"/crm/emails?related_entity_type=LEAD&related_entity_id={lead['id']}"
    ).json()["data"]
    assert len(messages) == 1, messages
    assert messages[0]["subject"] == "Welcome, Mail Recipient"
    assert messages[0]["to_addresses"], "must be addressed to someone"
    assert messages[0]["status"] in ("QUEUED", "SENT", "FAILED")


async def test_disabled_workflow_does_not_fire(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Never activated",
        actions=[{"type": "SEND_NOTIFICATION", "title": "Should not appear"}],
    )
    assert workflow["is_active"] is False

    as_alpha_admin.post(
        "/crm/leads", json={"first_name": "No", "last_name": "Fire", "company": "Nowhere"}
    )
    await _drain(session_factory)

    notifications = as_alpha_admin.get("/notifications").json()["data"]
    assert not any("Should not appear" in item["title"] for item in notifications)


async def test_enabling_a_workflow_makes_future_events_fire(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Enable then fire",
        actions=[{"type": "SEND_NOTIFICATION", "title": "Now active"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Now", "last_name": "Active", "company": "Somewhere"}
    )
    await _drain(session_factory)

    notifications = as_alpha_admin.get("/notifications").json()["data"]
    assert any("Now active" in item["title"] for item in notifications)


async def test_a_change_stage_action_is_still_blueprint_guarded(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    """Step 3/14: never a second, weaker-gated write path for a stage move."""
    # A blueprint's ``from_state``/``to_state`` for OPPORTUNITY_STAGE are
    # pipeline stage *ids*, not names — unlike a workflow's own STAGE_CHANGED
    # trigger/CHANGE_STAGE action, which are human-configured by name.
    blueprint = as_alpha_admin.post(
        "/crm/blueprints", json={"name": "No skipping to Closed Won", "field": "OPPORTUNITY_STAGE"}
    ).json()
    transition = as_alpha_admin.post(
        f"/crm/blueprints/{blueprint['id']}/transitions",
        json={
            "to_state": _stage_id(as_alpha_admin, "Closed Won"),
            "from_state": _stage_id(as_alpha_admin, "Negotiation"),
        },
    )
    assert transition.status_code == 201, transition.text
    activated = as_alpha_admin.patch(f"/crm/blueprints/{blueprint['id']}", json={"is_active": True})
    assert activated.status_code == 200, activated.text

    workflow = _make_workflow(
        as_alpha_admin,
        name="Auto-win on discount approval",
        entity_type="OPPORTUNITY",
        trigger_type="FIELD_CHANGED",
        trigger_config={"field": "forecast_category", "to": "APPROVED"},
        actions=[{"type": "CHANGE_STAGE", "stage_name": "Closed Won"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    opportunity_id = _make_opportunity(as_alpha_admin)
    as_alpha_admin.patch(
        f"/crm/opportunities/{opportunity_id}", json={"forecast_category": "APPROVED"}
    )

    await _drain(session_factory)

    # The blueprint refused the jump from Qualification straight to Closed Won
    # (only Negotiation -> Closed Won is described), so the deal never moved —
    # a workflow's action carries no more authority than a person's click.
    opportunity = as_alpha_admin.get(f"/crm/opportunities/{opportunity_id}").json()
    assert opportunity["stage_id"] != _stage_id(as_alpha_admin, "Closed Won")

    runs = as_alpha_admin.get(f"/crm/workflows/{workflow['id']}/runs").json()["data"]
    assert len(runs) == 1
    assert runs[0]["status"] == "FAILED"
    assert runs[0]["actions_failed"] == 1


# --- Reliability: idempotency and loop protection ---------------------------


async def test_a_redelivered_event_does_not_run_the_action_twice(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    workflow = _make_workflow(
        as_alpha_admin,
        name="Once only",
        actions=[{"type": "CREATE_TASK", "title": "Only once"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Once", "last_name": "Only", "company": "Idempotent Inc"}
    )

    async with session_factory() as session:
        event = (await session.execute(select(OutboxEvent))).scalars().one()
        handler = registered_handlers()[event.event_type]

    # Simulate at-least-once redelivery directly: the same event, handled
    # twice, the way it would be if the dispatcher's own completion write
    # were lost between two commits (see platform.events.service's module
    # docstring — this is a documented, expected failure mode, not a bug).
    for _ in range(2):
        async with session_factory() as session:
            await apply_tenant_context(
                session, TenantContext(organization_id=event.organization_id)
            )
            await handler.handle(session, event)
            await session.commit()

    tasks = as_alpha_admin.get("/crm/tasks").json()["data"]
    matching = [t for t in tasks if t["title"] == "Only once"]
    assert len(matching) == 1, "the same event ran the action twice"

    runs = as_alpha_admin.get(f"/crm/workflows/{workflow['id']}/runs").json()["data"]
    assert len(runs) == 1, "a duplicate delivery must not create a second run"


async def test_two_workflows_cannot_loop_forever(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    """Step 13: A sets industry from company_size, B sets company_size from industry."""
    workflow_a = _make_workflow(
        as_alpha_admin,
        name="A: size -> industry",
        trigger_type="FIELD_CHANGED",
        trigger_config={"field": "company_size", "to": "LOOP_A"},
        actions=[{"type": "UPDATE_FIELD", "field": "industry", "value": "LOOP_B"}],
    )
    workflow_b = _make_workflow(
        as_alpha_admin,
        name="B: industry -> size",
        trigger_type="FIELD_CHANGED",
        trigger_config={"field": "industry", "to": "LOOP_B"},
        actions=[{"type": "UPDATE_FIELD", "field": "company_size", "value": "LOOP_A"}],
    )
    _activate(as_alpha_admin, workflow_a["id"])
    _activate(as_alpha_admin, workflow_b["id"])

    lead = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Loop", "last_name": "Test", "company": "Cycle Co"}
    ).json()
    as_alpha_admin.patch(f"/crm/leads/{lead['id']}", json={"company_size": "LOOP_A"})

    # Each pass only advances the chain by one hop; drain well past the
    # configured depth limit to prove it actually stops rather than merely
    # being slow to loop.
    await _drain(session_factory, passes=20)

    runs_a = as_alpha_admin.get(f"/crm/workflows/{workflow_a['id']}/runs").json()["data"]
    runs_b = as_alpha_admin.get(f"/crm/workflows/{workflow_b['id']}/runs").json()["data"]
    total_runs = len(runs_a) + len(runs_b)

    assert total_runs > 1, "the chain should hop at least a few times"
    assert total_runs < 20, "the chain must be depth-limited, not merely rare"


# --- Scheduled automation -----------------------------------------------------


async def test_a_scheduled_rule_fires_once_for_an_overdue_opportunity(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    opportunity_id = _make_opportunity(
        as_alpha_admin, expected_close_date=(dt.date.today() - dt.timedelta(days=1)).isoformat()
    )
    workflow = _make_workflow(
        as_alpha_admin,
        name="Close date passed",
        entity_type="OPPORTUNITY",
        trigger_type="SCHEDULED",
        trigger_config={"date_field": "expected_close_date", "offset_minutes": 0},
        actions=[{"type": "SEND_NOTIFICATION", "title": "Close date passed"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    now = dt.datetime.now(dt.UTC)
    fired_first = await scan_scheduled_workflows(session_factory, now=now)
    fired_second = await scan_scheduled_workflows(session_factory, now=now)

    assert fired_first == 1
    assert fired_second == 0, "the same day must not fire the same record twice"

    notifications = as_alpha_admin.get("/notifications").json()["data"]
    assert any("Close date passed" in item["title"] for item in notifications)
    assert opportunity_id  # the opportunity itself is untouched by this action


async def test_a_task_due_rule_fires_for_an_overdue_task(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    outbox: None,
) -> None:
    overdue = as_alpha_admin.post(
        "/crm/tasks",
        json={
            "title": "Overdue task",
            "due_date": (dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).isoformat(),
        },
    )
    assert overdue.status_code == 201, overdue.text

    workflow = _make_workflow(
        as_alpha_admin,
        name="Task overdue alert",
        entity_type="TASK",
        trigger_type="TASK_DUE",
        trigger_config={"offset_minutes": 0},
        actions=[{"type": "SEND_NOTIFICATION", "title": "A task is overdue"}],
    )
    _activate(as_alpha_admin, workflow["id"])

    fired = await scan_scheduled_workflows(session_factory, now=dt.datetime.now(dt.UTC))

    assert fired == 1
    notifications = as_alpha_admin.get("/notifications").json()["data"]
    assert any("A task is overdue" in item["title"] for item in notifications)
