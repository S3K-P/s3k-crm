"""Email routes: compose, send, read a conversation, manage templates.

Three groups of endpoints on two routers, mounted at ``/crm/emails`` and
``/crm/email-templates``.

**Sending takes ``CREATE``, not a permission of its own.** Composing a message
and sending it are the same act from the user's side — the composer has one
button — and splitting them would create a role that may write mail it cannot
send, which is a state nobody asked for. What ``EDIT`` governs is changing a
draft somebody already saved.

**Every response goes through :func:`_present`**, which is where BCC redaction
happens. Doing it in the router rather than the schema is deliberate: the rule
depends on the *caller*, and a schema does not know who is reading it. One
function, applied at every exit, so a new endpoint cannot leak the field by
forgetting a step — the only way to build a response is to call it.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.config import Settings, get_settings
from app.core.database import DbSession
from app.core.exceptions import NotFoundError
from app.platform.auth.dependencies import Principal, require_permission
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.common import CrmEntityType
from app.products.crm.emails.models import (
    EmailDirection,
    EmailMessage,
    EmailStatus,
    EmailTemplate,
)
from app.products.crm.emails.policies import (
    MODULE,
    may_read_template,
    may_see_blind_copies,
    readable_messages,
)
from app.products.crm.emails.schemas import (
    EmailMessageCreate,
    EmailMessageResponse,
    EmailMessageUpdate,
    EmailTemplateCreate,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    EmailThreadDetailResponse,
    EmailThreadResponse,
    TemplateRenderRequest,
    TemplateRenderResponse,
)
from app.products.crm.emails.service import EmailService
from app.products.crm.emails.templates_service import EmailTemplateService
from app.products.crm.emails.variables import offered_placeholders
from app.products.crm.shared.pagination import Page, PageParams, page_params

router = APIRouter()
templates_router = APIRouter()

PageParamsDep = Annotated[PageParams, Depends(page_params)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_service(session: DbSession, settings: SettingsDep) -> EmailService:
    return EmailService(session, settings=settings)


def get_template_service(session: DbSession) -> EmailTemplateService:
    return EmailTemplateService(session)


ServiceDep = Annotated[EmailService, Depends(get_service)]
TemplateServiceDep = Annotated[EmailTemplateService, Depends(get_template_service)]

Viewer = Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.VIEW))]
Composer = Annotated[
    Principal, Depends(require_permission(MODULE, PermissionAction.CREATE))
]
Editor = Annotated[Principal, Depends(require_permission(MODULE, PermissionAction.EDIT))]
Remover = Annotated[
    Principal, Depends(require_permission(MODULE, PermissionAction.DELETE))
]


def _present(
    message: EmailMessage, principal: Principal, *, attachment_count: int = 0
) -> EmailMessageResponse:
    """One message, with the blind-copy list stripped unless it may be seen.

    ``bcc_count`` is always populated and ``bcc_addresses`` sometimes is, which
    is the distinction the schema exists to carry: a colleague can tell that a
    message had two blind copies — worth knowing when reading a conversation —
    without learning who they were.
    """
    response = EmailMessageResponse.model_validate(message)
    response.bcc_count = len(message.bcc_addresses)
    if not may_see_blind_copies(principal, message):
        response.bcc_addresses = None
    response.attachment_count = attachment_count
    return response


# --- Messages ---------------------------------------------------------------


@router.get("", response_model=Page[EmailMessageResponse])
async def list_messages(
    principal: Viewer,
    service: ServiceDep,
    params: PageParamsDep,
    thread_id: Annotated[uuid.UUID | None, Query()] = None,
    related_entity_type: Annotated[CrmEntityType | None, Query()] = None,
    related_entity_id: Annotated[uuid.UUID | None, Query()] = None,
    message_status: Annotated[EmailStatus | None, Query(alias="status")] = None,
    direction: Annotated[EmailDirection | None, Query()] = None,
    search: Annotated[
        str | None, Query(max_length=200, description="Subject or recipient.")
    ] = None,
) -> Page[EmailMessageResponse]:
    """Messages the caller may see, newest first.

    Another user's drafts are excluded by the query itself, so they are never
    fetched and never counted.
    """
    filters = service.build_message_filters(
        readable=readable_messages(principal.user_id),
        thread_id=thread_id,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        message_status=message_status,
        direction=direction,
        search=search,
    )
    items, total = await service.list_messages(
        principal.organization_id, params=params, filters=filters
    )
    counts = await service.attachment_counts(principal.organization_id, items)
    return Page.build(
        [
            _present(item, principal, attachment_count=counts.get(item.id, 0))
            for item in items
        ],
        total=total,
        params=params,
    )


@router.post("", response_model=EmailMessageResponse, status_code=status.HTTP_201_CREATED)
async def compose_message(
    payload: EmailMessageCreate,
    principal: Composer,
    service: ServiceDep,
) -> EmailMessageResponse:
    """Save a draft, or compose and send.

    The sender's identity is taken from the authenticated principal, never from
    the body: a caller must not be able to send mail that claims to be from a
    colleague.
    """
    sender_address, sender_name = await service.sender_identity(
        principal.organization_id, principal.user_id
    )
    message = await service.create_message(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        sender_address=sender_address,
        sender_name=sender_name,
        values=payload.model_dump(exclude_unset=True),
        principal=principal,
    )
    return _present(message, principal)


@router.get("/threads", response_model=Page[EmailThreadResponse])
async def list_threads(
    principal: Viewer,
    service: ServiceDep,
    params: PageParamsDep,
    related_entity_type: Annotated[CrmEntityType | None, Query()] = None,
    related_entity_id: Annotated[uuid.UUID | None, Query()] = None,
) -> Page[EmailThreadResponse]:
    """Conversations, most recently active first."""
    filters = service.build_thread_filters(
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
    )
    items, total = await service.list_threads(
        principal.organization_id, params=params, filters=filters
    )
    return Page.build(
        [EmailThreadResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@router.get("/threads/{thread_id}", response_model=EmailThreadDetailResponse)
async def get_thread(
    thread_id: uuid.UUID,
    principal: Viewer,
    service: ServiceDep,
) -> EmailThreadDetailResponse:
    """One conversation and every message in it the caller may read."""
    thread = await service.get_thread_or_404(thread_id, principal.organization_id)
    messages = await service.thread_messages(
        thread_id,
        principal.organization_id,
        readable=readable_messages(principal.user_id),
    )
    counts = await service.attachment_counts(principal.organization_id, messages)
    return EmailThreadDetailResponse(
        **EmailThreadResponse.model_validate(thread).model_dump(),
        messages=[
            _present(message, principal, attachment_count=counts.get(message.id, 0))
            for message in messages
        ],
    )


@router.get("/{message_id}", response_model=EmailMessageResponse)
async def get_message(
    message_id: uuid.UUID,
    principal: Viewer,
    service: ServiceDep,
) -> EmailMessageResponse:
    """One message. Somebody else's draft returns 404."""
    message = await service.get_readable_message(
        message_id, principal.organization_id, viewer_id=principal.user_id
    )
    counts = await service.attachment_counts(principal.organization_id, [message])
    return _present(message, principal, attachment_count=counts.get(message.id, 0))


