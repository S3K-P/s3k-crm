"""S3-compatible object storage for attachments (ADR-014, `P2-W19-BE-02`).

Cloudflare R2 in deployed environments, MinIO in local development and in the
integration suite. Both implement the S3 API, so **one** boto3 client serves
both and only the endpoint and credentials differ — which is the point: the
code exercised by `tests/integration/test_attachments.py` is byte-for-byte the
code that runs against R2, not a stand-in that can drift from it.

Bytes never pass through this process. The browser PUTs directly to storage
against a pre-signed URL and GETs the same way (doc 13 "File Upload Security"),
so the API stays out of the data path entirely — no 50 MB request bodies, no
streaming, and no opportunity for the application to become the bottleneck on
a large file.

**Why boto3 and not an async client.** ADR-014 names boto3, and the two
operations that touch the network here — ``head`` and ``delete`` — are small,
infrequent metadata calls. They run through :func:`asyncio.to_thread` so a slow
storage endpoint cannot block the event loop. Signing is pure local
computation: it makes no network call at all, which is why the pre-signed URL
methods are not threaded.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import structlog
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import status

from app.core.config import Settings
from app.core.exceptions import AppError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mypy_boto3_s3.client import S3Client

logger = structlog.get_logger(__name__)

#: Error codes S3 and R2 use for "no such object". Both spellings occur:
#: ``HeadObject`` answers ``404`` while ``GetObject`` answers ``NoSuchKey``.
_MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class StorageNotConfiguredError(AppError):
    """Object storage has no bucket or credentials in this environment.

    A 503 rather than a 500: nothing is broken, the deployment simply has no
    storage wired up. Reported before any metadata row is written, so a
    developer running without MinIO gets a clear answer instead of an
    attachment stuck in ``PENDING`` forever.

    Unreachable outside development — ``Settings`` refuses to start staging or
    production without storage configured.
    """

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "storage_not_configured"
    message = (
        "File storage is not configured for this environment, so attachments "
        "cannot be uploaded or downloaded."
    )


class StorageUnavailableError(AppError):
    """Object storage is configured but did not answer."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "storage_unavailable"
    message = "File storage is temporarily unavailable. Please try again."


@dataclass(frozen=True, slots=True)
class StorageObject:
    """What storage reports about an object that actually landed.

    Read back with ``HeadObject`` after the browser's PUT and used to check the
    upload against the limits, because everything the *client* said at
    upload-url time was a claim about a file it had not sent yet.
    """

    size_bytes: int
    content_type: str | None
    etag: str | None


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    """A single-use instruction for the browser to PUT one object."""

    url: str
    method: str
    #: Headers the browser **must** send verbatim. They are part of the
    #: signature, so altering one invalidates the URL — which is exactly how
    #: the declared content type is bound to the upload.
    headers: dict[str, str]
    expires_at: dt.datetime


@runtime_checkable
class ObjectStorage(Protocol):
    """The storage operations the documents module needs.

    A Protocol so the service layer can be unit-tested against an in-memory
    double without reaching for a network, while the only implementation that
    ever runs — in development, in the integration suite and in production —
    is :class:`S3ObjectStorage`.
    """

    async def presigned_upload(
        self, key: str, *, content_type: str, content_length: int, ttl_seconds: int
    ) -> PresignedUpload: ...

    async def presigned_download(
        self, key: str, *, filename: str, ttl_seconds: int
    ) -> tuple[str, dt.datetime]: ...

    async def head(self, key: str) -> StorageObject | None: ...

    async def delete(self, key: str) -> None: ...


