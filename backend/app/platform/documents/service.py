"""Use cases for the documents module — the module's public interface.

The upload is a three-party dance (doc 09 "Documents & File Storage"): the API
issues a pre-signed URL, the **browser** PUTs the bytes straight to storage,
and the API is told to confirm. Bytes never pass through this process, which is
what keeps a 50 MB attachment from occupying a worker and a database
transaction for the duration of the transfer.

That shape means the two stores can disagree, so the ordering here is chosen to
make every disagreement recoverable in the safe direction:

**Metadata first, as ``PENDING``.** The row is written before the URL is
issued, because the storage key is derived from the row's own id. An abandoned
upload therefore leaves a ``PENDING`` row and no object — invisible to every
read path (the repository filters to ``ACTIVE``), and cheap.

**Confirm reads storage, not the client.** Everything the client said at
upload-url time was a claim about a file it had not sent yet. ``HeadObject``
reports what actually landed, and the size and type are re-checked against it.
A mismatch deletes the object and the row rather than trusting either.

**Nothing is orphaned in the direction that costs money.** Cleanup always
removes the object first and the row second. An object with no row is storage
nobody can find, name or bill down; a row with no object is an invisible
``PENDING`` row, or at worst a download that 404s. Given a choice, strand the
row.

That ordering also survives the rollback. A rejected confirmation *raises*, and
raising rolls the request transaction back — so the object deletion (which is
not transactional) stands while the row deletion is undone, leaving a
``PENDING`` row that no read path returns. The browser's abandon call clears it;
if that never arrives, an invisible row is the harmless end state. The
alternative ordering would leave the object instead, which nothing cleans up.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.core.ids import uuid7
from app.core.pagination import PageParams
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import AuditService, audit_for_session
from app.platform.auth.dependencies import Principal
from app.platform.documents.models import Attachment, AttachmentStatus
from app.platform.documents.policies import (
    MODULE,
    EntityAccess,
    EntityAccessVerifier,
)
from app.platform.documents.repository import AttachmentRepository
from app.platform.documents.storage import (
    ObjectStorage,
    PresignedUpload,
    StorageNotConfiguredError,
)
from app.platform.documents.validation import (
    build_storage_key,
    sanitize_filename,
    validate_content_type,
    validate_size,
)

logger = structlog.get_logger(__name__)

#: Entity type recorded on audit rows for the attachment itself.
AUDIT_ENTITY_TYPE = "ATTACHMENT"

# ``EntityAccess`` and ``EntityAccessVerifier`` are imported above and named in
# ``__all__`` so a product can implement the verifier against this module
# rather than against ``policies`` — ARCHITECTURE-BOUNDARIES.md rule 2:
# products consume Platform through service interfaces only. Same reasoning as
# ``authorization.service.Action``.


class AttachmentNotReadyError(AppError):
    """The object never landed, so there is nothing to confirm or download."""

    status_code = status.HTTP_409_CONFLICT
    code = "attachment_not_ready"
    message = "The file was not uploaded. Start the upload again."


@dataclass(frozen=True, slots=True)
class UploadTicket:
    """A created ``PENDING`` attachment plus the URL to send its bytes to."""

    attachment: Attachment
    upload: PresignedUpload


@dataclass(frozen=True, slots=True)
class DownloadTicket:
    url: str
    expires_at: dt.datetime
    filename: str


class DocumentService:
    """Attachment metadata and its object in storage, kept in step."""

    def __init__(
        self,
        repository: AttachmentRepository,
        *,
        storage: ObjectStorage | None,
        access: EntityAccessVerifier,
        download_ttl_seconds: int,
        upload_ttl_seconds: int,
        audit: AuditService | None = None,
    ) -> None:
        self._repository = repository
        # ``None`` when the environment has no storage configured. Every path
        # that needs it calls ``_require_storage`` first, so the 503 is raised
        # before any row is written.
        self._storage = storage
        self._access = access
        self._download_ttl = download_ttl_seconds
        self._upload_ttl = upload_ttl_seconds
        self._audit = audit or audit_for_session(repository.session)

    # --- Authorization -----------------------------------------------------

    async def _require_record_access(
        self,
        principal: Principal,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        write: bool,
    ) -> EntityAccess:
        """Resolve access to the linked record, or 404.

        404 rather than 403 for every failure, and the same 404 for all three
        of them — unknown entity type, missing record, record the caller may
        not see. Distinguishing them would let a caller map another user's
        pipeline by watching which ids answer differently.
        """
        access = await self._access.resolve(
            principal=principal, entity_type=entity_type, entity_id=entity_id
        )
        if not access.can_view or (write and not access.can_edit):
            logger.info(
                "attachment_entity_access_denied",
                entity_type=entity_type,
                entity_id=str(entity_id),
                user_id=str(principal.user_id),
                write=write,
            )
            raise NotFoundError("The linked record does not exist.")
        return access

    def _require_storage(self) -> ObjectStorage:
        if self._storage is None:
            raise StorageNotConfiguredError
        return self._storage

    # --- Reads -------------------------------------------------------------

    async def list_for_entity(
        self,
        principal: Principal,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        params: PageParams,
    ) -> tuple[Sequence[Attachment], int]:
        """Attachments on a record the caller may read."""
        await self._require_record_access(
            principal, entity_type=entity_type, entity_id=entity_id, write=False
        )
        return await self._repository.list_for_entity(
            principal.organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            params=params,
        )

    async def get_or_404(
        self, attachment_id: uuid.UUID, principal: Principal
    ) -> Attachment:
        """Fetch an attachment and re-check access to the record it hangs off.

        Both halves matter. The organization filter stops another tenant's id
        resolving at all; the record check stops a caller reaching a file
        attached to a record inside their own organization that record-level
        visibility hides from them.
        """
        attachment = await self._repository.get(
            attachment_id, principal.organization_id
        )
        if attachment is None:
            raise NotFoundError("Attachment not found.")
        await self._require_record_access(
            principal,
            entity_type=attachment.entity_type,
            entity_id=attachment.entity_id,
            write=False,
        )
        return attachment

    # --- Upload ------------------------------------------------------------

    async def create_upload(
        self,
        principal: Principal,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        filename: str,
        content_type: str,
        size_bytes: int,
    ) -> UploadTicket:
        """Validate, reserve metadata and issue a pre-signed PUT URL.

        Order matters and is not arbitrary:

        1. storage availability, so an unconfigured environment fails before
           anything is written;
        2. record access, so a caller cannot even learn that a record exists by
           watching which uploads are accepted;
        3. filename, type and size, so a rejected upload never reaches storage;
        4. the ``PENDING`` row, whose id becomes the storage key;
        5. the signed URL, which binds the content type and length so the
           browser cannot substitute a different file for the one described.

        Raises:
            StorageNotConfiguredError: no bucket or credentials (503).
            NotFoundError: the linked record is missing or not visible.
            InvalidFilenameError, UnsupportedFileTypeError, FileTooLargeError.
        """
        storage = self._require_storage()
        await self._require_record_access(
            principal, entity_type=entity_type, entity_id=entity_id, write=True
        )

        safe_name = sanitize_filename(filename)
        normalised_type = validate_content_type(content_type, safe_name)
        declared_size = validate_size(size_bytes)

        # The id is generated here rather than left to the column default
        # because the storage key is derived from it and the URL must be signed
        # before the transaction commits.
        attachment_id = uuid7()
        attachment = Attachment(
            id=attachment_id,
            organization_id=principal.organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            name=safe_name,
            mime_type=normalised_type,
            size_bytes=declared_size,
            storage_key=build_storage_key(principal.organization_id, attachment_id),
            status=AttachmentStatus.PENDING,
            created_by_id=principal.user_id,
            updated_by_id=principal.user_id,
        )
        await self._repository.add(attachment)

        upload = await storage.presigned_upload(
            attachment.storage_key,
            content_type=normalised_type,
            content_length=declared_size,
            ttl_seconds=self._upload_ttl,
        )
        logger.info(
            "attachment_upload_reserved",
            attachment_id=str(attachment.id),
            organization_id=str(principal.organization_id),
            size_bytes=declared_size,
        )
        return UploadTicket(attachment=attachment, upload=upload)

    async def confirm_upload(
        self, attachment_id: uuid.UUID, principal: Principal
    ) -> Attachment:
        """Verify the object landed, then publish the attachment.

        The size and content type are taken from ``HeadObject`` — what storage
        actually holds — and re-validated. This is defence in depth rather than
        the primary control: the pre-signed URL binds both, so a mismatch means
        the object arrived by some route other than the one that was issued.

        A rejection deletes the object and attempts to delete the row. The
        object deletion stands; the row deletion is rolled back with the
        request when this raises, leaving a ``PENDING`` row no read path
        returns — see the module docstring for why that direction is the safe
        one.

        Idempotent for an attachment already ``ACTIVE``: a client that retries
        a confirm whose response it never saw gets the same answer rather than
        a conflict.

        Raises:
            NotFoundError: unknown id, another tenant's id, or a record the
                caller cannot see.
            AttachmentNotReadyError: no object at the key (409).
            FileTooLargeError, UnsupportedFileTypeError: what landed does not
                match what was promised.
        """
        storage = self._require_storage()
        attachment = await self._repository.get(
            attachment_id, principal.organization_id
        )
        if attachment is None:
            raise NotFoundError("Attachment not found.")
        await self._require_record_access(
            principal,
            entity_type=attachment.entity_type,
            entity_id=attachment.entity_id,
            write=True,
        )

        if attachment.status is AttachmentStatus.ACTIVE:
            return attachment

        stored = await storage.head(attachment.storage_key)
        if stored is None:
            logger.info(
                "attachment_confirm_object_missing",
                attachment_id=str(attachment.id),
            )
            raise AttachmentNotReadyError

        try:
            actual_size = validate_size(stored.size_bytes)
            # Storage echoes the content type the signed PUT bound, so a
            # mismatch here means the object was written by some other route.
            actual_type = validate_content_type(
                stored.content_type or attachment.mime_type, attachment.name
            )
        except AppError:
            await self._discard(attachment, reason="failed_validation_on_confirm")
            raise

        attachment.size_bytes = actual_size
        attachment.mime_type = actual_type
        attachment.checksum = stored.etag
        attachment.status = AttachmentStatus.ACTIVE
        attachment.updated_by_id = principal.user_id
        await self._repository.flush()

        await self._audit.record(
            organization_id=principal.organization_id,
            action=AuditAction.ATTACHMENT_UPLOADED,
            module=MODULE,
            actor_id=principal.user_id,
            entity_type=AUDIT_ENTITY_TYPE,
            entity_id=attachment.id,
            entity_label=attachment.name,
            details={
                "linked_entity_type": attachment.entity_type,
                "linked_entity_id": attachment.entity_id,
                "mime_type": attachment.mime_type,
                "size_bytes": attachment.size_bytes,
                "checksum": stored.etag,
            },
        )
        logger.info(
            "attachment_uploaded",
            attachment_id=str(attachment.id),
            organization_id=str(principal.organization_id),
            size_bytes=actual_size,
        )
        return attachment

    async def _discard(self, attachment: Attachment, *, reason: str) -> None:
        """Undo a reservation that will never become an attachment.

        Object first, then row: an object whose row is gone is unreachable
        storage that nothing will ever clean up, whereas a stranded row is
        invisible and cheap. Deleting an absent object succeeds, so this is
        safe whatever stage the upload reached.

        The row deletion only survives when the caller goes on to commit. On
        the rejection path it does not, which is deliberate — see the module
        docstring.
        """
        if self._storage is not None:
            await self._storage.delete(attachment.storage_key)
        await self._repository.delete_row(attachment)
        logger.info(
            "attachment_discarded",
            attachment_id=str(attachment.id),
            reason=reason,
        )

    async def abandon_upload(
        self, attachment_id: uuid.UUID, principal: Principal
    ) -> None:
        """Drop a reservation the client decided not to complete.

        Lets the browser clean up after a failed or cancelled PUT instead of
        leaving a ``PENDING`` row behind. Refuses to touch an ``ACTIVE`` one —
        deleting a live attachment goes through :meth:`delete`, which audits.
        """
        attachment = await self._repository.get(
            attachment_id, principal.organization_id
        )
        if attachment is None:
            return
        await self._require_record_access(
            principal,
            entity_type=attachment.entity_type,
            entity_id=attachment.entity_id,
            write=True,
        )
        if attachment.status is AttachmentStatus.ACTIVE:
            raise AttachmentNotReadyError(
                "That attachment is already published; delete it instead."
            )
        await self._discard(attachment, reason="abandoned_by_client")

    # --- Download ----------------------------------------------------------

    async def download_url(
        self, attachment_id: uuid.UUID, principal: Principal
    ) -> DownloadTicket:
        """A short-lived read URL for an attachment the caller may see.

        Permission on the linked record is checked **before** the URL is
        generated (doc 13), because a pre-signed URL is a bearer credential:
        once issued it works for anyone holding it until it expires, so the
        check cannot be deferred to the fetch.

        Access is audited. Doc 13 requires it and it is the only record of who
        read which file — the storage layer's own logs are not tenant-scoped
        and are not visible to an organization's administrator.

        Raises:
            NotFoundError, AttachmentNotReadyError.
        """
        storage = self._require_storage()
        attachment = await self.get_or_404(attachment_id, principal)

        if attachment.status is not AttachmentStatus.ACTIVE:
            raise AttachmentNotReadyError

        url, expires_at = await storage.presigned_download(
            attachment.storage_key,
            filename=attachment.name,
            ttl_seconds=self._download_ttl,
        )

        await self._audit.record(
            organization_id=principal.organization_id,
            action=AuditAction.ATTACHMENT_DOWNLOADED,
            module=MODULE,
            actor_id=principal.user_id,
            entity_type=AUDIT_ENTITY_TYPE,
            entity_id=attachment.id,
            entity_label=attachment.name,
            details={
                "linked_entity_type": attachment.entity_type,
                "linked_entity_id": attachment.entity_id,
                # The URL itself is deliberately absent: it is a live bearer
                # credential for the TTL, and the audit trail is readable by
                # every administrator.
                "url_ttl_seconds": self._download_ttl,
            },
        )
        return DownloadTicket(
            url=url, expires_at=expires_at, filename=attachment.name
        )

    # --- Delete ------------------------------------------------------------

    async def delete(self, attachment_id: uuid.UUID, principal: Principal) -> None:
        """Remove an attachment: the object from storage, the row by soft delete.

        The object goes first, for the same reason as in :meth:`_discard`. The
        row is soft-deleted rather than dropped so the audit trail's
        ``entity_id`` still resolves to something, and so the record of what
        was attached survives the file itself.

        Doc 13 describes a 30-day retention window before the object is purged.
        That presumes a scheduled purge worker, and none exists yet
        (`P1-W08-BE-04` is unstarted) — so retaining objects would leak them
        indefinitely with nothing to collect them, and there is no restore
        endpoint that would make the window useful. The object is therefore
        removed immediately; see CR12.

        Raises:
            NotFoundError: unknown id, another tenant's id, or a record the
                caller may not see.
        """
        storage = self._require_storage()
        attachment = await self._repository.get(
            attachment_id, principal.organization_id
        )
        if attachment is None:
            raise NotFoundError("Attachment not found.")
        # Write access: deleting somebody's file is an edit to the record it
        # hangs off, not a read of it.
        await self._require_record_access(
            principal,
            entity_type=attachment.entity_type,
            entity_id=attachment.entity_id,
            write=True,
        )

        await storage.delete(attachment.storage_key)
        attachment.updated_by_id = principal.user_id
        await self._repository.soft_delete(attachment)

        await self._audit.record(
            organization_id=principal.organization_id,
            action=AuditAction.ATTACHMENT_DELETED,
            module=MODULE,
            actor_id=principal.user_id,
            entity_type=AUDIT_ENTITY_TYPE,
            entity_id=attachment.id,
            entity_label=attachment.name,
            details={
                "linked_entity_type": attachment.entity_type,
                "linked_entity_id": attachment.entity_id,
                "size_bytes": attachment.size_bytes,
                "object_removed": True,
            },
        )
        logger.info(
            "attachment_deleted",
            attachment_id=str(attachment.id),
            organization_id=str(principal.organization_id),
        )


def documents_for_session(
    session: AsyncSession,
    *,
    storage: ObjectStorage | None,
    access: EntityAccessVerifier,
    download_ttl_seconds: int,
    upload_ttl_seconds: int,
) -> DocumentService:
    """Build a :class:`DocumentService` bound to an existing session."""
    return DocumentService(
        AttachmentRepository(session),
        storage=storage,
        access=access,
        download_ttl_seconds=download_ttl_seconds,
        upload_ttl_seconds=upload_ttl_seconds,
    )


__all__ = [
    "AUDIT_ENTITY_TYPE",
    "AttachmentNotReadyError",
    "DocumentService",
    "DownloadTicket",
    "EntityAccess",
    "EntityAccessVerifier",
    "UploadTicket",
    "documents_for_session",
]
