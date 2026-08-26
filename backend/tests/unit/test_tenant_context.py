"""Tenant-context resolution and its fail-closed security posture.

The rule under test: a browser-supplied organization id is an assertion, never
an authorization. It is accepted only after membership verification.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import Settings
from app.core.tenant import (
    ORGANIZATION_HEADER,
    DenyAllMembershipVerifier,
    TenantContext,
    TenantContextError,
    get_tenant_context,
    require_tenant_context,
    reset_tenant_context,
    set_tenant_context,
)

ORG_A = uuid.UUID("11111111-1111-7111-8111-111111111111")
USER_A = uuid.UUID("22222222-2222-7222-8222-222222222222")


class AllowAllMembershipVerifier:
    """Stand-in for the Phase 1 membership check."""

    async def verify(self, *, organization_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
        return True


class StubPrincipalResolver:
    """Stands in for JWT verification.

    The middleware now requires an authenticated principal before it will even
    consider the organization header, so a membership verifier alone is no
    longer enough to establish context.
    """

    def __init__(self, user_id: uuid.UUID | None) -> None:
        self.user_id = user_id

    async def resolve(
        self, *, authorization: str | None, organization_header: uuid.UUID | None
    ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        return self.user_id, organization_header


class AllowOnlyMembershipVerifier:
    """Approves exactly one organization, like a real membership lookup."""

    def __init__(self, allowed: uuid.UUID) -> None:
        self.allowed = allowed

    async def verify(self, *, organization_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
        return organization_id == self.allowed


def _probe_app(
    settings: Settings,
    verifier: object | None,
    resolver: object | None = None,
) -> FastAPI:
    """Build an app with one endpoint that reports the resolved tenant."""
    router = APIRouter()

    @router.get("/tenant-probe")
    async def tenant_probe() -> dict[str, str | None]:
        context = get_tenant_context()
        return {
            "organization_id": str(context.organization_id) if context else None,
        }

    app = create_app(
        settings,
        membership_verifier=verifier,  # type: ignore[arg-type]
        principal_resolver=resolver or StubPrincipalResolver(USER_A),  # type: ignore[arg-type]
    )
    app.include_router(router, prefix=settings.api_prefix)
    return app


# --- contextvar plumbing ---------------------------------------------------


def test_context_is_none_by_default() -> None:
    assert get_tenant_context() is None


def test_set_and_reset_context() -> None:
    token = set_tenant_context(TenantContext(organization_id=ORG_A))
    try:
        current = get_tenant_context()
        assert current is not None
        assert current.organization_id == ORG_A
    finally:
        reset_tenant_context(token)

    assert get_tenant_context() is None


def test_require_tenant_context_raises_when_unset() -> None:
    """Code that reaches the database must never silently run unscoped."""
    with pytest.raises(TenantContextError):
        require_tenant_context()


def test_tenant_context_is_immutable() -> None:
    context = TenantContext(organization_id=ORG_A)

    with pytest.raises((AttributeError, TypeError)):
        context.organization_id = uuid.uuid4()  # type: ignore[misc]


# --- the security-critical behaviour ---------------------------------------


async def test_deny_all_verifier_rejects_every_organization() -> None:
    verifier = DenyAllMembershipVerifier()

    assert await verifier.verify(organization_id=ORG_A, user_id=None) is False
    assert await verifier.verify(organization_id=uuid.uuid4(), user_id=None) is False


def test_supplied_header_is_not_trusted_without_membership(settings: Settings) -> None:
    """Without a membership that verifies, the header is ignored entirely.

    The deny-all verifier is passed explicitly: since Phase 1 the *default*
    verifier is the database-backed one, so omitting it would open a
    connection rather than exercise the fail-closed path.
    """
    with TestClient(_probe_app(settings, DenyAllMembershipVerifier())) as client:
        response = client.get("/api/v1/tenant-probe", headers={ORGANIZATION_HEADER: str(ORG_A)})

    assert response.status_code == 200
    assert response.json()["organization_id"] is None


def test_header_is_accepted_once_membership_is_verified(settings: Settings) -> None:
    with TestClient(_probe_app(settings, AllowAllMembershipVerifier())) as client:
        response = client.get("/api/v1/tenant-probe", headers={ORGANIZATION_HEADER: str(ORG_A)})

    assert response.json()["organization_id"] == str(ORG_A)


def test_organization_the_caller_does_not_belong_to_is_rejected(
    settings: Settings,
) -> None:
    """The core forged-organizationId threat from doc 13's threat model."""
    other_org = uuid.uuid4()
    verifier = AllowOnlyMembershipVerifier(ORG_A)

    with TestClient(_probe_app(settings, verifier)) as client:
        allowed = client.get("/api/v1/tenant-probe", headers={ORGANIZATION_HEADER: str(ORG_A)})
        forged = client.get("/api/v1/tenant-probe", headers={ORGANIZATION_HEADER: str(other_org)})

    assert allowed.json()["organization_id"] == str(ORG_A)
    assert forged.json()["organization_id"] is None


def test_malformed_header_is_rejected_not_crashed(settings: Settings) -> None:
    with TestClient(_probe_app(settings, AllowAllMembershipVerifier())) as client:
        response = client.get("/api/v1/tenant-probe", headers={ORGANIZATION_HEADER: "not-a-uuid"})

    assert response.status_code == 200
    assert response.json()["organization_id"] is None


def test_missing_header_yields_no_context(settings: Settings) -> None:
    with TestClient(_probe_app(settings, AllowAllMembershipVerifier())) as client:
        response = client.get("/api/v1/tenant-probe")

    assert response.json()["organization_id"] is None


def test_context_does_not_leak_between_requests(settings: Settings) -> None:
    """A pooled worker must not carry one tenant's scope into the next request."""
    verifier = AllowAllMembershipVerifier()

    with TestClient(_probe_app(settings, verifier)) as client:
        scoped = client.get("/api/v1/tenant-probe", headers={ORGANIZATION_HEADER: str(ORG_A)})
        unscoped = client.get("/api/v1/tenant-probe")

    assert scoped.json()["organization_id"] == str(ORG_A)
    assert unscoped.json()["organization_id"] is None


def test_health_endpoints_stay_exempt_from_tenant_resolution(
    settings: Settings,
) -> None:
    """Probes must answer before any tenant exists."""
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200


def test_an_unauthenticated_request_gets_no_tenant_context(settings: Settings) -> None:
    """Phase 1 strengthening: the header alone is no longer sufficient.

    Before authentication existed, membership verification was the only gate.
    Now a request must also carry a verified principal — a header presented by
    an anonymous caller establishes nothing, whatever the verifier says.
    """
    app = _probe_app(
        settings,
        AllowAllMembershipVerifier(),
        StubPrincipalResolver(None),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenant-probe", headers={ORGANIZATION_HEADER: str(ORG_A)}
        )

    assert response.status_code == 200
    assert response.json()["organization_id"] is None


def test_the_organization_falls_back_to_the_one_in_the_token(
    settings: Settings,
) -> None:
    """A client that names no organization gets the session's own."""

    class TokenOnlyResolver:
        async def resolve(
            self, *, authorization: str | None, organization_header: uuid.UUID | None
        ) -> tuple[uuid.UUID | None, uuid.UUID | None]:
            return USER_A, ORG_A

    app = _probe_app(settings, AllowAllMembershipVerifier(), TokenOnlyResolver())

    with TestClient(app) as client:
        response = client.get("/api/v1/tenant-probe")

    assert response.json()["organization_id"] == str(ORG_A)
