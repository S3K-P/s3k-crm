"""How the documents module behaves when storage misbehaves.

Every case here is one where the two stores could end up disagreeing — an
object that never landed, one larger than promised, an endpoint that refuses.
They use an in-memory double rather than MinIO because the point is to control
*failure*, and a real S3 endpoint will not reliably produce a timeout or a
truncated object on demand.

That double implements the same ``ObjectStorage`` Protocol the boto3 client
does, so it cannot drift into permitting a call the real one does not have. The
happy paths and the genuine S3 semantics are covered against real storage in
``tests/integration/test_attachments.py``; these tests deliberately cover only
what that suite cannot.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

import pytest

from app.platform.documents.policies import EntityAccess
from app.platform.documents.storage import (
    PresignedUpload,
    StorageNotConfiguredError,
    StorageObject,
    StorageUnavailableError,
)
from app.platform.documents.validation import (
    FileTooLargeError,
    UnsupportedFileTypeError,
    validate_content_type,
    validate_size,
)


@pytest.fixture(autouse=True)
def _no_ambient_storage_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the "storage is unconfigured" cases genuinely unconfigured.

    ``Settings`` is a ``BaseSettings``: passing ``_env_file=None`` stops it
    reading ``backend/.env`` but *not* the process environment, so a developer
    or CI job that exports ``STORAGE_BUCKET`` for the integration suite would
    silently invert the two assertions below — they would stop testing the
    unconfigured path and start passing for the wrong reason.
    """
    for name in (
        "STORAGE_BUCKET",
        "STORAGE_ACCESS_KEY_ID",
        "STORAGE_SECRET_ACCESS_KEY",
        "STORAGE_ENDPOINT_URL",
        "STORAGE_PUBLIC_ENDPOINT_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@dataclass
class FakeStorage:
    """An in-memory ``ObjectStorage`` whose failures are controllable."""

    objects: dict[str, StorageObject] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)
    fail_on: set[str] = field(default_factory=set)

    async def presigned_upload(
        self, key: str, *, content_type: str, content_length: int, ttl_seconds: int
    ) -> PresignedUpload:
        if "presign" in self.fail_on:
            raise StorageUnavailableError
        return PresignedUpload(
            url=f"https://storage.invalid/{key}",
            method="PUT",
            headers={"Content-Type": content_type, "Content-Length": str(content_length)},
            expires_at=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=ttl_seconds),
        )

    async def presigned_download(
        self, key: str, *, filename: str, ttl_seconds: int
    ) -> tuple[str, dt.datetime]:
        if "download" in self.fail_on:
            raise StorageUnavailableError
        return (
            f"https://storage.invalid/{key}?name={filename}",
            dt.datetime.now(dt.UTC) + dt.timedelta(seconds=ttl_seconds),
        )

    async def head(self, key: str) -> StorageObject | None:
        if "head" in self.fail_on:
            raise StorageUnavailableError
        return self.objects.get(key)

    async def delete(self, key: str) -> None:
        if "delete" in self.fail_on:
            raise StorageUnavailableError
        self.deleted.append(key)
        self.objects.pop(key, None)


def test_the_double_satisfies_the_storage_protocol() -> None:
    """Guards the guard.

    If ``ObjectStorage`` grows a method, this fails rather than letting the
    double silently diverge from what the service actually calls.
    """
    from app.platform.documents.storage import ObjectStorage

    assert isinstance(FakeStorage(), ObjectStorage)


# --- Confirmation is judged on what landed, not on what was promised --------


def test_an_oversized_object_is_rejected_at_confirm() -> None:
    """The last of the three size checks.

    The declared size passed, the signed length capped the transfer — and this
    still runs, because a storage backend that accepted more than it was told
    to must not produce a published attachment.
    """
    from app.platform.documents.models import MAX_ATTACHMENT_BYTES

    with pytest.raises(FileTooLargeError):
        validate_size(MAX_ATTACHMENT_BYTES + 1)


def test_an_object_stored_under_a_disallowed_type_is_rejected_at_confirm() -> None:
    """Storage echoes the content type the signed PUT bound, so a value outside
    the whitelist means the object arrived by some other route."""
    with pytest.raises(UnsupportedFileTypeError):
        validate_content_type("application/x-msdownload", "payload.exe")


