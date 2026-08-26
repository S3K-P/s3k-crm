"""Teams, departments and the team dimension of record-level visibility.

Real PostgreSQL, real RLS. Grouped by the question each set answers:

**Does the CRUD work**, and is it tenant-scoped — including the join table,
which has no ``organization_id`` of its own and is isolated through its team.

**Is it authorized** — team administration is gated on the ``teams`` module,
and *User* deliberately holds none of it.

**Does the visibility rung actually work.** This is the point of B02 and the
part that could most easily be wrong in the dangerous direction. ``VIEW_TEAM``
is granted only to *Admin* by the migration — who already holds the wider
``VIEW_ALL`` — so a test that wants the middle rung grants it to *User*
explicitly and then checks both halves: a team-mate's records become visible,
and a non-team-mate's do not.

Those grants are made against the **system role templates**, which
``clean_database`` deliberately leaves alone because reference data belongs to
the migration. Anything a test grants there it must therefore revoke precisely
— see :func:`_revoke_view_team`.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


# --- Helpers ----------------------------------------------------------------


def _team(session: ApiSession, name: str = "Pipeline West", **extra: object) -> str:
    created = session.post("/teams", json={"name": name, **extra})
    assert created.status_code == 201, created.text
    team_id: str = created.json()["id"]
    return team_id


def _department(session: ApiSession, name: str = "Sales") -> str:
    created = session.post("/departments", json={"name": name})
    assert created.status_code == 201, created.text
    department_id: str = created.json()["id"]
    return department_id


async def _grant_view_team(
    factory: async_sessionmaker, organization_id: uuid.UUID, role_name: str, module: str
) -> None:
    """Give a system role ``<module>.VIEW_TEAM``.

    The migration grants it only to *Admin*, so a test that wants an ordinary
    user on the middle rung has to ask for it — which is exactly the shape of
    the decision an administrator makes on the Roles screen.
    """
    async with factory() as session:
        await session.execute(
            text(
                "INSERT INTO platform.role_permissions (role_id, permission_id) "
                "SELECT r.id, p.id FROM platform.roles r, platform.permissions p "
                "WHERE r.organization_id IS NULL AND r.name = :role "
                "  AND p.module = :module "
                "  AND p.action = CAST('VIEW_TEAM' AS platform.permission_action) "
                "ON CONFLICT (role_id, permission_id) DO NOTHING"
            ),
            {"role": role_name, "module": module},
        )
        await session.commit()


async def _revoke_view_team(factory: async_sessionmaker, role_name: str, module: str) -> None:
    """Undo exactly the grant :func:`_grant_view_team` made — and nothing else.

    Scoped to the one role and module on purpose. An unscoped
    ``DELETE ... WHERE action = 'VIEW_TEAM'`` also removes the grants the B02
    migration seeded for *Admin*, which ``clean_database`` does not restore
    because reference data is owned by the migration rather than by any test.
    That leaves the database permanently short of them and fails
    ``test_the_admin_role_grants_the_whole_catalogue`` on the next run — a test
    corrupting seeded state for every test after it, in a way that survives the
    session.
    """
    async with factory() as session:
        await session.execute(
            text(
                "DELETE FROM platform.role_permissions rp "
                "USING platform.permissions p, platform.roles r "
                "WHERE rp.permission_id = p.id AND rp.role_id = r.id "
                "  AND p.action = 'VIEW_TEAM' AND p.module = :module "
                "  AND r.organization_id IS NULL AND r.name = :role"
            ),
            {"role": role_name, "module": module},
        )
        await session.commit()


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
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    yield session


@pytest.fixture
def manager_session(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> Iterator[ApiSession]:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.manager.email, organization_id=alpha.organization_id)
    yield session


# =============================================================================
# Departments and teams: the happy path
# =============================================================================


def test_a_team_can_be_created_and_read_back(as_alpha_admin: ApiSession) -> None:
    team_id = _team(as_alpha_admin, "Enterprise")

    response = as_alpha_admin.get(f"/teams/{team_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Enterprise"
    assert body["department_id"] is None
    assert body["member_count"] == 0


def test_a_team_can_belong_to_a_department(as_alpha_admin: ApiSession) -> None:
    department_id = _department(as_alpha_admin)

    team_id = _team(as_alpha_admin, "Mid-Market", department_id=department_id)

    assert as_alpha_admin.get(f"/teams/{team_id}").json()["department_id"] == department_id


def test_teams_can_be_filtered_by_department(as_alpha_admin: ApiSession) -> None:
    department_id = _department(as_alpha_admin)
    _team(as_alpha_admin, "In Department", department_id=department_id)
    _team(as_alpha_admin, "Unassigned")

    listed = as_alpha_admin.get("/teams", params={"department_id": department_id}).json()

    assert [item["name"] for item in listed["data"]] == ["In Department"]


def test_a_duplicate_team_name_is_refused(as_alpha_admin: ApiSession) -> None:
    _team(as_alpha_admin, "Only One")

    assert as_alpha_admin.post("/teams", json={"name": "Only One"}).status_code == 409


def test_a_deleted_team_releases_its_name(as_alpha_admin: ApiSession) -> None:
    """The unique index is partial on ``deleted_at IS NULL``, so an archived
    team must not reserve its name forever."""
    team_id = _team(as_alpha_admin, "Recycled")
    assert as_alpha_admin.delete(f"/teams/{team_id}").status_code == 204

    assert as_alpha_admin.post("/teams", json={"name": "Recycled"}).status_code == 201


def test_a_team_can_be_renamed_and_moved(as_alpha_admin: ApiSession) -> None:
    department_id = _department(as_alpha_admin)
    team_id = _team(as_alpha_admin, "Before")

    response = as_alpha_admin.patch(
        f"/teams/{team_id}", json={"name": "After", "department_id": department_id}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "After"
    assert response.json()["department_id"] == department_id


def test_omitting_department_id_leaves_it_alone(as_alpha_admin: ApiSession) -> None:
    """Absent and explicit-null must not mean the same thing."""
    department_id = _department(as_alpha_admin)
    team_id = _team(as_alpha_admin, "Keeps Department", department_id=department_id)

    as_alpha_admin.patch(f"/teams/{team_id}", json={"name": "Renamed Only"})

    assert as_alpha_admin.get(f"/teams/{team_id}").json()["department_id"] == department_id


def test_an_explicit_null_department_detaches_the_team(as_alpha_admin: ApiSession) -> None:
    department_id = _department(as_alpha_admin)
    team_id = _team(as_alpha_admin, "Detaches", department_id=department_id)

    as_alpha_admin.patch(f"/teams/{team_id}", json={"department_id": None})

    assert as_alpha_admin.get(f"/teams/{team_id}").json()["department_id"] is None


def test_a_department_with_teams_cannot_be_deleted(as_alpha_admin: ApiSession) -> None:
    """Refused rather than cascading: deleting a team changes who sees what."""
    department_id = _department(as_alpha_admin)
    _team(as_alpha_admin, "Blocks Deletion", department_id=department_id)

    response = as_alpha_admin.delete(f"/departments/{department_id}")

    assert response.status_code == 409


def test_an_empty_department_can_be_deleted(as_alpha_admin: ApiSession) -> None:
    """The paired positive: the guard above must not refuse everything."""
    department_id = _department(as_alpha_admin, "Empty")

    assert as_alpha_admin.delete(f"/departments/{department_id}").status_code == 204


# =============================================================================
# Membership
# =============================================================================


def test_a_user_can_be_added_to_and_removed_from_a_team(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    team_id = _team(as_alpha_admin)

    added = as_alpha_admin.post(
        f"/teams/{team_id}/members", json={"user_id": str(alpha.member.user_id)}
    )
    assert added.status_code == 201
    assert as_alpha_admin.get(f"/teams/{team_id}").json()["member_count"] == 1

    removed = as_alpha_admin.delete(f"/teams/{team_id}/members/{alpha.member.user_id}")
    assert removed.status_code == 204
    assert as_alpha_admin.get(f"/teams/{team_id}").json()["member_count"] == 0


def test_adding_the_same_member_twice_is_idempotent(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """A double-submitted form must not surface as an error."""
    team_id = _team(as_alpha_admin)
    payload = {"user_id": str(alpha.member.user_id)}

    first = as_alpha_admin.post(f"/teams/{team_id}/members", json=payload)
    second = as_alpha_admin.post(f"/teams/{team_id}/members", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert as_alpha_admin.get(f"/teams/{team_id}").json()["member_count"] == 1


def test_removing_somebody_who_is_not_on_the_team_is_not_found(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    team_id = _team(as_alpha_admin)

    response = as_alpha_admin.delete(f"/teams/{team_id}/members/{alpha.member.user_id}")

    assert response.status_code == 404


def test_deleting_a_team_removes_its_membership(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Memberships go for real, so nobody keeps visibility through a team that
    no longer exists."""
    team_id = _team(as_alpha_admin)
    as_alpha_admin.post(
        f"/teams/{team_id}/members", json={"user_id": str(alpha.member.user_id)}
    )

    assert as_alpha_admin.delete(f"/teams/{team_id}").status_code == 204
    assert as_alpha_admin.get(f"/teams/{team_id}").status_code == 404


