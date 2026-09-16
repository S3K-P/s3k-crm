"""Notification emails for the four CRM events the roadmap names (P4-W27-BE-03).

Task assigned, task completed, lead qualified, opportunity won. Each raises an
in-app notification for the person it concerns and enqueues its email twin on
the outbox, which the worker delivers (here, to a stub standing in for
Microsoft Graph). Nobody is notified of their own action, and nothing leaks
across tenants.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.platform.email.models import EmailDelivery
from app.platform.email.provider import DeliveryReceipt, OutboundEmail
from app.platform.email.service import EMAIL_REQUESTED, deliver_email_event
from app.platform.email.templates import NOTIFICATION
from app.platform.events.models import OutboxEvent
from app.platform.events.service import (
    EventDispatcher,
    clear_handlers,
    register_handler,
    registered_handlers,
)
from tests.integration.conftest import ApiSession, Tenant, scope_session_to

pytestmark = pytest.mark.integration


class StubProvider:
    def __init__(self) -> None:
        self.name = "stub"
        self.sent: list[OutboundEmail] = []

    async def send(self, message: OutboundEmail) -> DeliveryReceipt:
        self.sent.append(message)
        return DeliveryReceipt(message_id=f"stub-{len(self.sent)}", provider=self.name)


@pytest.fixture(autouse=True)
def _isolate_handlers() -> Iterator[None]:
    existing = registered_handlers()
    clear_handlers()
    yield
    clear_handlers()
    for handler in existing.values():
        register_handler(
            handler.event_type, handler.handle, tenant_scoped=handler.tenant_scoped
        )


@pytest.fixture
def provider() -> StubProvider:
    stub = StubProvider()

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        await deliver_email_event(session, event, provider=stub)

    register_handler(EMAIL_REQUESTED, handler, tenant_scoped=True)
    return stub


@pytest_asyncio.fixture(autouse=True)
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


@pytest.fixture
def member_session(client: TestClient, integration_settings: Settings) -> ApiSession:
    """A second signed-in session; the shared fixtures are one object."""
    return ApiSession(client, integration_settings.api_prefix)


def _notifications(session: ApiSession) -> list[dict[str, object]]:
    listed = session.get("/notifications")
    assert listed.status_code == 200, listed.text
    return list(listed.json()["data"])


async def _drain(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await EventDispatcher(session_factory).drain_once()


# --- Task assigned ---------------------------------------------------------------


async def test_assigning_a_task_to_a_colleague_notifies_and_emails_them(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    provider: StubProvider,
) -> None:
    created = as_alpha_admin.post(
        "/crm/tasks",
        json={
            "title": "Call Zephyr back",
            "assigned_to_id": str(alpha.member.user_id),
            "owner_id": str(alpha.member.user_id),
        },
    )
    assert created.status_code == 201, created.text

    member_session.login(alpha.member.email, organization_id=alpha.organization_id)
    (notification,) = _notifications(member_session)
    assert notification["kind"] == "TASK_ASSIGNED"
    assert notification["title"] == "Task assigned to you: Call Zephyr back"
    assert notification["entity_id"] == created.json()["id"]

    await _drain(session_factory)
    (message,) = provider.sent
    assert message.to_address == alpha.member.email
    assert message.subject == "Task assigned to you: Call Zephyr back"
    assert f"{integration_settings.public_app_url.rstrip('/')}/tasks" in message.text_body

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        (delivery,) = (await session.execute(select(EmailDelivery))).scalars().all()
    assert delivery.template == NOTIFICATION
    assert delivery.organization_id == alpha.organization_id


async def test_assigning_a_task_to_yourself_is_silent(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    created = as_alpha_admin.post(
        "/crm/tasks",
        json={"title": "Note to self", "assigned_to_id": str(alpha.admin.user_id)},
    )
    assert created.status_code == 201, created.text

    assert _notifications(as_alpha_admin) == []
    await _drain(session_factory)
    assert provider.sent == []


async def test_reassigning_a_task_notifies_the_new_assignee_once(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    created = as_alpha_admin.post("/crm/tasks", json={"title": "Prepare demo"})
    task_id = created.json()["id"]

    moved = as_alpha_admin.patch(
        f"/crm/tasks/{task_id}", json={"assigned_to_id": str(alpha.manager.user_id)}
    )
    assert moved.status_code == 200, moved.text
    # An unrelated edit afterwards must not re-notify.
    edited = as_alpha_admin.patch(f"/crm/tasks/{task_id}", json={"description": "Slides"})
    assert edited.status_code == 200, edited.text

    await _drain(session_factory)
    assert [message.to_address for message in provider.sent] == [alpha.manager.email]


# --- Task completed ---------------------------------------------------------------


async def test_completing_a_colleagues_task_notifies_its_creator(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    created = as_alpha_admin.post(
        "/crm/tasks",
        json={
            "title": "Send contract",
            "assigned_to_id": str(alpha.member.user_id),
            "owner_id": str(alpha.member.user_id),
        },
    )
    task_id = created.json()["id"]

    member_session.login(alpha.member.email, organization_id=alpha.organization_id)
    done = member_session.post(f"/crm/tasks/{task_id}/status", json={"status": "COMPLETED"})
    assert done.status_code == 200, done.text

    kinds = [n["kind"] for n in _notifications(as_alpha_admin)]
    assert kinds == ["TASK_COMPLETED"]

    await _drain(session_factory)
    recipients = sorted(message.to_address for message in provider.sent)
    assert recipients == sorted([alpha.member.email, alpha.admin.email])


# --- Lead qualified ----------------------------------------------------------------


async def test_qualifying_a_colleagues_lead_notifies_its_owner(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    lead = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Asha",
            "last_name": "Rao",
            "company": "Zephyr",
            "owner_id": str(alpha.member.user_id),
        },
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]

    for status in ("CONTACTED", "QUALIFIED"):
        moved = as_alpha_admin.post(f"/crm/leads/{lead_id}/status", json={"status": status})
        assert moved.status_code == 200, moved.text

    member_session.login(alpha.member.email, organization_id=alpha.organization_id)
    (notification,) = _notifications(member_session)
    assert notification["kind"] == "LEAD_QUALIFIED"
    assert notification["title"] == "Lead qualified: Asha Rao"

    await _drain(session_factory)
    (message,) = provider.sent
    assert message.to_address == alpha.member.email
    assert f"/leads/{lead_id}" in message.text_body


async def test_qualifying_your_own_lead_is_silent(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Own", "last_name": "Lead"}
    ).json()["id"]
    for status in ("CONTACTED", "QUALIFIED"):
        as_alpha_admin.post(f"/crm/leads/{lead_id}/status", json={"status": status})

    assert _notifications(as_alpha_admin) == []
    await _drain(session_factory)
    assert provider.sent == []


# --- Opportunity won ---------------------------------------------------------------


async def test_winning_a_colleagues_opportunity_notifies_its_owner(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    stages = as_alpha_admin.get("/crm/opportunities/stages").json()
    first = next(s for s in stages if not s["is_won"] and not s["is_lost"])
    won = next(s for s in stages if s["is_won"])
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Zephyr Ltd"}).json()["id"]
    opportunity = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Zephyr rollout",
            "account_id": account,
            "stage_id": first["id"],
            "owner_id": str(alpha.member.user_id),
            "deal_value": "12500.00",
            "currency": "USD",
        },
    )
    assert opportunity.status_code == 201, opportunity.text
    opportunity_id = opportunity.json()["id"]

    closed = as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage", json={"stage_id": won["id"]}
    )
    assert closed.status_code == 200, closed.text

    member_session.login(alpha.member.email, organization_id=alpha.organization_id)
    (notification,) = _notifications(member_session)
    assert notification["kind"] == "OPPORTUNITY_WON"

    await _drain(session_factory)
    (message,) = provider.sent
    assert message.subject == "Opportunity won: Zephyr rollout"
    assert "USD 12,500.00" in message.text_body
    assert f"/opportunities/{opportunity_id}" in message.text_body


# --- Isolation --------------------------------------------------------------------


async def test_a_notification_email_stays_inside_its_tenant(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    beta: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    as_alpha_admin.post(
        "/crm/tasks",
        json={"title": "Alpha only", "assigned_to_id": str(alpha.member.user_id)},
    )
    await _drain(session_factory)
    assert len(provider.sent) == 1

    async with session_factory() as session:
        await scope_session_to(session, beta.organization_id)
        beta_deliveries = (await session.execute(select(EmailDelivery))).scalars().all()
        beta_notifications = await session.scalar(
            text("SELECT count(*) FROM platform.notifications")
        )
    assert beta_deliveries == []
    assert beta_notifications == 0


async def test_assigning_to_someone_outside_the_organization_emails_nobody(
    as_alpha_admin: ApiSession,
    beta: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    provider: StubProvider,
) -> None:
    """The address comes from this organization's member directory, never the caller."""
    created = as_alpha_admin.post(
        "/crm/tasks",
        json={"title": "Stray", "assigned_to_id": str(beta.admin.user_id)},
    )
    assert created.status_code in (201, 422), created.text

    await _drain(session_factory)
    assert all(message.to_address != beta.admin.email for message in provider.sent)


