"""Checkpoint 3: unified timelines for Contact and Opportunity, the new
task/email/note sources shared with Account's, calls' duration, tasks'
due-date quick-view filters, and the activity attachment enablement.

Every assertion goes through HTTP against real PostgreSQL, for the same
reason ``test_account_relationships.py`` does: a service-level test would
prove a query compiles, not that the route enforces tenant isolation and
record-level visibility for a real caller.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.platform.email.provider import DeliveryReceipt, OutboundEmail
from app.platform.events.service import (
    EventDispatcher,
    clear_handlers,
    register_handler,
    registered_handlers,
)
from app.products.crm.emails.delivery import deliver_crm_email_event
from app.products.crm.emails.events import CRM_EMAIL_SEND_REQUESTED
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


# --- Helpers ------------------------------------------------------------


def _stage_id(session: ApiSession, name: str) -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


def _account(session: ApiSession, name: str = "Zephyr Systems") -> str:
    created = session.post("/crm/accounts", json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _contact(session: ApiSession, account_id: str, first: str, last: str) -> str:
    created = session.post(
        "/crm/contacts",
        json={"first_name": first, "last_name": last, "account_id": account_id},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _deal(session: ApiSession, account_id: str, name: str, **overrides: object) -> str:
    body: dict[str, object] = {
        "name": name,
        "account_id": account_id,
        "stage_id": _stage_id(session, "Qualification"),
    }
    body.update(overrides)
    created = session.post("/crm/opportunities", json=body)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _task(session: ApiSession, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"title": "Send proposal"}
    body.update(overrides)
    created = session.post("/crm/tasks", json=body)
    assert created.status_code == 201, created.text
    return dict(created.json())


def _note(session: ApiSession, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {"content": "Called, left a voicemail."}
    body.update(overrides)
    created = session.post("/crm/notes", json=body)
    assert created.status_code == 201, created.text
    return dict(created.json())


def _kinds(entries: list[dict[str, object]]) -> set[str]:
    return {str(entry["kind"]) for entry in entries}


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """A second signed-in session for the plain ``User`` of alpha.

    Mirrors the fixture in ``test_account_relationships.py`` — these tests
    need two people signed in on the same organization at once.
    """
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


# --- Contact timeline -----------------------------------------------------


def test_contact_timeline_scopes_deals_by_primary_contact_not_account(
    as_alpha_admin: ApiSession,
) -> None:
    """A contact's timeline shows deals it is the primary contact for, not
    every deal on the account it belongs to — the account has its own
    timeline for that broader view."""
    account_id = _account(as_alpha_admin)
    contact_id = _contact(as_alpha_admin, account_id, "Priya", "Shah")
    other_contact_id = _contact(as_alpha_admin, account_id, "Rahul", "Sharma")

    mine = _deal(
        as_alpha_admin, account_id, "Priya's deal", primary_contact_id=contact_id
    )
    _deal(as_alpha_admin, account_id, "Rahul's deal", primary_contact_id=other_contact_id)

    timeline = as_alpha_admin.get(f"/crm/contacts/{contact_id}/timeline")

    assert timeline.status_code == 200
    body = timeline.json()
    assert any(entry["entity_id"] == mine and entry["kind"] == "deal_created" for entry in body)
    assert not any(
        entry["kind"] == "deal_created" and entry["entity_id"] != mine for entry in body
    )


def test_contact_timeline_includes_tasks_and_a_completion_entry(
    as_alpha_admin: ApiSession,
) -> None:
    account_id = _account(as_alpha_admin)
    contact_id = _contact(as_alpha_admin, account_id, "Priya", "Shah")
    task = _task(
        as_alpha_admin,
        title="Follow up call",
        related_entity_type="CONTACT",
        related_entity_id=contact_id,
    )

    completed = as_alpha_admin.post(
        f"/crm/tasks/{task['id']}/status", json={"status": "COMPLETED"}
    )
    assert completed.status_code == 200, completed.text

    timeline = as_alpha_admin.get(f"/crm/contacts/{contact_id}/timeline").json()

    kinds = _kinds(timeline)
    assert "task_created" in kinds
    assert "task_completed" in kinds


def test_contact_timeline_notes_respect_private_visibility(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """A private note joins the timeline for its author and is invisible to
    everyone else — the identical rule the Notes tab enforces, reused rather
    than re-derived (Checkpoint 3).

    The contact is owned by ``rep`` (so ``rep`` can see the *contact* itself
    via ``contacts.VIEW_ALL``-free ownership) and the note is authored by
    ``as_alpha_admin`` (who reaches it through ``VIEW_ALL``) — isolating "can
    this caller see the note" from "can this caller see the record at all",
    which a same-owner setup would conflate.
    """
    account_id = _account(rep, "Shared Account")
    contact_id = _contact(rep, account_id, "Priya", "Shah")

    _note(
        as_alpha_admin,
        content="Confidential renewal risk",
        visibility="PRIVATE",
        related_entity_type="CONTACT",
        related_entity_id=contact_id,
    )

    author_view = as_alpha_admin.get(f"/crm/contacts/{contact_id}/timeline").json()
    other_view = rep.get(f"/crm/contacts/{contact_id}/timeline").json()

    assert "note_added" in _kinds(author_view)
    assert "note_added" not in _kinds(other_view)
    # Content is never echoed onto the shared timeline, private or not.
    assert not any("renewal" in str(entry).lower() for entry in author_view)


def test_contact_timeline_random_id_is_404(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get(f"/crm/contacts/{uuid.uuid4()}/timeline")
    assert response.status_code == 404


# --- Opportunity timeline ---------------------------------------------------


def test_opportunity_timeline_includes_its_own_creation_and_stage_moves(
    as_alpha_admin: ApiSession,
) -> None:
    account_id = _account(as_alpha_admin)
    deal_id = _deal(as_alpha_admin, account_id, "Platform rollout")
    discovery = _stage_id(as_alpha_admin, "Discovery")
    moved = as_alpha_admin.post(
        f"/crm/opportunities/{deal_id}/stage", json={"stage_id": discovery}
    )
    assert moved.status_code == 200, moved.text

    timeline = as_alpha_admin.get(f"/crm/opportunities/{deal_id}/timeline")

    assert timeline.status_code == 200
    body = timeline.json()
    assert all(
        entry["entity_id"] == deal_id or entry["entity_type"] != "OPPORTUNITY" for entry in body
    )
    kinds = _kinds(body)
    assert "deal_created" in kinds
    assert "stage_changed" in kinds


def test_opportunity_timeline_does_not_leak_a_sibling_deals_stage_moves(
    as_alpha_admin: ApiSession,
) -> None:
    account_id = _account(as_alpha_admin)
    deal_id = _deal(as_alpha_admin, account_id, "Deal A")
    sibling_id = _deal(as_alpha_admin, account_id, "Deal B")
    discovery = _stage_id(as_alpha_admin, "Discovery")
    as_alpha_admin.post(f"/crm/opportunities/{sibling_id}/stage", json={"stage_id": discovery})

    timeline = as_alpha_admin.get(f"/crm/opportunities/{deal_id}/timeline").json()

    assert not any(entry["entity_id"] == sibling_id for entry in timeline)


def test_opportunity_timeline_random_id_is_404(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get(f"/crm/opportunities/{uuid.uuid4()}/timeline")
    assert response.status_code == 404


# --- Sent email joins the timeline, drafts do not --------------------------


class _StubProvider:
    def __init__(self) -> None:
        self.name = "stub"
        self.sent: list[OutboundEmail] = []

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        self.sent.append(message)
        return DeliveryReceipt(message_id=f"stub-{len(self.sent)}", provider="stub")


@pytest.fixture(autouse=True)
def _isolate_handlers() -> Iterator[None]:
    """Swap the real event-handler registry out and put it back (mirrors
    ``test_crm_email.py``): it is process-global, so a stub registered here
    would otherwise leak into whichever test runs next."""
    existing = registered_handlers()
    clear_handlers()
    yield
    clear_handlers()
    for handler in existing.values():
        register_handler(
            handler.event_type, handler.handle, tenant_scoped=handler.tenant_scoped
        )


@pytest_asyncio.fixture
async def clean_outbox(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    async def wipe() -> None:
        async with session_factory() as session:
            await session.execute(text("DELETE FROM platform.outbox_events"))
            await session.commit()

    await wipe()
    yield
    await wipe()


async def test_a_sent_email_joins_the_timeline_but_a_draft_does_not(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    clean_outbox: None,
) -> None:
    provider = _StubProvider()

    async def handler(session: AsyncSession, event: object) -> None:
        await deliver_crm_email_event(session, event, provider=provider, storage=None)  # type: ignore[arg-type]

    register_handler(CRM_EMAIL_SEND_REQUESTED, handler, tenant_scoped=True)

    account_id = _account(as_alpha_admin)

    draft = as_alpha_admin.post(
        "/crm/emails",
        json={
            "subject": "Draft only",
            "body_text": "Not sent yet.",
            "to_addresses": ["ravi@zephyr.example"],
            "related_entity_type": "ACCOUNT",
            "related_entity_id": account_id,
        },
    )
    assert draft.status_code == 201, draft.text

    sent = as_alpha_admin.post(
        "/crm/emails",
        json={
            "subject": "Your proposal",
            "body_text": "Attached is the proposal.",
            "to_addresses": ["ravi@zephyr.example"],
            "related_entity_type": "ACCOUNT",
            "related_entity_id": account_id,
            "send": True,
        },
    )
    assert sent.status_code == 201, sent.text

    result = await EventDispatcher(session_factory).drain_once()
    assert result.succeeded == 1

    timeline = as_alpha_admin.get(f"/crm/accounts/{account_id}/timeline").json()
    email_titles = [entry["title"] for entry in timeline if entry["kind"] == "email_sent"]

    assert any("Your proposal" in title for title in email_titles)
    assert not any("Draft only" in title for title in email_titles)


# --- Account timeline: the new task/email sources ---------------------------


def test_account_timeline_includes_task_created_and_completed(
    as_alpha_admin: ApiSession,
) -> None:
    account_id = _account(as_alpha_admin)
    task = _task(
        as_alpha_admin,
        title="Prepare contract",
        related_entity_type="ACCOUNT",
        related_entity_id=account_id,
    )
    as_alpha_admin.post(f"/crm/tasks/{task['id']}/status", json={"status": "COMPLETED"})

    timeline = as_alpha_admin.get(f"/crm/accounts/{account_id}/timeline").json()

    kinds = _kinds(timeline)
    assert "task_created" in kinds
    assert "task_completed" in kinds


def test_account_timeline_notes_are_included_and_visibility_scoped(
    rep: ApiSession, as_alpha_admin: ApiSession
) -> None:
    """A TEAM note is shared, not private, so both readers see it. The
    account is owned by ``rep`` and the note is authored by
    ``as_alpha_admin`` (reaching the account through ``accounts.VIEW_ALL``),
    so the assertion is genuinely about note visibility rather than about
    which of the two can see the account at all."""
    account_id = _account(rep, "Shared Account 2")
    _note(
        as_alpha_admin,
        content="Team-visible context",
        visibility="TEAM",
        related_entity_type="ACCOUNT",
        related_entity_id=account_id,
    )

    admin_view = as_alpha_admin.get(f"/crm/accounts/{account_id}/timeline").json()
    rep_view = rep.get(f"/crm/accounts/{account_id}/timeline").json()

    assert "note_added" in _kinds(admin_view)
    assert "note_added" in _kinds(rep_view)


# --- Calls: a duration field -------------------------------------------------


def test_a_call_can_record_its_duration(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post(
        "/crm/activities",
        json={
            "type": "CALL",
            "subject": "Discovery call",
            "status": "COMPLETED",
            "outcome": "Interested, wants a proposal",
            "duration_minutes": 24,
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["duration_minutes"] == 24


def test_call_duration_rejects_a_negative_value(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post(
        "/crm/activities",
        json={"type": "CALL", "subject": "Bad call", "duration_minutes": -5},
    )

    assert created.status_code == 422


# --- Tasks: overdue / upcoming quick views ----------------------------------


def test_tasks_due_before_excludes_a_task_with_no_due_date(
    as_alpha_admin: ApiSession,
) -> None:
    _task(as_alpha_admin, title="No due date")
    overdue_task = _task(
        as_alpha_admin,
        title="Was due yesterday",
        due_date=(dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).isoformat(),
    )

    listed = as_alpha_admin.get(
        "/crm/tasks",
        params={
            "open_only": "true",
            "due_before": dt.datetime.now(dt.UTC).isoformat(),
        },
    )

    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()["data"]}
    assert overdue_task["id"] in ids
    assert len(ids) == 1


def test_tasks_due_after_selects_only_future_due_dates(as_alpha_admin: ApiSession) -> None:
    upcoming_task = _task(
        as_alpha_admin,
        title="Due next week",
        due_date=(dt.datetime.now(dt.UTC) + dt.timedelta(days=7)).isoformat(),
    )
    _task(
        as_alpha_admin,
        title="Was due yesterday",
        due_date=(dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).isoformat(),
    )

    listed = as_alpha_admin.get(
        "/crm/tasks",
        params={"due_after": dt.datetime.now(dt.UTC).isoformat()},
    )

    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()["data"]}
    assert upcoming_task["id"] in ids
    assert all(row["id"] == upcoming_task["id"] for row in listed.json()["data"])


# --- Attachments: an activity is now an attachable entity -------------------


def test_a_file_can_be_reserved_against_an_activity(
    as_alpha_admin: ApiSession, integration_settings: Settings
) -> None:
    if not integration_settings.storage_configured:
        pytest.skip(
            "object storage is not configured; run `docker compose up -d minio "
            "minio-init` and set STORAGE_* in backend/.env"
        )

    activity = as_alpha_admin.post(
        "/crm/activities",
        json={"type": "CALL", "subject": "Call to attach a recording to"},
    )
    assert activity.status_code == 201, activity.text

    reserved = as_alpha_admin.post(
        "/attachments/upload-url",
        json={
            "entity_type": "ACTIVITY",
            "entity_id": activity.json()["id"],
            "filename": "recording.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
        },
    )

    assert reserved.status_code == 201, reserved.text


def test_a_file_cannot_be_attached_to_another_tenants_activity(
    api: ApiSession, alpha: Tenant, beta: Tenant, integration_settings: Settings
) -> None:
    if not integration_settings.storage_configured:
        pytest.skip(
            "object storage is not configured; run `docker compose up -d minio "
            "minio-init` and set STORAGE_* in backend/.env"
        )

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    activity = api.post(
        "/crm/activities", json={"type": "CALL", "subject": "Alpha's call"}
    )
    assert activity.status_code == 201, activity.text
    activity_id = activity.json()["id"]

    api.login(beta.admin.email, organization_id=beta.organization_id)
    reserved = api.post(
        "/attachments/upload-url",
        json={
            "entity_type": "ACTIVITY",
            "entity_id": activity_id,
            "filename": "recording.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
        },
    )

    assert reserved.status_code == 404
