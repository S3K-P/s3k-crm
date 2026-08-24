"""Pydantic v2 schemas for the documents module.

The upload request describes a file the client has **not sent yet**, so every
field on it is a claim. They are validated here for shape and again in
``validation.py`` against the whitelist and the ceiling, then bound into the
pre-signed URL's signature so the browser cannot substitute something else. The
authority on what was actually stored is ``HeadObject`` at confirm time, never
this payload.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.platform.documents.models import MAX_ATTACHMENT_BYTES, AttachmentStatus
from app.platform.documents.validation import MAX_FILENAME_LENGTH


class AttachmentUploadRequest(BaseModel):
    """Ask for permission to upload one file to one record."""

    entity_type: str = Field(
        max_length=64,
        description="Record kind the file attaches to, e.g. ACCOUNT.",
    )
    entity_id: uuid.UUID
    filename: str = Field(
        min_length=1,
        max_length=MAX_FILENAME_LENGTH,
        description="Original filename. Sanitised server-side before storage.",
    )
    content_type: str = Field(
        min_length=1,
        max_length=160,
        description="Declared MIME type. Must be on the server whitelist.",
    )
    size_bytes: int = Field(
        gt=0,
        le=MAX_ATTACHMENT_BYTES,
        description=f"Exact byte count. At most {MAX_ATTACHMENT_BYTES} bytes.",
    )


class AttachmentResponse(BaseModel):
    """Attachment metadata as the CRM detail pages render it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    name: str
    mime_type: str
    size_bytes: int
    status: AttachmentStatus
    checksum: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    created_by_id: uuid.UUID | None

    # ``storage_key`` is deliberately absent. It is an internal object address;
    # publishing it would tell a caller the exact key layout of every tenant's
    # bucket, which is information they never need and an attacker would.


class AttachmentUploadResponse(BaseModel):
    """The reserved attachment plus how to send its bytes."""

    attachment: AttachmentResponse
    upload_url: str = Field(description="Pre-signed URL. Single file, short-lived.")
    method: str = Field(description="HTTP method to use, always PUT.")
    headers: dict[str, str] = Field(
        description=(
            "Headers the client must send unchanged. They are part of the "
            "signature, so altering one invalidates the URL."
        )
    )
    expires_at: dt.datetime
    #: Where to confirm once the PUT succeeds. Spelled out so the client does
    #: not have to construct API paths by string concatenation.
    confirm_path: str


class AttachmentDownloadResponse(BaseModel):
    """A short-lived read URL (doc 13: 15-minute TTL)."""

    url: str
    expires_at: dt.datetime
    filename: str


__all__ = [
    "AttachmentDownloadResponse",
    "AttachmentResponse",
    "AttachmentUploadRequest",
    "AttachmentUploadResponse",
]
