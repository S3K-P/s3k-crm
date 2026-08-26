"""Legitimate multi-organization membership and organization switching.

``test_tenant_isolation_api.py`` proves a user cannot reach an organization
they do **not** belong to. This suite proves the complementary half, which is
what actually exercises the scoping machinery: a user who legitimately belongs
to *two* organizations must see strictly different data in each, decided by the
verified request scope and nothing else.

Without a genuinely multi-organization user, every "scoping works" assertion is
vacuous — one user with one membership would pass even if the organization
filter were ignored entirely.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from tests.integration.conftest import ApiSession, DualMember, Tenant

pytestmark = pytest.mark.integration


def _create_account(session: ApiSession, name: str, organization_id: uuid.UUID) -> uuid.UUID:
    response = session.post(
        "/crm/accounts", json={"name": name}, organization_id=organization_id
    )
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


def _account_names(session: ApiSession, organization_id: uuid.UUID) -> list[str]:
    response = session.get("/crm/accounts", organization_id=organization_id)
    assert response.status_code == 200, response.text
    return sorted(row["name"] for row in response.json()["data"])


# --- Membership resolution --------------------------------------------------


def test_a_dual_member_sees_both_organizations_in_their_profile(
    api: ApiSession, dual_member: DualMember
) -> None:
    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)

    body = api.get("/auth/me").json()
    organization_ids = {m["organization_id"] for m in body["memberships"]}

    assert organization_ids == {
        str(dual_member.alpha_organization_id),
        str(dual_member.beta_organization_id),
    }


def test_a_dual_member_may_log_into_either_organization(
    api: ApiSession, dual_member: DualMember
) -> None:
    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)
    assert api.organization_id == dual_member.alpha_organization_id

    api.login(dual_member.email, organization_id=dual_member.beta_organization_id)
    assert api.organization_id == dual_member.beta_organization_id


# --- Scope actually changes -------------------------------------------------


def test_the_same_credentials_return_disjoint_data_per_organization(
    api: ApiSession, dual_member: DualMember
) -> None:
    """The headline property: one user, one token, two disjoint data sets."""
    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)

    _create_account(api, "Alpha Only Ltd", dual_member.alpha_organization_id)
    _create_account(api, "Beta Only Ltd", dual_member.beta_organization_id)

    in_alpha = _account_names(api, dual_member.alpha_organization_id)
    in_beta = _account_names(api, dual_member.beta_organization_id)

    assert in_alpha == ["Alpha Only Ltd"]
    assert in_beta == ["Beta Only Ltd"]
    assert set(in_alpha).isdisjoint(in_beta)


def test_switching_organizations_changes_scope_without_re_authenticating(
    api: ApiSession, dual_member: DualMember
) -> None:
    """Only the organization header changes between these two reads."""
    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)
    _create_account(api, "Scoped To Alpha", dual_member.alpha_organization_id)

    # Same access token, different verified scope.
    assert _account_names(api, dual_member.beta_organization_id) == []
    assert _account_names(api, dual_member.alpha_organization_id) == ["Scoped To Alpha"]


def test_a_record_created_under_one_scope_is_invisible_under_the_other(
    api: ApiSession, dual_member: DualMember
) -> None:
    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)
    account_id = _create_account(api, "Alpha Private", dual_member.alpha_organization_id)

    seen_from_beta = api.get(
        f"/crm/accounts/{account_id}", organization_id=dual_member.beta_organization_id
    )

    assert seen_from_beta.status_code == 404


def test_a_dual_member_still_cannot_reach_an_organization_they_do_not_belong_to(
    api: ApiSession, dual_member: DualMember
) -> None:
    """Holding two memberships is not a licence to assert a third."""
    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)

    response = api.get("/crm/accounts", organization_id=uuid.uuid4())

    assert response.status_code == 403


def test_losing_one_membership_does_not_affect_the_other(
    api: ApiSession, dual_member: DualMember, integration_settings: Settings
) -> None:
    """Suspension is per-membership, not per-user."""
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)
    in_beta = api.get("/crm/accounts", organization_id=dual_member.beta_organization_id)
    assert in_beta.status_code == 200

    async def suspend_beta() -> None:
        engine = create_async_engine(integration_settings.database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE platform.organization_memberships SET status = 'SUSPENDED' "
                        "WHERE organization_id = :org AND user_id = :user"
                    ),
                    {"org": dual_member.beta_organization_id, "user": dual_member.user_id},
                )
        finally:
            await engine.dispose()

    asyncio.run(suspend_beta())

    suspended = api.get("/crm/accounts", organization_id=dual_member.beta_organization_id)
    still_active = api.get("/crm/accounts", organization_id=dual_member.alpha_organization_id)
    assert suspended.status_code == 403
    assert still_active.status_code == 200


# --- Scope is server-derived, never client-asserted -------------------------


def test_a_record_is_created_under_the_verified_scope_not_the_body(
    api: ApiSession, dual_member: DualMember
) -> None:
    """A dual member could plausibly be trusted with either id — they are not.

    The header decides the scope; an `organization_id` in the body is ignored
    even when the caller genuinely belongs to the organization it names.
    """
    api.login(dual_member.email, organization_id=dual_member.alpha_organization_id)

    response = api.post(
        "/crm/accounts",
        json={
            "name": "Body Says Beta",
            "organization_id": str(dual_member.beta_organization_id),
        },
        organization_id=dual_member.alpha_organization_id,
    )

    assert response.status_code == 201
    assert response.json()["organization_id"] == str(dual_member.alpha_organization_id)
    # And it is genuinely absent from the organization the body named.
    assert "Body Says Beta" not in _account_names(api, dual_member.beta_organization_id)


def test_a_single_org_member_is_unaffected_by_the_dual_member_fixture(
    api: ApiSession, alpha: Tenant, dual_member: DualMember
) -> None:
    """Guards the fixture: alpha's own admin must not gain beta access."""
    api.login(alpha.admin.email, organization_id=alpha.organization_id)

    response = api.get("/crm/accounts", organization_id=dual_member.beta_organization_id)

    assert response.status_code == 403
