"""HTTP routes for the documents module.

Mounted at ``/api/v1/attachments`` by the composition root. Every route is
gated twice: once on the ``documents`` permission, and once on access to the
CRM record the file hangs off.

That second check is product logic — it depends on ``owner_id`` and on the
caller's ``VIEW_ALL`` grant, both of which live in ``app.products.crm``, and
ARCHITECTURE-BOUNDARIES.md rule 1 forbids Platform from importing a product.
The dependency is therefore inverted behind a Platform-owned abstraction: this
module declares :func:`register_entity_access`, and ``app/api/router.py`` — the
one module permitted to see both layers — registers the CRM implementation
before including the router.

**Registered rather than passed in.** A router *factory* taking the verifier as
an argument reads better and was the first shape tried, but it does not survive
``from __future__ import annotations``: the ``Annotated[...]`` dependency
aliases would have to be locals inside the factory, and FastAPI resolves route
annotations against module globals, so each one becomes an unresolvable forward
reference. Registration keeps the conventional module-level ``router`` every
other module uses.

The registry **fails closed**: until something registers a verifier the default
is :class:`~app.platform.documents.policies.DenyAllEntityAccess`, so a wiring
mistake produces 404s rather than unguarded access to every record.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import DbSession
from app.core.pagination import Page, PageParams, page_params
from app.platform.audit.service import audit_for_session
from app.platform.auth.dependencies import (
    Principal,
    get_settings_from_request,
    require_permission,
)
from app.platform.documents.policies import (
    CREATE,
    DELETE,
    MODULE,
    VIEW,
    DenyAllEntityAccess,
)
from app.platform.documents.policies import (
    EntityAccessVerifier as EntityAccessVerifierProtocol,
)
from app.platform.documents.repository import AttachmentRepository
from app.platform.documents.schemas import (
    AttachmentDownloadResponse,
    AttachmentResponse,
    AttachmentUploadRequest,
    AttachmentUploadResponse,
)
from app.platform.documents.service import DocumentService
from app.platform.documents.storage import ObjectStorage

router = APIRouter()

#: Builds the per-request verifier. A callable rather than an instance because
#: resolving a CRM record needs the request's own database session.
EntityAccessFactory = Callable[[AsyncSession], EntityAccessVerifierProtocol]

#: Set once by the composition root. ``None`` means nothing was registered,
#: which resolves to "deny everything" rather than "allow everything".
_entity_access_factory: EntityAccessFactory | None = None


def register_entity_access(factory: EntityAccessFactory) -> None:
    """Register the product resolver for linked-record access.

    Called by ``app/api/router.py`` at import time, before the router is
    included. Idempotent by nature — registering the same factory twice is
    harmless — and deliberately not reachable from a request.
    """
    # Module-level rather than app.state: the composition root runs at import
    # time, before any application object exists to hang it on.
    global _entity_access_factory
    _entity_access_factory = factory


def get_entity_access(session: DbSession) -> EntityAccessVerifierProtocol:
    """The verifier for this request, or one that refuses everything."""
    if _entity_access_factory is None:
        return DenyAllEntityAccess()
    return _entity_access_factory(session)


PageParamsDep = Annotated[PageParams, Depends(page_params)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_request)]
EntityAccessDep = Annotated[EntityAccessVerifierProtocol, Depends(get_entity_access)]

#: The three gates this module enforces, declared once so no route can be added
#: with a weaker one by accident. Record-level access is checked separately, in
#: the service — see ``policies.py`` for why both are needed.
Reader = Annotated[Principal, Depends(require_permission(MODULE, VIEW))]
Writer = Annotated[Principal, Depends(require_permission(MODULE, CREATE))]
Remover = Annotated[Principal, Depends(require_permission(MODULE, DELETE))]


def get_service(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    access: EntityAccessDep,
) -> DocumentService:
    # The storage client is built once during startup rather than per request:
    # constructing a boto3 client parses configuration and builds a signer, and
    # it is thread-safe for the calls made here.
    storage: ObjectStorage | None = request.app.state.object_storage
    return DocumentService(
        AttachmentRepository(session),
        storage=storage,
        access=access,
        download_ttl_seconds=settings.storage_download_url_ttl_seconds,
        upload_ttl_seconds=settings.storage_upload_url_ttl_seconds,
        audit=audit_for_session(session),
    )


ServiceDep = Annotated[DocumentService, Depends(get_service)]


@router.get("", response_model=Page[AttachmentResponse])
async def list_attachments(
    principal: Reader,
    service: ServiceDep,
    params: PageParamsDep,
    entity_type: Annotated[str, Query(max_length=64)],
    entity_id: Annotated[uuid.UUID, Query()],
) -> Page[AttachmentResponse]:
    """Files attached to one CRM record.

    The record is always named explicitly. There is no "list every attachment
    in the organization" route, because such a list could not be filtered by
    record-level visibility without resolving every row's linked record one at
    a time.
    """
    items, total = await service.list_for_entity(
        principal, entity_type=entity_type, entity_id=entity_id, params=params
    )
    return Page.build(
        [AttachmentResponse.model_validate(item) for item in items],
        total=total,
        params=params,
    )


@router.post(
    "/upload-url",
    response_model=AttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_upload_url(
    payload: AttachmentUploadRequest,
    principal: Writer,
    service: ServiceDep,
    request: Request,
) -> AttachmentUploadResponse:
    """Reserve an attachment and return a pre-signed PUT URL.

    201 because a ``PENDING`` row now exists. It becomes visible to readers
    only after ``/confirm``.
    """
    ticket = await service.create_upload(
        principal,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
    )
    return AttachmentUploadResponse(
        attachment=AttachmentResponse.model_validate(ticket.attachment),
        upload_url=ticket.upload.url,
        method=ticket.upload.method,
        headers=ticket.upload.headers,
        expires_at=ticket.upload.expires_at,
        confirm_path=str(
            request.url_for("confirm_upload", attachment_id=ticket.attachment.id).path
        ),
    )


@router.post("/{attachment_id}/confirm", response_model=AttachmentResponse)
async def confirm_upload(
    attachment_id: uuid.UUID,
    principal: Writer,
    service: ServiceDep,
) -> AttachmentResponse:
    """Publish an attachment once its bytes have landed.

    Verifies against storage rather than trusting the client, and rejects —
    deleting both object and row — anything that does not match what was
    promised at upload-url time.
    """
    attachment = await service.confirm_upload(attachment_id, principal)
    return AttachmentResponse.model_validate(attachment)


@router.delete("/{attachment_id}/upload", status_code=status.HTTP_204_NO_CONTENT)
async def abandon_upload(
    attachment_id: uuid.UUID,
    principal: Writer,
    service: ServiceDep,
) -> Response:
    """Release a reservation whose upload failed or was cancelled.

    Lets the browser clean up after itself instead of leaving a ``PENDING`` row
    behind. Separate from ``DELETE /{id}``: that removes a published attachment
    and needs ``documents.DELETE``, while this only discards something that was
    never visible to anyone.
    """
    await service.abandon_upload(attachment_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    attachment_id: uuid.UUID,
    principal: Reader,
    service: ServiceDep,
) -> AttachmentResponse:
    """One attachment's metadata. Another tenant's id returns 404."""
    attachment = await service.get_or_404(attachment_id, principal)
    return AttachmentResponse.model_validate(attachment)


@router.get("/{attachment_id}/download-url", response_model=AttachmentDownloadResponse)
async def create_download_url(
    attachment_id: uuid.UUID,
    principal: Reader,
    service: ServiceDep,
) -> AttachmentDownloadResponse:
    """A short-lived URL for the file itself.

    The API never proxies the bytes: it authorizes, then hands back a URL the
    browser fetches directly from storage. Permission on the linked record is
    checked before the URL exists, because once issued it works for whoever
    holds it until it expires.
    """
    ticket = await service.download_url(attachment_id, principal)
    return AttachmentDownloadResponse(
        url=ticket.url, expires_at=ticket.expires_at, filename=ticket.filename
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    attachment_id: uuid.UUID,
    principal: Remover,
    service: ServiceDep,
) -> Response:
    """Remove the object from storage and archive its metadata row."""
    await service.delete(attachment_id, principal)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["EntityAccessFactory", "register_entity_access", "router"]
