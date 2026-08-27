"""Attachments end to end: real PostgreSQL, real S3-compatible storage.

Storage here is MinIO from ``docker compose``, not a stub. That is the whole
point of the arrangement: MinIO implements the S3 API, so every assertion below
exercises the same ``boto3`` pre-sign / PUT / ``HeadObject`` / ``DeleteObject``
path that runs against Cloudflare R2 in production (ADR-014). A double would
have proved that the code calls itself correctly and nothing more.

Uploads go through the real three-step flow — ask for a URL, PUT the bytes
directly to storage, confirm — because the interesting failures live in the
gaps between those steps: an object that never lands, one that lands larger
than promised, one whose row belongs to another tenant.

Grouped by the question each set answers:

**Does the happy path work**, and is the metadata what was actually stored
rather than what the client claimed?

**Is it authorized** — module permission, tenant, and the CRM record's own
record-level visibility, which is the check an attachment endpoint could most
easily become a way around.

**Does it fail safely** — rejected uploads leaving neither an object nor a row,
a storage outage not producing a half-attached file.

**Is it audited**, since a pre-signed URL is a bearer credential and the trail
is the only tenant-visible record of who read which file.
"""

from __future__ import annotations

import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.platform.documents.models import MAX_ATTACHMENT_BYTES
from tests.integration.conftest import ApiSession, Tenant, scope_session_to

pytestmark = pytest.mark.integration

PDF_BYTES = b"%PDF-1.7\n% a small but genuine-looking document\n"
PDF_TYPE = "application/pdf"


# --- Helpers ----------------------------------------------------------------


def _require_storage(settings: Settings) -> None:
    if not settings.storage_configured:  # pragma: no cover - environment dependent
        pytest.skip(
            "object storage is not configured; run `docker compose up -d minio "
            "minio-init` and set STORAGE_* in backend/.env"
        )


# S310 flags ``urlopen`` on a non-literal URL. Every URL below was produced by
# this application's own pre-signer and points at the MinIO container from
# docker-compose; none of it is caller-supplied. The whole purpose of these
# helpers is to be the browser, which is the one participant in the upload flow
# the test client cannot stand in for.