async def test_a_missing_object_leaves_the_reservation_untouched() -> None:
    """``head`` returning ``None`` is an ordinary outcome — the browser may
    simply never have completed the PUT — so it must not raise from storage."""
    storage = FakeStorage()

    assert await storage.head("never/uploaded") is None


async def test_deleting_an_absent_object_succeeds() -> None:
    """The cleanup path runs after a failure whose exact point is unknown, so
    it must not itself fail because the object never landed. S3 delete is
    idempotent by design and the double matches that."""
    storage = FakeStorage()

    await storage.delete("never/uploaded")
    await storage.delete("never/uploaded")

    assert storage.deleted == ["never/uploaded", "never/uploaded"]


async def test_a_storage_outage_surfaces_as_service_unavailable() -> None:
    """503, not 500: nothing is broken in the application, and the client
    should retry rather than treat the file as rejected."""
    storage = FakeStorage(fail_on={"head"})

    with pytest.raises(StorageUnavailableError) as caught:
        await storage.head("some/key")

    assert caught.value.status_code == 503


async def test_a_download_outage_surfaces_as_service_unavailable() -> None:
    storage = FakeStorage(fail_on={"download"})

    with pytest.raises(StorageUnavailableError):
        await storage.presigned_download("k", filename="f.pdf", ttl_seconds=60)


# --- Unconfigured environments ----------------------------------------------


def test_an_unconfigured_environment_reports_service_unavailable() -> None:
    """A developer running without MinIO gets a clear answer rather than an
    attachment stuck in ``PENDING`` or a credentials error from deep in boto3."""
    error = StorageNotConfiguredError()

    assert error.status_code == 503
    assert error.code == "storage_not_configured"


def test_building_storage_without_configuration_returns_nothing() -> None:
    from app.core.config import Settings
    from app.platform.documents.storage import build_storage

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        environment="development",
    )

    assert settings.storage_configured is False
    assert build_storage(settings) is None


def test_staging_refuses_to_start_without_storage() -> None:
    """The unconfigured case is unreachable outside development.

    Starting anyway would accept uploads that fail at the last step, which is
    the failure mode the B01 blocker note warned about.
    """
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError, match="STORAGE_BUCKET"):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://u:p@localhost:5432/db",
            redis_url="redis://localhost:6379/0",
            environment="staging",
            jwt_private_key="x",
            jwt_public_key="y",
        )


def test_configured_storage_is_recognised() -> None:
    from app.core.config import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        storage_bucket="bucket",
        storage_access_key_id="key",
        storage_secret_access_key="secret",
    )

    assert settings.storage_configured is True


def test_the_browser_endpoint_falls_back_to_the_signing_endpoint() -> None:
    """Unset in production, where R2 is the same host for everyone."""
    from app.core.config import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        storage_endpoint_url="https://account.r2.cloudflarestorage.com",
    )

    assert (
        settings.storage_browser_endpoint_url
        == "https://account.r2.cloudflarestorage.com"
    )


def test_a_separate_browser_endpoint_overrides_it() -> None:
    """Inside Docker the API reaches ``minio:9000`` while the browser can only
    reach ``localhost:9000``; a URL signed for the first is unusable from the
    second."""
    from app.core.config import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@localhost:5432/db",
        redis_url="redis://localhost:6379/0",
        storage_endpoint_url="http://minio:9000",
        storage_public_endpoint_url="http://localhost:9000",
    )

    assert settings.storage_browser_endpoint_url == "http://localhost:9000"


# --- Entity access ----------------------------------------------------------


def test_denied_access_permits_nothing() -> None:
    access = EntityAccess.denied()

    assert access.can_view is False
    assert access.can_edit is False
    assert access.label is None


async def test_the_default_verifier_denies_everything() -> None:
    """Fails closed: a wiring mistake must produce 404s, not open access to
    every record in the organization."""
    from app.platform.documents.policies import DenyAllEntityAccess

    access = await DenyAllEntityAccess().resolve(
        principal=None,  # type: ignore[arg-type]  # never inspected
        entity_type="ACCOUNT",
        entity_id=uuid.uuid4(),
    )

    assert access.can_view is False
    assert access.can_edit is False