@router.patch("/{message_id}", response_model=EmailMessageResponse)
async def update_draft(
    message_id: uuid.UUID,
    payload: EmailMessageUpdate,
    principal: Editor,
    service: ServiceDep,
) -> EmailMessageResponse:
    """Edit an unsent message. A sent one returns 409."""
    message = await service.get_readable_message(
        message_id, principal.organization_id, viewer_id=principal.user_id
    )
    updated = await service.update_draft(
        message,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
        principal=principal,
    )
    return _present(updated, principal)


@router.post("/{message_id}/send", response_model=EmailMessageResponse)
async def send_message(
    message_id: uuid.UUID,
    principal: Composer,
    service: ServiceDep,
) -> EmailMessageResponse:
    """Queue a draft for delivery.

    Returns as soon as the event is enqueued, with the message on ``QUEUED``.
    It has not been sent yet and the response does not claim it has — the
    worker moves it to ``SENT`` or ``FAILED``, and the client polls or reloads.
    Blocking here until a relay answered would tie a request to a third party's
    latency for no gain in truthfulness.
    """
    message = await service.get_readable_message(
        message_id, principal.organization_id, viewer_id=principal.user_id
    )
    sent = await service.send_message(message, actor_id=principal.user_id)
    return _present(sent, principal)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_message(
    message_id: uuid.UUID,
    principal: Remover,
    service: ServiceDep,
) -> Response:
    """Archive a message. Soft, like every deletion in the CRM."""
    message = await service.get_readable_message(
        message_id, principal.organization_id, viewer_id=principal.user_id
    )
    await service.discard_draft(message, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Templates --------------------------------------------------------------


@templates_router.get("", response_model=Page[EmailTemplateResponse])
async def list_templates(
    principal: Viewer,
    service: TemplateServiceDep,
    params: PageParamsDep,
    category: Annotated[str | None, Query(max_length=80)] = None,
) -> Page[EmailTemplateResponse]:
    """Templates the caller may use: the organization's, plus their own."""
    items, total = await service.list_templates(
        principal.organization_id,
        params=params,
        viewer_id=principal.user_id,
        category=category,
    )
    return Page.build(
        [EmailTemplateResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@templates_router.get("/placeholders", response_model=list[str])
async def list_placeholders(
    principal: Viewer,
    related_entity_type: Annotated[CrmEntityType | None, Query()] = None,
) -> list[str]:
    """Placeholder names a template may use against this record type.

    Static — derived from the field allow-list, not from any record — so it
    needs no organization scope and leaks nothing. It exists so the composer's
    "insert field" menu offers exactly what will resolve.
    """
    del principal  # Authorization only; the answer is the same for everyone.
    return offered_placeholders(related_entity_type)


@templates_router.post(
    "", response_model=EmailTemplateResponse, status_code=status.HTTP_201_CREATED
)
async def create_template(
    payload: EmailTemplateCreate,
    principal: Composer,
    service: TemplateServiceDep,
) -> EmailTemplateResponse:
    """Save a template. Names are unique per organization among the living."""
    template = await service.create_template(
        organization_id=principal.organization_id,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return EmailTemplateResponse.model_validate(template)


@templates_router.get("/{template_id}", response_model=EmailTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    principal: Viewer,
    service: TemplateServiceDep,
) -> EmailTemplateResponse:
    """One template. Somebody else's private one returns 404."""
    template = await _readable_template(service, template_id, principal)
    return EmailTemplateResponse.model_validate(template)


@templates_router.post("/{template_id}/render", response_model=TemplateRenderResponse)
async def render_template(
    template_id: uuid.UUID,
    payload: TemplateRenderRequest,
    principal: Viewer,
    service: TemplateServiceDep,
    emails: ServiceDep,
) -> TemplateRenderResponse:
    """Fill a template against a record, and say what could not be filled."""
    template = await _readable_template(service, template_id, principal)
    sender_email, sender_name = await emails.sender_identity(
        principal.organization_id, principal.user_id
    )
    rendered = await emails.render_template(
        template,
        organization_id=principal.organization_id,
        entity_type=payload.related_entity_type,
        entity_id=payload.related_entity_id,
        sender_name=sender_name,
        sender_email=sender_email,
        organization_name=await emails.organization_name(principal.organization_id),
        principal=principal,
    )
    return TemplateRenderResponse(**rendered)


@templates_router.patch("/{template_id}", response_model=EmailTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    payload: EmailTemplateUpdate,
    principal: Editor,
    service: TemplateServiceDep,
) -> EmailTemplateResponse:
    """Edit a template. Authors only, like a note."""
    template = await _readable_template(service, template_id, principal)
    updated = await service.update_template(
        template,
        actor_id=principal.user_id,
        values=payload.model_dump(exclude_unset=True),
    )
    return EmailTemplateResponse.model_validate(updated)


@templates_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_template(
    template_id: uuid.UUID,
    principal: Remover,
    service: TemplateServiceDep,
) -> Response:
    """Retire a template. Messages sent with it keep their history."""
    template = await _readable_template(service, template_id, principal)
    await service.archive_template(template, actor_id=principal.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _readable_template(
    service: EmailTemplateService, template_id: uuid.UUID, principal: Principal
) -> EmailTemplate:
    """Fetch a template the caller may see, or 404.

    Somebody else's private template produces the same 404 as one that does
    not exist — the same treatment a private note gets, and for the same
    reason.
    """
    template = await service.get_or_404(template_id, principal.organization_id)
    if not may_read_template(
        is_shared=template.is_shared,
        owner_id=template.owner_id,
        viewer_id=principal.user_id,
    ):
        raise NotFoundError("Template not found.")
    return template


__all__ = ["router", "templates_router"]
