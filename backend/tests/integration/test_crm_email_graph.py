"""CRM email through Microsoft Graph: permissions, the workflow action, delivery.

Three groups, all against the real database, outbox, dispatcher and RLS:

* **Record visibility.** Composing against, or rendering a template against, a
  record the caller cannot open is refused exactly like a record that does not
  exist — and so is using a colleague's private template.
* **The workflow action.** ``execute_send_templated_email`` sends only what its
  principal could have sent by hand, and refuses rather than guesses.
* **Graph end to end.** The delivery handler runs with the real
  :class:`GraphEmailService` over an ``httpx.MockTransport`` standing in for
  Graph, so the whole path — compose, outbox, worker, Graph request, delivery
  log — is exercised, including a permanent refusal and a transient outage.
"""

from __future__ import annotations

import base64
import json
import urllib.request
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.platform.auth.dependencies import Principal
from app.platform.auth.models import User
from app.platform.authorization.repository import AuthorizationRepository
from app.platform.authorization.service import AuthorizationService, PermissionDeniedError
from app.platform.documents.storage import ObjectStorage, build_storage
from app.platform.email.graph import INLINE_REQUEST_BUDGET_BYTES, GraphEmailService
from app.platform.email.models import EmailDelivery, EmailDeliveryStatus
from app.platform.events.models import EventStatus, OutboxEvent
from app.platform.events.service import (
    EventDispatcher,
    clear_handlers,
    register_handler,
    registered_handlers,
)
from app.products.crm.common import CrmEntityType
from app.products.crm.emails.actions import (
    InvalidEmailActionError,
    NoRecipientError,
    SendTemplatedEmailAction,
    UnresolvedTemplateError,
    execute_send_templated_email,
)
from app.products.crm.emails.delivery import deliver_crm_email_event
from app.products.crm.emails.events import CRM_EMAIL_SEND_REQUESTED
from app.products.crm.emails.models import EmailMessage, EmailStatus
from app.products.crm.shared.relations import UnknownRelatedEntityError
from tests.integration.conftest import (
    ApiSession,
    Tenant,
    membership_id_for,
    revoke_all_roles,
    scope_session_to,
)

pytestmark = pytest.mark.integration

SENDER = "crm@s3k.example.com"


# --- A mocked Microsoft Graph ------------------------------------------------------


class FakeGraph:
    """Entra ID and Graph mail endpoints, answering with a configurable status.

    ``sent`` holds each delivered Graph message resource, with ``attachments``
    filled in for both paths: inline on ``sendMail``, and reassembled from the
    draft's attachment requests and upload-session chunks on the large path.
    """

    def __init__(self, *, send_status: int = 202, graph_code: str | None = None) -> None:
        self.send_status = send_status
        self.graph_code = graph_code
        self.sent: list[dict[str, Any]] = []
        self.draft: dict[str, Any] | None = None
        self.uploads: dict[str, bytearray] = {}
        self.upload_names: dict[str, str] = {}
        self.used_draft_path = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "login.microsoftonline.com" in url:
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        if url.endswith("/sendMail"):
            if self.send_status != 202:
                return httpx.Response(
                    self.send_status, json={"error": {"code": self.graph_code or "Err"}}
                )
            self.sent.append(json.loads(request.content)["message"])
            return httpx.Response(202)
        if request.method == "POST" and url.endswith("/messages"):
            self.used_draft_path = True
            self.draft = {**json.loads(request.content), "attachments": []}
            return httpx.Response(201, json={"id": "draft-1"})
        if url.endswith("/messages/draft-1/attachments") and self.draft is not None:
            self.draft["attachments"].append(json.loads(request.content))
            return httpx.Response(201, json={})
        if url.endswith("/attachments/createUploadSession"):
            item = json.loads(request.content)["AttachmentItem"]
            session = f"https://upload.example/{len(self.uploads)}"
            self.uploads[session] = bytearray()
            self.upload_names[session] = item["name"]
            return httpx.Response(201, json={"uploadUrl": session})
        if request.method == "PUT" and url in self.uploads:
            self.uploads[url].extend(request.content)
            return httpx.Response(200, json={})
        if url.endswith("/messages/draft-1/send") and self.draft is not None:
            for session, content in self.uploads.items():
                self.draft["attachments"].append(
                    {
                        "name": self.upload_names[session],
                        "contentBytes": base64.b64encode(bytes(content)).decode(),
                    }
                )
            self.sent.append(self.draft)
            return httpx.Response(202)
        return httpx.Response(404)


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