class S3ObjectStorage:
    """boto3 against any S3-compatible endpoint."""

    def __init__(self, settings: Settings) -> None:
        if not settings.storage_configured:
            raise StorageNotConfiguredError
        # Narrowed by the guard above; mypy cannot see through the property.
        assert settings.storage_bucket is not None  # noqa: S101
        self._bucket = settings.storage_bucket
        self._settings = settings
        self._signing_client = self._build_client(settings.storage_endpoint_url)
        # A second client only when the browser reaches storage on a different
        # host than the API does (Docker). Signing is host-specific: a URL
        # signed for ``minio:9000`` does not verify when presented to
        # ``localhost:9000``, so the two cannot share one client.
        browser_endpoint = settings.storage_browser_endpoint_url
        self._browser_client = (
            self._signing_client
            if browser_endpoint == settings.storage_endpoint_url
            else self._build_client(browser_endpoint)
        )

    def _build_client(self, endpoint_url: str | None) -> S3Client:
        import boto3

        client: S3Client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=self._settings.storage_region,
            aws_access_key_id=self._settings.storage_access_key_id,
            aws_secret_access_key=self._settings.storage_secret_access_key,
            config=Config(
                # SigV4 is required by R2 and is what MinIO expects too.
                signature_version="s3v4",
                s3={
                    "addressing_style": "path"
                    if self._settings.storage_force_path_style
                    else "auto"
                },
                connect_timeout=self._settings.storage_connect_timeout_seconds,
                read_timeout=self._settings.storage_read_timeout_seconds,
                # A stuck upload must surface as an error, not as a hung
                # request holding a database transaction open behind it.
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        return client

    # --- Signing (no network) ----------------------------------------------

    async def presigned_upload(
        self, key: str, *, content_type: str, content_length: int, ttl_seconds: int
    ) -> PresignedUpload:
        """A URL the browser may PUT exactly one object to.

        ``ContentType`` and ``ContentLength`` are signed parameters, not
        advisory ones, and they fail differently — both verified against MinIO
        rather than assumed:

        * **Content type.** Sending a different one is rejected outright with
          403, because the header is part of the signature.
        * **Content length.** Sending a different *declared* length is likewise
          a 403. Declaring the signed length while streaming a larger body is
          accepted by the server, but HTTP reads exactly ``Content-Length``
          bytes, so the object stored is **truncated** to the size that was
          signed. A URL issued for a 2 KB PDF therefore cannot be used to store
          2 GB — the excess is discarded rather than refused.

        Truncation is a silent failure from the client's point of view, which
        is precisely why confirmation re-reads the object with ``HeadObject``
        and re-validates its real size rather than trusting that the upload
        went as instructed.
        """
        params: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": content_length,
        }
        url = self._browser_client.generate_presigned_url(
            "put_object", Params=params, ExpiresIn=ttl_seconds, HttpMethod="PUT"
        )
        return PresignedUpload(
            url=url,
            method="PUT",
            headers={
                "Content-Type": content_type,
                "Content-Length": str(content_length),
            },
            expires_at=_expires_at(ttl_seconds),
        )

    async def presigned_download(
        self, key: str, *, filename: str, ttl_seconds: int
    ) -> tuple[str, dt.datetime]:
        """A short-lived read URL (doc 13: 15-minute TTL).

        ``ResponseContentDisposition`` makes the browser save the object under
        the name the user uploaded rather than the opaque storage key, and
        ``attachment`` stops it rendering inline — an uploaded HTML or SVG file
        served inline from a storage origin would be a stored-XSS vector.
        """
        url = self._browser_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ResponseContentDisposition": _content_disposition(filename),
            },
            ExpiresIn=ttl_seconds,
            HttpMethod="GET",
        )
        return url, _expires_at(ttl_seconds)

    # --- Network operations ------------------------------------------------

    async def head(self, key: str) -> StorageObject | None:
        """What storage actually holds at ``key``, or ``None`` if nothing does.

        The truth against which an upload is confirmed. A missing object is a
        normal outcome — the browser may never have completed the PUT — so it
        returns ``None`` rather than raising.
        """

        def _head() -> StorageObject | None:
            try:
                response = self._signing_client.head_object(
                    Bucket=self._bucket, Key=key
                )
            except ClientError as error:
                if _is_missing(error):
                    return None
                raise
            return StorageObject(
                size_bytes=int(response.get("ContentLength", 0)),
                content_type=response.get("ContentType"),
                etag=(response.get("ETag") or "").strip('"') or None,
            )

        return await self._run(_head, operation="head", key=key)

    async def delete(self, key: str) -> None:
        """Remove an object. Deleting a key that is already gone succeeds.

        S3 delete is idempotent by design, and relying on that matters here:
        the cleanup path runs after a failure whose exact point is unknown, so
        it must not itself fail because the object never landed.
        """

        def _delete() -> None:
            self._signing_client.delete_object(Bucket=self._bucket, Key=key)

        await self._run(_delete, operation="delete", key=key)

    async def _run[T](self, call: Callable[[], T], *, operation: str, key: str) -> T:
        """Run a blocking boto3 call off the event loop, mapping its failures.

        Raises:
            StorageUnavailableError: the endpoint refused, timed out or
                answered with an error this module does not treat as normal.
                The underlying message goes to the log, never to the client —
                it can name buckets, hosts and account ids.
        """
        try:
            return await asyncio.to_thread(call)
        except (BotoCoreError, ClientError) as error:
            logger.error(
                "object_storage_call_failed",
                operation=operation,
                key=key,
                error=str(error),
            )
            raise StorageUnavailableError from error


def _is_missing(error: ClientError) -> bool:
    response: dict[str, Any] = error.response  # type: ignore[assignment]
    code = str(response.get("Error", {}).get("Code", ""))
    if code in _MISSING_CODES:
        return True
    return int(response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)) == 404


def _expires_at(ttl_seconds: int) -> dt.datetime:
    return dt.datetime.now(dt.UTC) + dt.timedelta(seconds=ttl_seconds)


def _content_disposition(filename: str) -> str:
    """RFC 6266 disposition header that survives non-ASCII filenames.

    The plain ``filename`` parameter cannot carry them, so a UTF-8 ``filename*``
    is sent alongside an ASCII-only fallback. Quotes and backslashes are
    stripped from the fallback: unescaped, either would let a crafted filename
    break out of the quoted string and inject header parameters.
    """
    from urllib.parse import quote

    ascii_name = filename.encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace('"', "").replace("\\", "").strip()
    fallback = ascii_name or "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


def build_storage(settings: Settings) -> ObjectStorage | None:
    """The storage client for this process, or ``None`` when unconfigured.

    Built once during application startup rather than per request: boto3 client
    construction parses configuration and builds a signer, which is far from
    free, and the client is thread-safe for the calls made here.
    """
    if not settings.storage_configured:
        logger.info(
            "object_storage_not_configured",
            detail=(
                "Attachment endpoints will report 503. Set STORAGE_BUCKET, "
                "STORAGE_ACCESS_KEY_ID and STORAGE_SECRET_ACCESS_KEY to enable them."
            ),
        )
        return None
    return S3ObjectStorage(settings)


__all__ = [
    "ObjectStorage",
    "PresignedUpload",
    "S3ObjectStorage",
    "StorageNotConfiguredError",
    "StorageObject",
    "StorageUnavailableError",
    "build_storage",
]
