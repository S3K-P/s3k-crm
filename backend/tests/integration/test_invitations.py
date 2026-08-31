"""Organization invitations: the second way into a tenant.

The token is 256 bits and stored only as a digest, so guessing or reading one
out of the database is not the threat. What the tests below concentrate on is
everything else that could go wrong with a link somebody can forward:

* holding the link is **not** sufficient — the signed-in address must match;
* a spent, revoked or expired link is refused, and all three answer alike;
* an administrator cannot see or revoke another tenant's invitations;
* accepting adds a membership to the existing account rather than founding a
  new organization, which is the Phase 11 hazard.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration

INVITEE_PASSWORD = "Str0ngPassphrase!"
INVITEE_EMAIL = "newcomer@invited.example"


def _role_id(session: ApiSession, name: str) -> str:
    roles = session.get("/roles").json()
    rows = roles["data"] if isinstance(roles, dict) else roles
    return str(next(row["id"] for row in rows if row["name"] == name))


def _invite(session: ApiSession, email: str, *, role_id: str | None = None) -> Response:
    payload: dict[str, object] = {"email": email}
    if role_id is not None:
        payload["role_id"] = role_id
    return session.post("/organizations/current/invitations", json=payload)


def _signup(client: TestClient, settings: Settings, email: str) -> str:
    response = client.post(
        f"{settings.api_prefix}/auth/signup",
        json={
            "email": email,
            "password": INVITEE_PASSWORD,
            "first_name": "New",
            "last_name": "Comer",
        },
    )
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- Issuing ----------------------------------------------------------------


def test_an_administrator_can_invite_someone(as_alpha_admin: ApiSession) -> None:
    response = _invite(as_alpha_admin, INVITEE_EMAIL)

    assert response.status_code == 201
    body = response.json()
    assert body["invitation"]["email"] == INVITEE_EMAIL
    assert body["invitation"]["status"] == "PENDING"
    # Returned exactly once, and never stored in the clear.
    assert len(body["token"]) > 20


def test_the_token_is_never_returned_again(as_alpha_admin: ApiSession) -> None:
    """A listing that echoed tokens would turn read access into join access."""
    _invite(as_alpha_admin, INVITEE_EMAIL)

    listed = as_alpha_admin.get("/organizations/current/invitations").json()

    assert len(listed) == 1
    assert "token" not in listed[0]


def test_an_ordinary_member_cannot_invite(as_alpha_member: ApiSession) -> None:
    response = _invite(as_alpha_member, INVITEE_EMAIL)

    assert response.status_code == 403


def test_inviting_the_same_address_twice_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    """Two live links for one person is a revocation hazard, not a convenience."""
    assert _invite(as_alpha_admin, INVITEE_EMAIL).status_code == 201

    second = _invite(as_alpha_admin, INVITEE_EMAIL)

    assert second.status_code == 409


def test_inviting_with_a_role_this_organization_cannot_grant_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    """The role is resolved when the invitation is *issued*, not when redeemed.

    Storing an unchecked ``role_id`` would defer the failure to the moment
    somebody accepts — when the person hitting the error is the invitee, who
    can do nothing about it, and the administrator who caused it is not
    watching.

    Only the seeded system roles exist today (there is no endpoint that creates
    a tenant-owned one), so an id that resolves to nothing is the reachable
    form of "a role this organization cannot grant".
    """
    response = _invite(as_alpha_admin, INVITEE_EMAIL, role_id=str(uuid.uuid4()))

    assert response.status_code == 404

    # And nothing was stored: a refused invitation must not leave a PENDING row
    # holding the address hostage against the partial unique index.
    assert as_alpha_admin.get("/organizations/current/invitations").json() == []


# --- Redeeming --------------------------------------------------------------


def test_an_invited_user_joins_the_inviting_organization(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    """The whole journey, and the Phase 11 hazard it must avoid.

    The invitee signs up — which creates an identity and **no** organization —
    and then redeems. They end up in alpha with the role they were offered, and
    with exactly one membership: no accidental organization of their own.
    """
    token = _invite(as_alpha_admin, INVITEE_EMAIL, role_id=_role_id(as_alpha_admin, "User")).json()[
        "token"
    ]
    access = _signup(client, integration_settings, INVITEE_EMAIL)

    accepted = client.post(
        f"{integration_settings.api_prefix}/invitations/accept",
        headers=_auth(access),
        json={"token": token},
    )
    assert accepted.status_code == 200, accepted.text

    me = client.get(
        f"{integration_settings.api_prefix}/auth/me", headers=_auth(access)
    ).json()
    assert len(me["memberships"]) == 1
    assert me["memberships"][0]["organization_id"] == str(alpha.organization_id)
    assert me["memberships"][0]["roles"] == ["User"]


def test_an_invited_user_can_use_the_product_immediately(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    """Joining is enough; there is no second sign-in and no waiting."""
    token = _invite(as_alpha_admin, INVITEE_EMAIL, role_id=_role_id(as_alpha_admin, "User")).json()[
        "token"
    ]
    access = _signup(client, integration_settings, INVITEE_EMAIL)
    client.post(
        f"{integration_settings.api_prefix}/invitations/accept",
        headers=_auth(access),
        json={"token": token},
    )

    listed = client.get(
        f"{integration_settings.api_prefix}/crm/leads",
        headers={**_auth(access), "X-Organization-Id": str(alpha.organization_id)},
    )

    assert listed.status_code == 200


def test_a_forwarded_link_is_useless_to_anybody_else(
    as_alpha_admin: ApiSession, client: TestClient, integration_settings: Settings
) -> None:
    """The check that makes a leaked invitation harmless.

    Without it, a forwarded email, a shared inbox or a screenshot in a chat
    would each be a working grant of access to the tenant.
    """
    token = _invite(as_alpha_admin, INVITEE_EMAIL).json()["token"]
    interloper = _signup(client, integration_settings, "someone.else@invited.example")

    response = client.post(
        f"{integration_settings.api_prefix}/invitations/accept",
        headers=_auth(interloper),
        json={"token": token},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "invitation_address_mismatch"


def test_accepting_requires_authentication(
    as_alpha_admin: ApiSession, client: TestClient, integration_settings: Settings
) -> None:
    token = _invite(as_alpha_admin, INVITEE_EMAIL).json()["token"]

    response = client.post(
        f"{integration_settings.api_prefix}/invitations/accept", json={"token": token}
    )

    assert response.status_code == 401


def test_a_token_cannot_be_redeemed_twice(
    as_alpha_admin: ApiSession, client: TestClient, integration_settings: Settings
) -> None:
    token = _invite(as_alpha_admin, INVITEE_EMAIL).json()["token"]
    access = _signup(client, integration_settings, INVITEE_EMAIL)
    first = client.post(
        f"{integration_settings.api_prefix}/invitations/accept",
        headers=_auth(access),
        json={"token": token},
    )
    assert first.status_code == 200

    replay = client.post(
        f"{integration_settings.api_prefix}/invitations/accept",
        headers=_auth(access),
        json={"token": token},
    )

    assert replay.status_code == 404
    assert replay.json()["error"]["code"] == "invitation_not_redeemable"


def test_a_revoked_invitation_cannot_be_redeemed(
    as_alpha_admin: ApiSession, client: TestClient, integration_settings: Settings
) -> None:
    created = _invite(as_alpha_admin, INVITEE_EMAIL).json()
    as_alpha_admin.post(
        f"/organizations/current/invitations/{created['invitation']['id']}/revoke"
    )
    access = _signup(client, integration_settings, INVITEE_EMAIL)

    response = client.post(
        f"{integration_settings.api_prefix}/invitations/accept",
        headers=_auth(access),
        json={"token": created["token"]},
    )

    assert response.status_code == 404


async def test_an_expired_invitation_cannot_be_redeemed(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Expiry is read from the clock, not from a status somebody sweeps."""
    created = _invite(as_alpha_admin, INVITEE_EMAIL).json()
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE platform.organization_invitations "
                "SET expires_at = :past WHERE id = :id"
            ),
            {
                "past": dt.datetime.now(dt.UTC) - dt.timedelta(days=1),
                "id": uuid.UUID(created["invitation"]["id"]),
            },
        )
    access = _signup(client, integration_settings, INVITEE_EMAIL)

    response = client.post(
        f"{integration_settings.api_prefix}/invitations/accept",
        headers=_auth(access),
        json={"token": created["token"]},
    )

    assert response.status_code == 404