def _put(url: str, headers: dict[str, str], body: bytes) -> int:
    """PUT bytes straight to storage, exactly as a browser would."""
    request = urllib.request.Request(url, data=body, method="PUT", headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as error:  # pragma: no cover - failure paths
        return int(error.code)


def _get(url: str) -> tuple[int, bytes, str | None]:
    try:
        with urllib.request.urlopen(url) as response:  # noqa: S310
            return (
                int(response.status),
                response.read(),
                response.headers.get("Content-Disposition"),
            )
    except urllib.error.HTTPError as error:
        return int(error.code), b"", None


def _account(session: ApiSession, name: str = "Attachable Ltd", **extra: object) -> str:
    created = session.post("/crm/accounts", json={"name": name, **extra})
    assert created.status_code == 201, created.text
    account_id: str = created.json()["id"]
    return account_id


def _reserve(
    session: ApiSession,
    entity_id: str,
    *,
    entity_type: str = "ACCOUNT",
    filename: str = "contract.pdf",
    content_type: str = PDF_TYPE,
    size_bytes: int | None = None,
) -> Any:
    return session.post(
        "/attachments/upload-url",
        json={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(PDF_BYTES) if size_bytes is None else size_bytes,
        },
    )


def _upload(
    session: ApiSession,
    entity_id: str,
    *,
    entity_type: str = "ACCOUNT",
    filename: str = "contract.pdf",
    body: bytes = PDF_BYTES,
    content_type: str = PDF_TYPE,
) -> dict[str, Any]:
    """The full three-step flow, returning the confirmed attachment."""
    reserved = _reserve(
        session,
        entity_id,
        entity_type=entity_type,
        filename=filename,
        content_type=content_type,
        size_bytes=len(body),
    )
    assert reserved.status_code == 201, reserved.text
    ticket = reserved.json()

    assert _put(ticket["upload_url"], ticket["headers"], body) == 200

    confirmed = session.post(f"/attachments/{ticket['attachment']['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    result: dict[str, Any] = confirmed.json()
    return result


def _audit_actions(session: ApiSession, **params: object) -> list[str]:
    response = session.get("/audit-logs", params={"module": "documents", **params})
    assert response.status_code == 200, response.text
    return [entry["action"] for entry in response.json()["data"]]


@pytest.fixture(autouse=True)
def storage_required(integration_settings: Settings) -> None:
    _require_storage(integration_settings)


@pytest.fixture
def as_alpha_manager(api: ApiSession, alpha: Tenant) -> ApiSession:
    """Manager: holds documents.DELETE and VIEW_ALL across the CRM."""
    api.login(alpha.manager.email, organization_id=alpha.organization_id)
    return api


@pytest.fixture
def as_beta_admin(
    client: TestClient, integration_settings: Settings, beta: Tenant
) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(beta.admin.email, organization_id=beta.organization_id)
    return session


@pytest.fixture
def member_session(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> Iterator[ApiSession]:
    """A plain User on their own session.

    Separate from the shared ``as_alpha_member`` fixture because these tests
    need an admin *and* a member at once, and both shipped fixtures wrap the
    same ``ApiSession`` — requesting them together would have the second login
    overwrite the first token.
    """
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    yield session


# =============================================================================
# The happy path
# =============================================================================


def test_a_file_can_be_uploaded_and_downloaded(as_alpha_admin: ApiSession) -> None:
    """The whole contract in one test: reserve, PUT, confirm, read back."""
    account_id = _account(as_alpha_admin)

    attachment = _upload(as_alpha_admin, account_id, filename="proposal.pdf")

    assert attachment["status"] == "ACTIVE"
    assert attachment["name"] == "proposal.pdf"
    assert attachment["mime_type"] == PDF_TYPE
    assert attachment["size_bytes"] == len(PDF_BYTES)
    assert attachment["entity_id"] == account_id
    assert attachment["checksum"]

    ticket = as_alpha_admin.get(f"/attachments/{attachment['id']}/download-url")
    assert ticket.status_code == 200, ticket.text

    status_code, body, disposition = _get(ticket.json()["url"])

    assert status_code == 200
    assert body == PDF_BYTES
    # Never inline: an uploaded file rendered by the browser from the storage
    # origin would be a stored-XSS vector.
    assert disposition is not None
    assert disposition.startswith("attachment;")
    assert "proposal.pdf" in disposition


def test_metadata_reflects_what_storage_holds_not_what_the_client_claimed(
    as_alpha_admin: ApiSession,
) -> None:
    """Confirmation reads ``HeadObject``; the request body is only a claim.

    The client here under-declares the size. The PUT is signed for the declared
    length, so storage truncates to it — and the row records the truncated
    reality rather than either number the client chose.
    """
    account_id = _account(as_alpha_admin)
    declared = 8
    reserved = _reserve(as_alpha_admin, account_id, size_bytes=declared)
    ticket = reserved.json()

    _put(ticket["upload_url"], ticket["headers"], b"x" * 4000)
    confirmed = as_alpha_admin.post(
        f"/attachments/{ticket['attachment']['id']}/confirm"
    )

    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["size_bytes"] == declared


async def test_the_storage_key_is_prefixed_with_the_organization(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
) -> None:
    """Doc 13: ``{orgId}/{documentId}``.

    The prefix is the boundary that keeps one tenant's objects unreachable from
    another's, so it is asserted against the stored row rather than assumed.
    The key is deliberately absent from the API response, which is why this
    reads the database directly.
    """
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id)

    async with session_factory() as session:
        # ``platform.attachments`` is RLS-FORCEd: an unscoped read returns no
        # rows and `scalar_one` would raise, which says nothing about the key.
        await scope_session_to(session, alpha.organization_id)
        key = str(
            (
                await session.execute(
                    text("SELECT storage_key FROM platform.attachments WHERE id = :id"),
                    {"id": uuid.UUID(attachment["id"])},
                )
            ).scalar_one()
        )

    assert key == f"{alpha.organization_id}/{attachment['id']}"
    # No part of it comes from the client, so a crafted filename cannot escape
    # the prefix and reach another tenant's objects.
    assert attachment["name"] not in key


def test_the_storage_key_is_never_returned_over_the_api(
    as_alpha_admin: ApiSession,
) -> None:
    """It is an internal object address; publishing it maps the bucket."""
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id)

    assert "storage_key" not in attachment
    listed = as_alpha_admin.get(
        "/attachments", params={"entity_type": "ACCOUNT", "entity_id": account_id}
    ).json()
    assert "storage_key" not in str(listed)


def test_attachments_list_for_a_record(as_alpha_admin: ApiSession) -> None:
    account_id = _account(as_alpha_admin)
    _upload(as_alpha_admin, account_id, filename="one.pdf")
    _upload(as_alpha_admin, account_id, filename="two.pdf")

    page = as_alpha_admin.get(
        "/attachments", params={"entity_type": "ACCOUNT", "entity_id": account_id}
    ).json()

    assert page["pagination"]["total"] == 2
    assert {item["name"] for item in page["data"]} == {"one.pdf", "two.pdf"}


def test_a_reserved_upload_is_invisible_until_confirmed(
    as_alpha_admin: ApiSession,
) -> None:
    """A ``PENDING`` row exists for every URL ever issued, including abandoned
    ones. Listing them would show files that do not exist."""
    account_id = _account(as_alpha_admin)
    reserved = _reserve(as_alpha_admin, account_id)
    assert reserved.status_code == 201

    page = as_alpha_admin.get(
        "/attachments", params={"entity_type": "ACCOUNT", "entity_id": account_id}
    ).json()

    assert page["pagination"]["total"] == 0


def test_attachments_can_hang_off_every_attachable_crm_record(
    as_alpha_admin: ApiSession,
) -> None:
    """Accounts, contacts, leads, opportunities and campaigns."""
    account_id = _account(as_alpha_admin, name="Multi Ltd")
    contact_id = as_alpha_admin.post(
        "/crm/contacts", json={"first_name": "Ada", "last_name": "Lovelace"}
    ).json()["id"]
    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Alan", "last_name": "Turing"}
    ).json()["id"]
    campaign_id = as_alpha_admin.post(
        "/crm/campaigns", json={"name": "Spring Push", "type": "EMAIL"}
    ).json()["id"]

    for entity_type, entity_id in [
        ("ACCOUNT", account_id),
        ("CONTACT", contact_id),
        ("LEAD", lead_id),
        ("CAMPAIGN", campaign_id),
    ]:
        attachment = _upload(
            as_alpha_admin, entity_id, entity_type=entity_type, filename="brief.pdf"
        )
        assert attachment["entity_type"] == entity_type


