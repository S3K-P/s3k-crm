"""SQLAlchemy models for the documents module (doc 04 "Document & File Storage").

Attachments are a Platform concern, not a CRM one: several products will need
them, so the table lives in ``platform`` and links to a product record through
a loose ``entity_type``/``entity_id`` pair rather than a foreign key.

**Metadata only.** No bytes are stored or served here. ``storage_key`` names an
object in external storage; uploading and downloading it are out of scope for
this phase, so nothing in this module produces or consumes a pre-signed URL
yet.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    Index,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import (
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

PLATFORM_SCHEMA = "platform"

#: Upload ceiling from doc 13 ("max size 50MB MVP"). Enforced on the metadata
#: record so an oversized object cannot be registered even if it reached
#: storage by another route.
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


class AttachmentStatus(enum.StrEnum):
    #: Registered, awaiting the bytes to land in object storage.
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    QUARANTINED = "QUARANTINED"


class Attachment(
    Base,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
):
    """Metadata for a file attached to a record in any product."""

    __tablename__ = "attachments"
    __table_args__ = (
        Index(
            "ix_attachments_organization_id_entity",
            "organization_id",
            "entity_type",
            "entity_id",
        ),
        Index("ix_attachments_organization_id_created_at", "organization_id", "created_at"),
        CheckConstraint(
            f"size_bytes > 0 AND size_bytes <= {MAX_ATTACHMENT_BYTES}",
            name="size_bytes_within_limit",
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Object-storage key. Always prefixed with the organization id so a
    #: mis-scoped read cannot reach another tenant's object (doc 13).
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[AttachmentStatus] = mapped_column(
        Enum(
            AttachmentStatus,
            name="attachment_status",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=AttachmentStatus.PENDING,
        server_default=AttachmentStatus.PENDING.value,
    )
    #: Free-form product record reference, e.g. ``("ACCOUNT", <uuid>)``. Kept
    #: as a string so Platform never has to know the CRM entity enum.
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    @staticmethod
    def build_storage_key(organization_id: uuid.UUID, attachment_id: uuid.UUID) -> str:
        """Object key for an attachment: ``{orgId}/{attachmentId}`` (doc 13)."""
        return f"{organization_id}/{attachment_id}"


__all__ = [
    "MAX_ATTACHMENT_BYTES",
    "Attachment",
    "AttachmentStatus",
]