# =============================================================================
# Authorization and tenant isolation
# =============================================================================


def test_an_unauthenticated_caller_is_refused(client: TestClient) -> None:
    assert client.get("/api/v1/teams").status_code in (401, 403)


def test_a_plain_user_cannot_read_teams(member_session: ApiSession) -> None:
    """*User* holds nothing on the ``teams`` module."""
    assert member_session.get("/teams").status_code == 403


def test_a_plain_user_cannot_create_a_team(member_session: ApiSession) -> None:
    assert member_session.post("/teams", json={"name": "Nope"}).status_code == 403


def test_a_manager_may_read_but_not_create(manager_session: ApiSession) -> None:
    """Manager reads the org chart; restructuring it is administrative."""
    assert manager_session.get("/teams").status_code == 200
    assert manager_session.post("/teams", json={"name": "Nope"}).status_code == 403


def test_another_tenants_team_is_not_found(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    beta_team = _team(as_beta_admin, "Beta Only")

    assert as_alpha_admin.get(f"/teams/{beta_team}").status_code == 404
    assert as_alpha_admin.delete(f"/teams/{beta_team}").status_code == 404


def test_another_tenants_teams_are_not_listed(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    _team(as_beta_admin, "Beta Secret")
    _team(as_alpha_admin, "Alpha Own")

    names = [item["name"] for item in as_alpha_admin.get("/teams").json()["data"]]

    assert names == ["Alpha Own"]


def test_a_team_cannot_be_attached_to_another_tenants_department(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """The foreign key would hold — both rows live in one database — so the
    organization-scoped read is what makes this impossible."""
    beta_department = _department(as_beta_admin, "Beta Department")

    response = as_alpha_admin.post(
        "/teams", json={"name": "Cross Tenant", "department_id": beta_department}
    )

    assert response.status_code == 404


def test_membership_of_another_tenants_team_is_not_reachable(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession, alpha: Tenant
) -> None:
    """``team_memberships`` has no organization_id; it is isolated through the
    team it points at."""
    beta_team = _team(as_beta_admin, "Beta Staffed")

    added = as_alpha_admin.post(
        f"/teams/{beta_team}/members", json={"user_id": str(alpha.member.user_id)}
    )
    listed = as_alpha_admin.get(f"/teams/{beta_team}/members")

    assert added.status_code == 404
    assert listed.status_code == 404


# =============================================================================
# The visibility rung — the reason B02 blocked GATE 2
# =============================================================================


async def test_view_team_reveals_a_team_mates_records(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker,
) -> None:
    """The whole point of B02.

    A lead owned by the admin is invisible to a plain member. Put both on one
    team, grant ``leads.VIEW_TEAM``, and it becomes visible — without the
    member gaining ``VIEW_ALL``.
    """
    lead_id = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Team",
            "last_name": "Visible",
            "owner_id": str(alpha.admin.user_id),
        },
    ).json()["id"]

    # Before: not on a team, no VIEW_TEAM -> invisible.
    assert member_session.get(f"/crm/leads/{lead_id}").status_code == 404

    team_id = _team(as_alpha_admin, "Shared Pipeline")
    for user_id in (alpha.admin.user_id, alpha.member.user_id):
        as_alpha_admin.post(f"/teams/{team_id}/members", json={"user_id": str(user_id)})

    await _grant_view_team(session_factory, alpha.organization_id, "User", "leads")
    try:
        assert member_session.get(f"/crm/leads/{lead_id}").status_code == 200
    finally:
        await _revoke_view_team(session_factory, "User", "leads")


async def test_view_team_does_not_reveal_a_non_team_mates_records(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker,
) -> None:
    """The other half. Without this, the test above would pass on a bug that
    turned ``VIEW_TEAM`` into ``VIEW_ALL``."""
    lead_id = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Not",
            "last_name": "Shared",
            "owner_id": str(alpha.admin.user_id),
        },
    ).json()["id"]

    # The member is on a team; the admin who owns the lead is not.
    team_id = _team(as_alpha_admin, "Member Only")
    as_alpha_admin.post(
        f"/teams/{team_id}/members", json={"user_id": str(alpha.member.user_id)}
    )

    await _grant_view_team(session_factory, alpha.organization_id, "User", "leads")
    try:
        assert member_session.get(f"/crm/leads/{lead_id}").status_code == 404
    finally:
        await _revoke_view_team(session_factory, "User", "leads")