def test_an_unattachable_entity_type_is_refused(as_alpha_admin: ApiSession) -> None:
    """A file belongs on a record, not on a note about one.

    404 rather than 422: an unknown type and an unreachable record give the
    same answer, so probing cannot distinguish them.
    """
    account_id = _account(as_alpha_admin)

    response = _reserve(as_alpha_admin, account_id, entity_type="NOTE")

    assert response.status_code == 404


# =============================================================================
# Validation
# =============================================================================


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("payload.exe", "application/x-msdownload"),
        ("script.sh", "text/x-shellscript"),
        # Both can carry script and would run against the storage origin.
        ("page.html", "text/html"),
        ("vector.svg", "image/svg+xml"),
    ],
)
def test_a_type_outside_the_whitelist_is_rejected(
    as_alpha_admin: ApiSession, filename: str, content_type: str
) -> None:
    account_id = _account(as_alpha_admin)

    response = _reserve(
        as_alpha_admin, account_id, filename=filename, content_type=content_type
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_an_extension_contradicting_the_declared_type_is_rejected(
    as_alpha_admin: ApiSession,
) -> None:
    """The mismatch a whitelist alone misses: ``payload.exe`` declared as PDF.

    Without this, an executable would be stored under a trusted content type
    and handed back with it on download.
    """
    account_id = _account(as_alpha_admin)

    response = _reserve(
        as_alpha_admin, account_id, filename="payload.exe", content_type=PDF_TYPE
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_a_file_over_the_ceiling_is_rejected(as_alpha_admin: ApiSession) -> None:
    """50 MB (doc 13), refused before anything reaches storage."""
    account_id = _account(as_alpha_admin)

    response = _reserve(
        as_alpha_admin, account_id, size_bytes=MAX_ATTACHMENT_BYTES + 1
    )

    assert response.status_code == 422  # schema bound rejects it first


def test_an_empty_file_is_rejected(as_alpha_admin: ApiSession) -> None:
    account_id = _account(as_alpha_admin)

    response = _reserve(as_alpha_admin, account_id, size_bytes=0)

    assert response.status_code == 422


def test_a_traversal_filename_is_sanitised_rather_than_stored(
    as_alpha_admin: ApiSession,
) -> None:
    """The key is server-generated, so this protects the *metadata*.

    The name is displayed in the CRM and echoed in a ``Content-Disposition``
    header, so the directory component must not survive into it.
    """
    account_id = _account(as_alpha_admin)

    attachment = _upload(
        as_alpha_admin, account_id, filename="../../../etc/passwd.pdf"
    )

    assert attachment["name"] == "passwd.pdf"
    assert "/" not in attachment["name"]
    assert ".." not in attachment["name"]


def test_confirming_before_the_object_lands_is_a_conflict(
    as_alpha_admin: ApiSession,
) -> None:
    """Nothing was uploaded, so there is nothing to publish."""
    account_id = _account(as_alpha_admin)
    reserved = _reserve(as_alpha_admin, account_id).json()

    response = as_alpha_admin.post(
        f"/attachments/{reserved['attachment']['id']}/confirm"
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "attachment_not_ready"


def test_confirming_twice_is_idempotent(as_alpha_admin: ApiSession) -> None:
    """A client that retries a confirm whose response it never saw."""
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id)

    again = as_alpha_admin.post(f"/attachments/{attachment['id']}/confirm")

    assert again.status_code == 200
    assert again.json()["id"] == attachment["id"]


def test_downloading_an_unconfirmed_attachment_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    account_id = _account(as_alpha_admin)
    reserved = _reserve(as_alpha_admin, account_id).json()

    response = as_alpha_admin.get(
        f"/attachments/{reserved['attachment']['id']}/download-url"
    )

    assert response.status_code == 409


# =============================================================================
# Failing safely
# =============================================================================


def test_an_abandoned_upload_leaves_neither_row_nor_object(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The browser cleaning up after a cancelled or failed PUT.

    Both stores must end empty: a lingering object is storage nobody can find,
    and a lingering row is a download that 404s.
    """
    account_id = _account(as_alpha_admin)
    reserved = _reserve(as_alpha_admin, account_id).json()
    attachment_id = reserved["attachment"]["id"]
    _put(reserved["upload_url"], reserved["headers"], PDF_BYTES)

    response = as_alpha_admin.delete(f"/attachments/{attachment_id}/upload")
    assert response.status_code == 204

    assert as_alpha_admin.get(f"/attachments/{attachment_id}").status_code == 404


def test_abandoning_a_published_attachment_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    """Removing a live file goes through DELETE, which audits and needs
    ``documents.DELETE``. The cleanup route must not become a way round it."""
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id)

    response = as_alpha_admin.delete(f"/attachments/{attachment['id']}/upload")

    assert response.status_code == 409


def test_deleting_removes_the_object_as_well_as_the_row(
    as_alpha_admin: ApiSession,
) -> None:
    """Proven by fetching a URL issued *before* the delete.

    Checking only that the API stops listing it would pass even if the bytes
    were still sitting in the bucket.
    """
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id)
    url = as_alpha_admin.get(f"/attachments/{attachment['id']}/download-url").json()[
        "url"
    ]
    assert _get(url)[0] == 200

    assert as_alpha_admin.delete(f"/attachments/{attachment['id']}").status_code == 204

    assert _get(url)[0] == 404
    assert as_alpha_admin.get(f"/attachments/{attachment['id']}").status_code == 404


async def test_a_download_url_stops_working_once_it_expires(
    integration_settings: Settings,
) -> None:
    """The TTL is the reason a leaked URL is survivable (doc 13, `P2-W19-QA-01`).

    A pre-signed URL is a bearer credential: anyone holding it can read the
    object, with no further authorization. That is only acceptable because it
    stops working — so the expiry is asserted against real storage rather than
    taken on trust from the ``ExpiresIn`` parameter.

    Signed here with a one-second TTL rather than the configured fifteen
    minutes, for obvious reasons.
    """
    import asyncio

    from app.platform.documents.storage import build_storage

    storage = build_storage(integration_settings)
    assert storage is not None

    key = f"{uuid.uuid4()}/{uuid.uuid4()}"
    upload = await storage.presigned_upload(
        key, content_type=PDF_TYPE, content_length=len(PDF_BYTES), ttl_seconds=300
    )
    assert _put(upload.url, upload.headers, PDF_BYTES) == 200

    try:
        url, _expires = await storage.presigned_download(
            key, filename="ephemeral.pdf", ttl_seconds=1
        )
        assert _get(url)[0] == 200, "the URL should work before it expires"

        await asyncio.sleep(2)

        assert _get(url)[0] == 403
    finally:
        await storage.delete(key)


def test_a_deleted_attachment_disappears_from_its_record(
    as_alpha_admin: ApiSession,
) -> None:
    account_id = _account(as_alpha_admin)
    keep = _upload(as_alpha_admin, account_id, filename="keep.pdf")
    drop = _upload(as_alpha_admin, account_id, filename="drop.pdf")

    as_alpha_admin.delete(f"/attachments/{drop['id']}")

    page = as_alpha_admin.get(
        "/attachments", params={"entity_type": "ACCOUNT", "entity_id": account_id}
    ).json()

    assert [item["id"] for item in page["data"]] == [keep["id"]]


# =============================================================================
# Authorization: tenant, module permission, record-level visibility
# =============================================================================


def test_an_unauthenticated_caller_is_refused(
    client: TestClient, integration_settings: Settings
) -> None:
    response = client.get(
        f"{integration_settings.api_prefix}/attachments",
        params={"entity_type": "ACCOUNT", "entity_id": str(uuid.uuid4())},
    )

    assert response.status_code == 401


def test_another_tenants_attachment_id_is_not_found(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """404, not 403: confirming the id is real would leak its existence."""
    beta_account = _account(as_beta_admin, name="Beta Ltd")
    beta_attachment = _upload(as_beta_admin, beta_account)

    assert as_alpha_admin.get(f"/attachments/{beta_attachment['id']}").status_code == 404
    assert (
        as_alpha_admin.get(
            f"/attachments/{beta_attachment['id']}/download-url"
        ).status_code
        == 404
    )
    assert (
        as_alpha_admin.delete(f"/attachments/{beta_attachment['id']}").status_code == 404
    )


def test_a_file_cannot_be_attached_to_another_tenants_record(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """The forged-id case: the row would carry alpha's organization while
    pointing at beta's account, and would pass RLS on the way in."""
    beta_account = _account(as_beta_admin, name="Beta Target Ltd")

    response = _reserve(as_alpha_admin, beta_account)

    assert response.status_code == 404


def test_listing_another_tenants_record_returns_nothing(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    beta_account = _account(as_beta_admin, name="Beta Listed Ltd")
    _upload(as_beta_admin, beta_account)

    response = as_alpha_admin.get(
        "/attachments", params={"entity_type": "ACCOUNT", "entity_id": beta_account}
    )

    assert response.status_code == 404


def test_a_user_cannot_reach_a_file_on_a_record_they_cannot_see(
    as_alpha_admin: ApiSession, member_session: ApiSession, alpha: Tenant
) -> None:
    """The check attachments could most easily have skipped.

    A plain User holds ``leads.VIEW`` but not ``leads.VIEW_ALL``, so a lead
    owned by somebody else is invisible to them. The file attached to it must
    be equally invisible — otherwise attachments become a way around
    record-level visibility rather than a thing it protects.
    """
    lead_id = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Private",
            "last_name": "Lead",
            "owner_id": str(alpha.admin.user_id),
        },
    ).json()["id"]
    attachment = _upload(as_alpha_admin, lead_id, entity_type="LEAD")

    # The admin's own lead is invisible to the member...
    assert member_session.get(f"/crm/leads/{lead_id}").status_code == 404
    # ...and so is everything hanging off it.
    assert member_session.get(f"/attachments/{attachment['id']}").status_code == 404
    assert (
        member_session.get(f"/attachments/{attachment['id']}/download-url").status_code
        == 404
    )
    assert (
        member_session.get(
            "/attachments", params={"entity_type": "LEAD", "entity_id": lead_id}
        ).status_code
        == 404
    )


def test_a_user_can_reach_files_on_a_record_they_own(
    member_session: ApiSession,
) -> None:
    """The other half: record-level visibility must not lock people out of
    their own work. Without this, the test above would pass on a bug that
    denied everything."""
    lead_id = member_session.post(
        "/crm/leads", json={"first_name": "My", "last_name": "Lead"}
    ).json()["id"]

    attachment = _upload(member_session, lead_id, entity_type="LEAD")

    assert (
        member_session.get(f"/attachments/{attachment['id']}").status_code == 200
    )


def test_a_user_without_delete_permission_cannot_delete(
    as_alpha_admin: ApiSession, member_session: ApiSession
) -> None:
    """The User role holds VIEW/CREATE/EDIT on documents, never DELETE."""
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id)

    response = member_session.delete(f"/attachments/{attachment['id']}")

    assert response.status_code == 403


def test_a_manager_may_delete(as_alpha_manager: ApiSession) -> None:
    """Manager holds ``documents.DELETE``; the negative test above would pass
    on a bug that refused everyone."""
    account_id = _account(as_alpha_manager)
    attachment = _upload(as_alpha_manager, account_id)

    assert as_alpha_manager.delete(f"/attachments/{attachment['id']}").status_code == 204


async def test_write_access_requires_edit_on_the_linked_module(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
) -> None:
    """Attaching or removing a file takes EDIT on the record, not merely VIEW.

    Exercised against the verifier directly rather than over HTTP: every
    *seeded* role holds EDIT on every CRM module, so no combination of the
    shipped roles can reach this branch through the API. A tenant-defined role
    can — that is the point of the permission being data — so the rule is
    pinned here where the permission set can be stated explicitly.
    """
    from app.platform.auth.dependencies import Principal
    from app.platform.auth.repository import AuthRepository
    from app.products.crm.shared.attachments import CrmEntityAccess

    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Edit", "last_name": "Check"}
    ).json()["id"]

    async with session_factory() as session:
        # The verifier reads `crm.leads`, which is RLS-FORCEd. A real request
        # always carries tenant scope; without it here the lead is invisible
        # and every answer comes back "cannot view" regardless of permissions,
        # which is not the branch under test.
        await scope_session_to(session, alpha.organization_id)

        user = await AuthRepository(session).get_user(alpha.admin.user_id)
        assert user is not None

        def principal_with(*codes: str) -> Principal:
            return Principal(
                user=user,
                organization_id=alpha.organization_id,
                membership_id=uuid.uuid4(),
                permissions=frozenset(codes),
            )

        verifier = CrmEntityAccess(session)

        read_only = await verifier.resolve(
            principal=principal_with("leads.VIEW", "leads.VIEW_ALL"),
            entity_type="LEAD",
            entity_id=uuid.UUID(lead_id),
        )
        writable = await verifier.resolve(
            principal=principal_with("leads.VIEW", "leads.VIEW_ALL", "leads.EDIT"),
            entity_type="LEAD",
            entity_id=uuid.UUID(lead_id),
        )

    assert read_only.can_view is True
    assert read_only.can_edit is False
    assert writable.can_view is True
    assert writable.can_edit is True


