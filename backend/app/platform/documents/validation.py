"""What may be uploaded, and under what name (doc 13 "File Upload Security").

Three independent checks, because each catches something the others cannot:

**The MIME whitelist** decides what kinds of file this system accepts at all.
It is an allow-list, never a block-list: a block-list is a promise to have
thought of every dangerous type, and it is wrong the moment a new one exists.

**The extension check** catches the mismatch a whitelist alone misses — a
client declaring ``application/pdf`` for ``payload.exe``. Storage keeps what it
is given, and a download served under a trusted content type is exactly how a
file that is not what it claims gets opened.

**The filename rules** protect the *metadata*, not the object. The storage key
is generated server-side from two UUIDs and never contains user input, so path
traversal cannot reach storage. But the original name is displayed in the CRM
and is sent back in a ``Content-Disposition`` header, so control characters and
separators are stripped before it is stored.

Size is enforced in three places on purpose: here against the declared value,
in the pre-signed URL's signature (a mismatched ``Content-Length`` will not
verify), and again after the object lands via ``HeadObject``. The first is a
courtesy to the client, the second is the binding one, the third is what
catches a storage backend that accepted something it should not have.
"""

from __future__ import annotations

import posixpath
import re
import unicodedata
import uuid
from typing import Final

from fastapi import status

from app.core.exceptions import AppError
from app.platform.documents.models import MAX_ATTACHMENT_BYTES

#: Accepted content types, mapped to the extensions each may legitimately use.
#:
#: Deliberately conservative and business-document shaped: the CRM attaches
#: contracts, proposals, spreadsheets and screenshots. Nothing executable,
#: nothing that a browser will run — note the absence of ``text/html`` and
#: ``image/svg+xml``, both of which can carry script and would execute against
#: the storage origin if a download were ever served inline.
ALLOWED_CONTENT_TYPES: Final[dict[str, frozenset[str]]] = {
    "application/pdf": frozenset({".pdf"}),
    "image/png": frozenset({".png"}),
    "image/jpeg": frozenset({".jpg", ".jpeg"}),
    "image/gif": frozenset({".gif"}),
    "image/webp": frozenset({".webp"}),
    "text/plain": frozenset({".txt", ".log", ".md"}),
    "text/csv": frozenset({".csv"}),
    "application/msword": frozenset({".doc"}),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": frozenset(
        {".docx"}
    ),
    "application/vnd.ms-excel": frozenset({".xls"}),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": frozenset({".xlsx"}),
    "application/vnd.ms-powerpoint": frozenset({".ppt"}),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": frozenset(
        {".pptx"}
    ),
    "application/zip": frozenset({".zip"}),
}

MAX_FILENAME_LENGTH: Final = 255

#: Anything outside this is replaced with an underscore. Path separators are
#: absent by construction, so ``../`` cannot survive.
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9 ._\-()\[\]]+")

#: Collapse runs of dots so ``..`` cannot appear in a stored name.
_DOT_RUN = re.compile(r"\.{2,}")


class UnsupportedFileTypeError(AppError):
    """The content type is not on the whitelist, or contradicts the extension."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "unsupported_file_type"
    message = "That file type cannot be attached."


class FileTooLargeError(AppError):
    """The file exceeds the configured ceiling."""

    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "file_too_large"
    message = f"Attachments may be at most {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB."


class InvalidFilenameError(AppError):
    """The filename is empty, or contains nothing usable once sanitised."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invalid_filename"
    message = "That filename cannot be used."


def sanitize_filename(raw: str) -> str:
    """Return a display-safe filename, or raise if nothing usable remains.

    Normalised to NFC first so visually identical names compare equal, then
    reduced to a conservative character set. Any directory component is
    discarded — a browser will not send one, but a scripted client can, and
    ``../../etc/passwd`` must not survive into a stored name that later reaches
    a header or a filesystem.

    Raises:
        InvalidFilenameError: nothing usable is left.
    """
    normalised = unicodedata.normalize("NFC", raw).strip()
    # Strip both separators: a Windows client sends backslashes, and posixpath
    # would treat the whole thing as one component.
    normalised = normalised.replace("\\", "/")
    normalised = posixpath.basename(normalised)

    cleaned = _UNSAFE_FILENAME.sub("_", normalised)
    cleaned = _DOT_RUN.sub(".", cleaned).strip(" .")
    cleaned = cleaned[:MAX_FILENAME_LENGTH].strip(" .")

    # Unsupported characters are *replaced* rather than dropped, so an accented
    # or non-Latin name keeps its shape instead of collapsing. The consequence
    # is that a name made entirely of them survives as a row of underscores —
    # technically usable, meaningless to read. Requiring at least one
    # alphanumeric character rejects that while leaving real names alone.
    if not cleaned or not any(character.isalnum() for character in cleaned):
        raise InvalidFilenameError
    return cleaned


def file_extension(filename: str) -> str:
    """Lower-cased extension including the dot, or ``""`` when there is none."""
    _stem, dot, suffix = filename.rpartition(".")
    if not dot or not suffix:
        return ""
    return f".{suffix.lower()}"


def validate_content_type(content_type: str, filename: str) -> str:
    """Check the declared type against the whitelist and the extension.

    Args:
        content_type: as declared by the client. Parameters such as
            ``; charset=utf-8`` are stripped before matching.
        filename: already sanitised.

    Returns:
        The normalised content type to store and to sign the upload with.

    Raises:
        UnsupportedFileTypeError: the type is not accepted, or the extension
            does not belong to it.
    """
    normalised = content_type.split(";", 1)[0].strip().lower()
    allowed_extensions = ALLOWED_CONTENT_TYPES.get(normalised)
    if allowed_extensions is None:
        raise UnsupportedFileTypeError(
            details={
                "content_type": normalised,
                "allowed": sorted(ALLOWED_CONTENT_TYPES),
            }
        )

    extension = file_extension(filename)
    if extension not in allowed_extensions:
        raise UnsupportedFileTypeError(
            "The file extension does not match the declared file type.",
            details={
                "content_type": normalised,
                "extension": extension or None,
                "expected": sorted(allowed_extensions),
            },
        )
    return normalised


def validate_size(size_bytes: int) -> int:
    """Check a byte count against the ceiling.

    Zero is rejected as well as oversized: an empty object is never a file the
    user meant to attach, and the table's CHECK constraint forbids it anyway —
    better a 413 than an IntegrityError surfacing as a 500.

    Raises:
        FileTooLargeError: outside ``0 < size <= MAX_ATTACHMENT_BYTES``.
    """
    if size_bytes <= 0 or size_bytes > MAX_ATTACHMENT_BYTES:
        raise FileTooLargeError(
            details={"size_bytes": size_bytes, "max_bytes": MAX_ATTACHMENT_BYTES}
        )
    return size_bytes


def build_storage_key(organization_id: uuid.UUID, attachment_id: uuid.UUID) -> str:
    """Object key for an attachment: ``{orgId}/{attachmentId}`` (doc 13).

    Composed only of two server-generated UUIDs. No part of it comes from the
    client, so a crafted filename cannot escape the organization's prefix and
    reach another tenant's objects — which is what makes the prefix a boundary
    rather than a naming convention.
    """
    return f"{organization_id}/{attachment_id}"


__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "MAX_FILENAME_LENGTH",
    "FileTooLargeError",
    "InvalidFilenameError",
    "UnsupportedFileTypeError",
    "build_storage_key",
    "file_extension",
    "sanitize_filename",
    "validate_content_type",
    "validate_size",
]