async def test_view_team_on_no_team_degrades_to_owner_only(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker,
) -> None:
    """An empty peer set must never read as "no restriction"."""
    lead_id = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Admin",
            "last_name": "Owned",
            "owner_id": str(alpha.admin.user_id),
        },
    ).json()["id"]

    await _grant_view_team(session_factory, alpha.organization_id, "User", "leads")
    try:
        # Holds VIEW_TEAM, belongs to no team.
        assert member_session.get(f"/crm/leads/{lead_id}").status_code == 404
        # ...but still sees their own work.
        own = member_session.post(
            "/crm/leads", json={"first_name": "My", "last_name": "Lead"}
        ).json()["id"]
        assert member_session.get(f"/crm/leads/{own}").status_code == 200
    finally:
        await _revoke_view_team(session_factory, "User", "leads")


async def test_removing_somebody_from_a_team_withdraws_the_visibility(
    as_alpha_admin: ApiSession,
    member_session: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker,
) -> None:
    """Visibility is resolved from live rows, so it narrows the moment
    membership does — no cache to invalidate."""
    lead_id = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Was",
            "last_name": "Shared",
            "owner_id": str(alpha.admin.user_id),
        },
    ).json()["id"]
    team_id = _team(as_alpha_admin, "Temporary")
    for user_id in (alpha.admin.user_id, alpha.member.user_id):
        as_alpha_admin.post(f"/teams/{team_id}/members", json={"user_id": str(user_id)})

    await _grant_view_team(session_factory, alpha.organization_id, "User", "leads")
    try:
        assert member_session.get(f"/crm/leads/{lead_id}").status_code == 200

        as_alpha_admin.delete(f"/teams/{team_id}/members/{alpha.member.user_id}")

        assert member_session.get(f"/crm/leads/{lead_id}").status_code == 404
    finally:
        await _revoke_view_team(session_factory, "User", "leads")