def test_an_unknown_token_is_refused_exactly_like_a_spent_one(
    client: TestClient, integration_settings: Settings
) -> None:
    """No oracle: a random string must not reveal whether it was ever real."""
    access = _signup(client, integration_settings, INVITEE_EMAIL)

    response = client.post(
        f"{integration_settings.api_prefix}/invitations/accept",
        headers=_auth(access),
        json={"token": "not-a-real-invitation-token"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "invitation_not_redeemable"


# --- The preview screen -----------------------------------------------------


def test_the_preview_names_the_organization_without_authentication(
    as_alpha_admin: ApiSession, client: TestClient, integration_settings: Settings
) -> None:
    """So the accept page can say which account to sign in as.

    It discloses only what the holder of the link was already told, and it
    redeems nothing.
    """
    token = _invite(as_alpha_admin, INVITEE_EMAIL).json()["token"]

    response = client.get(
        f"{integration_settings.api_prefix}/invitations/preview", params={"token": token}
    )

    assert response.status_code == 200
    assert response.json()["email"] == INVITEE_EMAIL
    assert "organization_name" in response.json()


def test_the_preview_refuses_an_unknown_token(
    client: TestClient, integration_settings: Settings
) -> None:
    response = client.get(
        f"{integration_settings.api_prefix}/invitations/preview",
        params={"token": "nonsense"},
    )

    assert response.status_code == 404


# --- Tenant isolation -------------------------------------------------------


def test_an_administrator_sees_only_their_own_organizations_invitations(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    """The table carries no RLS policy, so the repository's filter *is* the isolation."""
    _invite(as_alpha_admin, INVITEE_EMAIL)

    beta_admin = ApiSession(client, integration_settings.api_prefix)
    beta_admin.login(beta.admin.email)

    assert beta_admin.get("/organizations/current/invitations").json() == []


def test_an_administrator_cannot_revoke_another_organizations_invitation(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    """Guessing an id from another tenant gets the same 404 as a missing one."""
    created = _invite(as_alpha_admin, INVITEE_EMAIL).json()

    beta_admin = ApiSession(client, integration_settings.api_prefix)
    beta_admin.login(beta.admin.email)
    response = beta_admin.post(
        f"/organizations/current/invitations/{created['invitation']['id']}/revoke"
    )

    assert response.status_code == 404