async def test_the_verifier_hides_a_record_owned_by_somebody_else(
    as_alpha_admin: ApiSession,
    session_factory: async_sessionmaker[AsyncSession],
    alpha: Tenant,
) -> None:
    """Without ``VIEW_ALL``, the visibility predicate is applied in SQL.

    The record simply does not come back, which is what makes "not yours" and
    "not there" the same answer.
    """
    from app.platform.auth.dependencies import Principal
    from app.platform.auth.repository import AuthRepository
    from app.products.crm.shared.attachments import CrmEntityAccess

    lead_id = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Owned",
            "last_name": "Elsewhere",
            "owner_id": str(alpha.admin.user_id),
        },
    ).json()["id"]

    async with session_factory() as session:
        member = await AuthRepository(session).get_user(alpha.member.user_id)
        assert member is not None
        access = await CrmEntityAccess(session).resolve(
            principal=Principal(
                user=member,
                organization_id=alpha.organization_id,
                membership_id=uuid.uuid4(),
                # VIEW but not VIEW_ALL: reads narrow to records they own.
                permissions=frozenset({"leads.VIEW", "leads.EDIT"}),
            ),
            entity_type="LEAD",
            entity_id=uuid.UUID(lead_id),
        )

    assert access.can_view is False
    assert access.can_edit is False
    assert access.label is None