async def test_view_all_still_wins_over_view_team(
    as_alpha_admin: ApiSession, manager_session: ApiSession, alpha: Tenant
) -> None:
    """A Manager holds ``VIEW_ALL`` and no team. Adding the team rung must not
    have narrowed them to their own records."""
    lead_id = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Manager",
            "last_name": "Sees",
            "owner_id": str(alpha.admin.user_id),
        },
    ).json()["id"]

    assert manager_session.get(f"/crm/leads/{lead_id}").status_code == 200


# =============================================================================
# Audit
# =============================================================================


def test_team_changes_are_audited(as_alpha_admin: ApiSession, alpha: Tenant) -> None:
    team_id = _team(as_alpha_admin, "Audited")
    as_alpha_admin.post(
        f"/teams/{team_id}/members", json={"user_id": str(alpha.member.user_id)}
    )

    actions = [
        entry["action"]
        for entry in as_alpha_admin.get(
            "/audit-logs", params={"module": "teams"}
        ).json()["data"]
    ]

    assert "TEAM_CREATED" in actions
    assert "TEAM_MEMBER_ADDED" in actions


def test_another_tenant_cannot_see_team_audit_records(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    _team(as_beta_admin, "Beta Audited Team")

    trail = str(as_alpha_admin.get("/audit-logs", params={"module": "teams"}).json())

    assert "Beta Audited Team" not in trail