def _deliver_through(
    graph: FakeGraph, settings: Settings, *, storage: ObjectStorage | None = None
) -> None:
    configured = settings.model_copy(
        update={
            "microsoft_tenant_id": "tenant",
            "microsoft_client_id": "client",
            "microsoft_client_secret": SecretStr("secret"),
            "microsoft_graph_sender_email": SENDER,
        }
    )
    service = GraphEmailService(configured, transport=httpx.MockTransport(graph.handler))

    async def handler(session: AsyncSession, event: OutboxEvent) -> None:
        await deliver_crm_email_event(session, event, provider=service, storage=storage)

    register_handler(CRM_EMAIL_SEND_REQUESTED, handler, tenant_scoped=True)


@pytest.fixture
def colleague(client: TestClient, integration_settings: Settings) -> ApiSession:
    """A second signed-in session (the shared fixtures are one object)."""
    return ApiSession(client, integration_settings.api_prefix)


def _lead(api: ApiSession, **overrides: object) -> str:
    payload: dict[str, object] = {
        "first_name": "Asha",
        "last_name": "Rao",
        "company": "Zephyr",
        "email": "asha@zephyr.example",
    }
    payload.update(overrides)
    created = api.post("/crm/leads", json=payload)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _template(api: ApiSession, **overrides: object) -> str:
    payload: dict[str, object] = {
        "name": f"Intro {uuid.uuid4().hex[:6]}",
        "subject": "Hello {{record.first_name}}",
        "body_text": "Hi {{record.full_name}}, this is {{sender.name}}.",
        "body_html": "<p>Hi {{record.full_name}}</p>",
    }
    payload.update(overrides)
    created = api.post("/crm/email-templates", json=payload)
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def _principal(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tenant: Tenant,
    user_id: uuid.UUID,
) -> Principal:
    membership_id = await membership_id_for(session_factory, user_id)
    user = await session.get(User, user_id)
    assert user is not None
    granted = await AuthorizationService(AuthorizationRepository(session)).effective_permissions(
        membership_id
    )
    return Principal(
        user=user,
        organization_id=tenant.organization_id,
        membership_id=membership_id,
        permissions=frozenset(granted),
    )


# --- Record visibility on compose and render ----------------------------------------