# =============================================================================
# Audit integration
# =============================================================================


def test_uploading_is_audited(as_alpha_admin: ApiSession) -> None:
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id, filename="audited.pdf")

    entries = as_alpha_admin.get(
        "/audit-logs", params={"module": "documents", "action": "ATTACHMENT_UPLOADED"}
    ).json()["data"]

    assert len(entries) == 1
    entry = entries[0]
    assert entry["entity_type"] == "ATTACHMENT"
    assert entry["entity_id"] == attachment["id"]
    assert entry["entity_label"] == "audited.pdf"
    assert entry["details"]["linked_entity_id"] == account_id
    assert entry["details"]["size_bytes"] == len(PDF_BYTES)


def test_downloading_is_audited(as_alpha_admin: ApiSession) -> None:
    """Doc 13 requires access logging, and this is the only tenant-visible
    record of who read which file — storage's own logs are neither."""
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id)

    as_alpha_admin.get(f"/attachments/{attachment['id']}/download-url")

    assert "ATTACHMENT_DOWNLOADED" in _audit_actions(as_alpha_admin)


def test_the_audit_trail_never_stores_the_signed_url(
    as_alpha_admin: ApiSession,
) -> None:
    """A pre-signed URL is a live bearer credential for its whole TTL.

    Recording it would put a working download link for every file into a table
    every administrator can read.
    """
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id)
    url = as_alpha_admin.get(f"/attachments/{attachment['id']}/download-url").json()[
        "url"
    ]

    trail = str(as_alpha_admin.get("/audit-logs", params={"module": "documents"}).json())

    assert url not in trail
    assert "X-Amz-Signature" not in trail
    assert "Signature=" not in trail