async def test_a_rep_cannot_email_a_lead_they_cannot_open(
    as_alpha_admin: ApiSession,
    colleague: ApiSession,
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    """The member holds emails.CREATE and leads.VIEW, but not VIEW_ALL."""
    admins_lead = _lead(as_alpha_admin)

    colleague.login(alpha.member.email, organization_id=alpha.organization_id)
    assert colleague.get(f"/crm/leads/{admins_lead}").status_code == 404

    refused = colleague.post(
        "/crm/emails",
        json={
            "subject": "Hello",
            "body_text": "Hi",
            "to_addresses": ["asha@zephyr.example"],
            "related_entity_type": "LEAD",
            "related_entity_id": admins_lead,
            "send": True,
        },
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "unknown_related_entity"


async def test_a_template_cannot_read_a_lead_the_caller_cannot_open(
    as_alpha_admin: ApiSession,
    colleague: ApiSession,
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    admins_lead = _lead(as_alpha_admin)
    shared = _template(as_alpha_admin, is_shared=True)

    colleague.login(alpha.member.email, organization_id=alpha.organization_id)
    refused = colleague.post(
        f"/crm/email-templates/{shared}/render",
        json={"related_entity_type": "LEAD", "related_entity_id": admins_lead},
    )

    assert refused.status_code == 422
    assert "Asha" not in refused.text


async def test_a_rep_can_email_their_own_lead(
    colleague: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    graph = FakeGraph()
    _deliver_through(graph, integration_settings)
    colleague.login(alpha.member.email, organization_id=alpha.organization_id)
    own_lead = _lead(colleague)

    sent = colleague.post(
        "/crm/emails",
        json={
            "subject": "Hello",
            "body_text": "Hi",
            "to_addresses": ["asha@zephyr.example"],
            "related_entity_type": "LEAD",
            "related_entity_id": own_lead,
            "send": True,
        },
    )
    assert sent.status_code == 201, sent.text
    assert (await EventDispatcher(session_factory).drain_once()).succeeded == 1
    assert len(graph.sent) == 1


async def test_composing_with_a_colleagues_private_template_is_refused(
    as_alpha_admin: ApiSession,
    colleague: ApiSession,
    alpha: Tenant,
    clean_outbox: None,
) -> None:
    private = _template(as_alpha_admin, is_shared=False)

    colleague.login(alpha.member.email, organization_id=alpha.organization_id)
    refused = colleague.post(
        "/crm/emails",
        json={
            "subject": "Hello",
            "body_text": "Hi",
            "to_addresses": ["asha@zephyr.example"],
            "template_id": private,
        },
    )
    assert refused.status_code == 404


async def test_a_member_without_email_permission_cannot_send(
    colleague: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    clean_outbox: None,
) -> None:
    # Signed in first: permissions are resolved per request, so the revocation
    # below still applies, and signing in in the same second the tenant was
    # seeded is what the revocation cutoff's whole-second granularity refuses.
    colleague.login(alpha.member.email, organization_id=alpha.organization_id)
    await revoke_all_roles(
        session_factory, await membership_id_for(session_factory, alpha.member.user_id)
    )

    refused = colleague.post(
        "/crm/emails",
        json={"subject": "Hi", "body_text": "Hi", "to_addresses": ["a@b.example"], "send": True},
    )
    templates = colleague.post(
        "/crm/email-templates", json={"name": "x", "subject": "x", "body_text": "x"}
    )

    assert refused.status_code == 403
    assert templates.status_code == 403


async def test_another_tenants_template_is_not_found(
    as_alpha_admin: ApiSession,
    colleague: ApiSession,
    beta: Tenant,
    clean_outbox: None,
) -> None:
    alphas = _template(as_alpha_admin, is_shared=True)

    colleague.login(beta.admin.email, organization_id=beta.organization_id)
    assert colleague.get(f"/crm/email-templates/{alphas}").status_code == 404
    refused = colleague.post(
        "/crm/emails",
        json={
            "subject": "Hello",
            "body_text": "Hi",
            "to_addresses": ["a@b.example"],
            "template_id": alphas,
        },
    )
    assert refused.status_code == 404


# --- Microsoft Graph end to end -------------------------------------------------------


async def test_a_composed_message_reaches_graph_with_its_recipients_and_reply_to(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    graph = FakeGraph()
    _deliver_through(graph, integration_settings)
    lead = _lead(as_alpha_admin)

    created = as_alpha_admin.post(
        "/crm/emails",
        json={
            "subject": "Proposal",
            "body_text": "Plain",
            "body_html": "<p>Rich</p>",
            "to_addresses": ["asha@zephyr.example"],
            "cc_addresses": ["cfo@zephyr.example"],
            "bcc_addresses": ["archive@s3k.example"],
            "related_entity_type": "LEAD",
            "related_entity_id": lead,
            "send": True,
        },
    )
    assert created.status_code == 201, created.text
    assert (await EventDispatcher(session_factory).drain_once()).succeeded == 1

    (message,) = graph.sent
    assert message["subject"] == "Proposal"
    assert message["body"] == {"contentType": "HTML", "content": "<p>Rich</p>"}
    assert message["ccRecipients"] == [{"emailAddress": {"address": "cfo@zephyr.example"}}]
    assert message["bccRecipients"] == [{"emailAddress": {"address": "archive@s3k.example"}}]
    # Sent from the shared mailbox, so replies are steered back to the rep.
    assert message["replyTo"] == [{"emailAddress": {"address": alpha.admin.email}}]

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        stored = await session.get(EmailMessage, uuid.UUID(created.json()["id"]))
        (delivery,) = (await session.execute(select(EmailDelivery))).scalars().all()
    assert stored is not None and stored.status is EmailStatus.SENT
    assert delivery.provider == "graph"
    assert delivery.status is EmailDeliveryStatus.SENT
    assert delivery.provider_message_id == stored.message_id


async def test_a_graph_refusal_dead_letters_and_is_logged_without_secrets(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    graph = FakeGraph(send_status=403, graph_code="ErrorAccessDenied")
    _deliver_through(graph, integration_settings)
    created = as_alpha_admin.post(
        "/crm/emails",
        json={"subject": "S", "body_text": "B", "to_addresses": ["a@b.example"], "send": True},
    )
    assert created.status_code == 201, created.text

    result = await EventDispatcher(session_factory).drain_once()
    assert result.dead == 1

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        stored = await session.get(EmailMessage, uuid.UUID(created.json()["id"]))
        (delivery,) = (await session.execute(select(EmailDelivery))).scalars().all()
    assert stored is not None and stored.status is EmailStatus.FAILED
    assert "ErrorAccessDenied" in (stored.error or "")
    assert delivery.status is EmailDeliveryStatus.FAILED
    assert "secret" not in (delivery.error or "")


async def test_a_graph_outage_is_retried_not_dead_lettered(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    graph = FakeGraph(send_status=503, graph_code="ServiceUnavailable")
    _deliver_through(graph, integration_settings)
    created = as_alpha_admin.post(
        "/crm/emails",
        json={"subject": "S", "body_text": "B", "to_addresses": ["a@b.example"], "send": True},
    )
    assert created.status_code == 201, created.text

    result = await EventDispatcher(session_factory).drain_once()
    assert result.retrying == 1

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        event = (await session.execute(select(OutboxEvent))).scalar_one()
    assert event.status is not EventStatus.DEAD


# --- Attachments -------------------------------------------------------------------------


def _attach_to_draft(api: ApiSession, message_id: str, filename: str, body: bytes) -> None:
    """The browser's three-step upload, against the message being composed."""
    reserved = api.post(
        "/attachments/upload-url",
        json={
            "entity_type": "EMAIL_MESSAGE",
            "entity_id": message_id,
            "filename": filename,
            "content_type": "application/pdf",
            "size_bytes": len(body),
        },
    )
    assert reserved.status_code == 201, reserved.text
    ticket = reserved.json()
    # The URL comes from this application's own pre-signer, pointing at MinIO.
    request = urllib.request.Request(  # noqa: S310
        ticket["upload_url"], data=body, method="PUT", headers=ticket["headers"]
    )
    with urllib.request.urlopen(request) as response:  # noqa: S310
        assert response.status == 200
    confirmed = api.post(f"/attachments/{ticket['attachment']['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text


@pytest.mark.parametrize(
    ("size", "expect_draft_path"),
    [(4096, False), (INLINE_REQUEST_BUDGET_BYTES + 512 * 1024, True)],
    ids=["inline", "upload-session"],
)
async def test_attachments_reach_graph_intact(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
    size: int,
    expect_draft_path: bool,
) -> None:
    storage = build_storage(integration_settings)
    if storage is None:  # pragma: no cover - environment dependent
        pytest.skip("object storage is not configured; attachments cannot be exercised")
    graph = FakeGraph()
    _deliver_through(graph, integration_settings, storage=storage)
    body = b"%PDF-1.7\n" + bytes(range(256)) * (size // 256)

    draft = as_alpha_admin.post(
        "/crm/emails",
        json={"subject": "Contract", "body_text": "Attached.", "to_addresses": ["a@b.example"]},
    )
    assert draft.status_code == 201, draft.text
    message_id = draft.json()["id"]
    _attach_to_draft(as_alpha_admin, message_id, "contract.pdf", body)

    sent = as_alpha_admin.post(f"/crm/emails/{message_id}/send")
    assert sent.status_code == 200, sent.text
    assert (await EventDispatcher(session_factory).drain_once()).succeeded == 1

    assert graph.used_draft_path is expect_draft_path
    (message,) = graph.sent
    (attachment,) = message["attachments"]
    assert attachment["name"] == "contract.pdf"
    assert base64.b64decode(attachment["contentBytes"]) == body


# --- The workflow action ---------------------------------------------------------------


async def test_the_workflow_action_renders_and_sends_through_graph(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    graph = FakeGraph()
    _deliver_through(graph, integration_settings)
    lead = _lead(as_alpha_admin)
    template = _template(as_alpha_admin)

    async with session_factory() as session, session.begin():
        await scope_session_to(session, alpha.organization_id)
        principal = await _principal(session, session_factory, alpha, alpha.admin.user_id)
        message = await execute_send_templated_email(
            session,
            settings=integration_settings,
            principal=principal,
            action=SendTemplatedEmailAction(
                template_id=uuid.UUID(template),
                related_entity_type=CrmEntityType.LEAD,
                related_entity_id=uuid.UUID(lead),
            ),
        )
        message_id = message.id

    assert (await EventDispatcher(session_factory).drain_once()).succeeded == 1
    (sent,) = graph.sent
    assert sent["subject"] == "Hello Asha"
    assert sent["toRecipients"] == [{"emailAddress": {"address": "asha@zephyr.example"}}]
    assert sent["body"]["content"] == "<p>Hi Asha Rao</p>"

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        stored = await session.get(EmailMessage, message_id)
    assert stored is not None
    assert stored.status is EmailStatus.SENT
    assert str(stored.template_id) == template
    assert str(stored.related_entity_id) == lead


async def test_the_workflow_action_cannot_reach_a_hidden_record(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    lead = _lead(as_alpha_admin)
    template = _template(as_alpha_admin, is_shared=True)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        member = await _principal(session, session_factory, alpha, alpha.member.user_id)
        with pytest.raises(UnknownRelatedEntityError):
            await execute_send_templated_email(
                session,
                settings=integration_settings,
                principal=member,
                action=SendTemplatedEmailAction(
                    template_id=uuid.UUID(template),
                    related_entity_type=CrmEntityType.LEAD,
                    related_entity_id=uuid.UUID(lead),
                ),
            )


async def test_the_workflow_action_requires_email_permission(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    lead = _lead(as_alpha_admin)
    template = _template(as_alpha_admin)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        admin = await _principal(session, session_factory, alpha, alpha.admin.user_id)
        stripped = Principal(
            user=admin.user,
            organization_id=admin.organization_id,
            membership_id=admin.membership_id,
            permissions=frozenset(p for p in admin.permissions if not p.startswith("emails.")),
        )
        with pytest.raises(PermissionDeniedError):
            await execute_send_templated_email(
                session,
                settings=integration_settings,
                principal=stripped,
                action=SendTemplatedEmailAction(
                    template_id=uuid.UUID(template),
                    related_entity_type=CrmEntityType.LEAD,
                    related_entity_id=uuid.UUID(lead),
                ),
            )


async def test_the_workflow_action_refuses_unfilled_placeholders(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    lead = _lead(as_alpha_admin)
    template = _template(as_alpha_admin, body_text="Your phone is {{record.phone}}.")

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        admin = await _principal(session, session_factory, alpha, alpha.admin.user_id)
        with pytest.raises(UnresolvedTemplateError) as raised:
            await execute_send_templated_email(
                session,
                settings=integration_settings,
                principal=admin,
                action=SendTemplatedEmailAction(
                    template_id=uuid.UUID(template),
                    related_entity_type=CrmEntityType.LEAD,
                    related_entity_id=uuid.UUID(lead),
                ),
            )
    assert raised.value.details["unresolved"] == ["record.phone"]


async def test_the_workflow_action_needs_somebody_to_send_to(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
    integration_settings: Settings,
    clean_outbox: None,
) -> None:
    lead = _lead(as_alpha_admin, email=None)
    template = _template(as_alpha_admin, subject="Hi", body_text="Hello.", body_html=None)

    async with session_factory() as session:
        await scope_session_to(session, alpha.organization_id)
        admin = await _principal(session, session_factory, alpha, alpha.admin.user_id)
        action = SendTemplatedEmailAction(
            template_id=uuid.UUID(template),
            related_entity_type=CrmEntityType.LEAD,
            related_entity_id=uuid.UUID(lead),
        )
        with pytest.raises(NoRecipientError):
            await execute_send_templated_email(
                session, settings=integration_settings, principal=admin, action=action
            )
        with pytest.raises(InvalidEmailActionError):
            await execute_send_templated_email(
                session,
                settings=integration_settings,
                principal=admin,
                action=SendTemplatedEmailAction(
                    template_id=action.template_id,
                    related_entity_type=action.related_entity_type,
                    related_entity_id=action.related_entity_id,
                    to_addresses=("not-an-address",),
                ),
            )