def test_deleting_is_audited(as_alpha_admin: ApiSession) -> None:
    account_id = _account(as_alpha_admin)
    attachment = _upload(as_alpha_admin, account_id, filename="removed.pdf")

    as_alpha_admin.delete(f"/attachments/{attachment['id']}")

    entries = as_alpha_admin.get(
        "/audit-logs", params={"module": "documents", "action": "ATTACHMENT_DELETED"}
    ).json()["data"]

    assert len(entries) == 1
    assert entries[0]["entity_label"] == "removed.pdf"
    assert entries[0]["details"]["object_removed"] is True


def test_a_rejected_upload_writes_no_audit_record(
    as_alpha_admin: ApiSession,
) -> None:
    """Nothing was attached, so the trail must not say something was."""
    account_id = _account(as_alpha_admin)

    _reserve(as_alpha_admin, account_id, filename="payload.exe", content_type=PDF_TYPE)

    assert _audit_actions(as_alpha_admin) == []


def test_another_tenant_cannot_see_attachment_audit_records(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    beta_account = _account(as_beta_admin, name="Beta Audited Ltd")
    _upload(as_beta_admin, beta_account, filename="beta-secret.pdf")

    trail = str(as_alpha_admin.get("/audit-logs", params={"module": "documents"}).json())

    assert "beta-secret.pdf" not in trail
