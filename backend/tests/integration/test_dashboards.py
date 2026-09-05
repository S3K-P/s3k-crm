"""Configurable dashboards.

Real PostgreSQL, real RLS, every assertion through HTTP.

**The question this file exists to answer is whether a shared dashboard can
hand somebody numbers they are not entitled to.** It cannot, and the mechanism
is that a tile is rendered by running its saved report *as the viewer* — so
the same board shows a manager and a rep different figures, and a tile reading
a module the viewer lacks comes back marked unavailable rather than either
failing the page or, far worse, showing the owner's numbers.

The rest covers the layout's own lifecycle: tiles belong to their dashboard,
ordering is applied whole, deleting a report still on a board is refused, and
one person's default is not another's.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.products.crm.dashboard.library import MAX_COMPONENTS_PER_DASHBOARD
from tests.integration.conftest import (
    ApiSession,
    Tenant,
    grant_custom_role,
    membership_id_for,
)

pytestmark = pytest.mark.integration

BOARDS = "/crm/dashboard/boards"
SAVED = "/crm/reports/saved"


# --- Helpers ----------------------------------------------------------------


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """Alpha's plain ``User``: no ``VIEW_ALL``, so owner-scoped reads narrow."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def manager(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    """Alpha's ``Manager``: holds ``VIEW_ALL`` across the CRM modules."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.manager.email, organization_id=alpha.organization_id)
    return session


def _board(session: ApiSession, name: str, **extra: object) -> dict[str, object]:
    created = session.post(BOARDS, json={"name": name, **extra})
    assert created.status_code == 201, created.text
    body: dict[str, object] = created.json()
    return body


def _save(
    session: ApiSession, *, name: str, key: str = "pipeline-by-stage", **extra: object
) -> dict[str, object]:
    created = session.post(SAVED, json={"name": name, "base_report_key": key, **extra})
    assert created.status_code == 201, created.text
    body: dict[str, object] = created.json()
    return body


def _tile(
    session: ApiSession, board_id: str, saved_report_id: str, **extra: object
) -> dict[str, object]:
    created = session.post(
        f"{BOARDS}/{board_id}/components",
        json={"saved_report_id": saved_report_id, **extra},
    )
    assert created.status_code == 201, created.text
    body: dict[str, object] = created.json()
    return body


def _account(session: ApiSession, name: str) -> str:
    created = session.post("/crm/accounts", json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _stage_id(session: ApiSession, name: str = "Qualification") -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


def _deal(session: ApiSession, *, name: str, account_id: str, value: str) -> str:
    created = session.post(
        "/crm/opportunities",
        json={
            "name": name,
            "account_id": account_id,
            "stage_id": _stage_id(session),
            "deal_value": value,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def _only_permissions(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    organization_id: uuid.UUID,
    membership_id: uuid.UUID,
    codes: list[str],
    name: str,
) -> None:
    """Give a membership exactly ``codes`` and nothing else."""
    async with session_factory() as session:
        await session.execute(
            sql("DELETE FROM platform.membership_roles WHERE membership_id = :membership"),
            {"membership": membership_id},
        )
        await session.commit()

    await grant_custom_role(
        session_factory,
        organization_id=organization_id,
        membership_id=membership_id,
        codes=codes,
        name=name,
    )


# --- The board itself -------------------------------------------------------


def test_a_dashboard_round_trips_with_its_tiles(as_alpha_admin: ApiSession) -> None:
    board = _board(as_alpha_admin, "Sales overview", description="What we watch.")
    report = _save(as_alpha_admin, name="Pipeline")
    _tile(as_alpha_admin, str(board["id"]), str(report["id"]), display="TABLE", width=12)

    fetched = as_alpha_admin.get(f"{BOARDS}/{board['id']}")

    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["name"] == "Sales overview"
    assert len(body["components"]) == 1
    assert body["components"][0]["display"] == "TABLE"
    assert body["components"][0]["width"] == 12
    assert body["components"][0]["saved_report_id"] == report["id"]


def test_two_dashboards_cannot_share_a_name(as_alpha_admin: ApiSession) -> None:
    _board(as_alpha_admin, "Overview")

    duplicate = as_alpha_admin.post(BOARDS, json={"name": "Overview"})

    assert duplicate.status_code == 409, duplicate.text


def test_a_dashboard_defaults_to_private(as_alpha_admin: ApiSession) -> None:
    board = _board(as_alpha_admin, "Draft board")

    assert board["visibility"] == "PRIVATE"


def test_a_colleagues_private_dashboard_is_invisible(
    manager: ApiSession, rep: ApiSession
) -> None:
    private = _board(manager, "Manager's board")

    listed = rep.get(BOARDS)
    assert listed.json()["data"] == []

    fetched = rep.get(f"{BOARDS}/{private['id']}")
    assert fetched.status_code == 404, fetched.text


def test_only_the_owner_may_reshape_a_shared_dashboard(
    manager: ApiSession, rep: ApiSession
) -> None:
    """Sharing invites colleagues to read it, not to rearrange it for everyone."""
    shared = _board(manager, "Team board", visibility="SHARED")

    renamed = rep.patch(f"{BOARDS}/{shared['id']}", json={"name": "Hijacked"})
    deleted = rep.delete(f"{BOARDS}/{shared['id']}")

    assert renamed.status_code == 403, renamed.text
    assert deleted.status_code == 403, deleted.text


def test_one_default_dashboard_per_person(as_alpha_admin: ApiSession) -> None:
    """Making a second board the default demotes the first."""
    first = _board(as_alpha_admin, "First", is_default=True)
    second = _board(as_alpha_admin, "Second", is_default=True)

    listed = {board["id"]: board for board in as_alpha_admin.get(BOARDS).json()["data"]}

    assert listed[first["id"]]["is_default"] is False
    assert listed[second["id"]]["is_default"] is True


def test_another_persons_default_is_untouched(
    manager: ApiSession, rep: ApiSession
) -> None:
    """The default is per owner, so one member's choice is not an org-wide act."""
    managers = _board(manager, "Manager board", is_default=True, visibility="SHARED")
    _board(rep, "Rep board", is_default=True)

    still_default = manager.get(f"{BOARDS}/{managers['id']}")

    assert still_default.json()["is_default"] is True


# --- Tiles ------------------------------------------------------------------


def test_tiles_append_in_order_and_reorder_as_a_whole(as_alpha_admin: ApiSession) -> None:
    board = _board(as_alpha_admin, "Ordered")
    first = _tile(
        as_alpha_admin,
        str(board["id"]),
        str(_save(as_alpha_admin, name="One")["id"]),
    )
    second = _tile(
        as_alpha_admin,
        str(board["id"]),
        str(_save(as_alpha_admin, name="Two", key="lead-funnel")["id"]),
    )

    assert first["sort_order"] == 0
    assert second["sort_order"] == 1

    reordered = as_alpha_admin.put(
        f"{BOARDS}/{board['id']}/layout",
        json={"order": [second["id"], first["id"]]},
    )

    assert reordered.status_code == 200, reordered.text
    assert [tile["id"] for tile in reordered.json()] == [second["id"], first["id"]]
    assert [tile["sort_order"] for tile in reordered.json()] == [0, 1]


def test_reordering_with_a_foreign_tile_id_is_rejected(
    as_alpha_admin: ApiSession,
) -> None:
    """A client sending an id from another board has a bug worth surfacing."""
    board = _board(as_alpha_admin, "Ordered")
    tile = _tile(
        as_alpha_admin, str(board["id"]), str(_save(as_alpha_admin, name="One")["id"])
    )

    refused = as_alpha_admin.put(
        f"{BOARDS}/{board['id']}/layout",
        json={"order": [tile["id"], str(uuid.uuid4())]},
    )

    assert refused.status_code == 404, refused.text


def test_a_tile_from_another_dashboard_cannot_be_edited_through_this_one(
    as_alpha_admin: ApiSession,
) -> None:
    """Scoped to the parent as well as the organization."""
    first = _board(as_alpha_admin, "First")
    second = _board(as_alpha_admin, "Second")
    tile = _tile(
        as_alpha_admin, str(first["id"]), str(_save(as_alpha_admin, name="One")["id"])
    )

    refused = as_alpha_admin.patch(
        f"{BOARDS}/{second['id']}/components/{tile['id']}", json={"width": 12}
    )

    assert refused.status_code == 404, refused.text


def test_an_explicit_null_clears_a_tile_title_but_not_its_width(
    as_alpha_admin: ApiSession,
) -> None:
    """``title`` is nullable and clearing it restores the report's own name.

    ``width`` is ``NOT NULL``, so the same null is ignored rather than sent to
    a column that would refuse it.
    """
    board = _board(as_alpha_admin, "Nulls")
    report = _save(as_alpha_admin, name="Pipeline")
    tile = _tile(
        as_alpha_admin, str(board["id"]), str(report["id"]), title="Custom", width=12
    )

    patched = as_alpha_admin.patch(
        f"{BOARDS}/{board['id']}/components/{tile['id']}",
        json={"title": None, "width": None, "display": None},
    )

    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] is None
    assert patched.json()["width"] == 12
    assert patched.json()["display"] == "CHART"

    rendered = as_alpha_admin.get(f"{BOARDS}/{board['id']}/data")
    assert rendered.json()["components"][0]["title"] == "Pipeline"


def test_a_colleagues_private_report_cannot_be_mounted(
    manager: ApiSession, rep: ApiSession
) -> None:
    """Otherwise a member could publish somebody's private report by tiling it."""
    private = _save(manager, name="Manager's draft")
    board = _board(rep, "Rep board")

    refused = rep.post(
        f"{BOARDS}/{board['id']}/components", json={"saved_report_id": str(private["id"])}
    )

    assert refused.status_code == 404, refused.text


def test_a_dashboard_will_not_grow_without_bound(as_alpha_admin: ApiSession) -> None:
    board = _board(as_alpha_admin, "Crowded")
    report = _save(as_alpha_admin, name="Pipeline")
    for _ in range(MAX_COMPONENTS_PER_DASHBOARD):
        _tile(as_alpha_admin, str(board["id"]), str(report["id"]))

    refused = as_alpha_admin.post(
        f"{BOARDS}/{board['id']}/components", json={"saved_report_id": str(report["id"])}
    )

    assert refused.status_code == 409, refused.text


def test_a_report_on_a_dashboard_cannot_be_deleted(as_alpha_admin: ApiSession) -> None:
    """Refused rather than cascaded, so a tile never silently blanks."""
    board = _board(as_alpha_admin, "Sales")
    report = _save(as_alpha_admin, name="Pipeline")
    tile = _tile(as_alpha_admin, str(board["id"]), str(report["id"]))

    refused = as_alpha_admin.delete(f"{SAVED}/{report['id']}")
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "saved_report_in_use"

    removed = as_alpha_admin.delete(f"{BOARDS}/{board['id']}/components/{tile['id']}")
    assert removed.status_code == 204, removed.text

    now_deletable = as_alpha_admin.delete(f"{SAVED}/{report['id']}")
    assert now_deletable.status_code == 204, now_deletable.text


def test_deleting_a_dashboard_frees_its_reports(as_alpha_admin: ApiSession) -> None:
    """The tiles go with the board; the reports in the library do not."""
    board = _board(as_alpha_admin, "Temporary")
    report = _save(as_alpha_admin, name="Pipeline")
    _tile(as_alpha_admin, str(board["id"]), str(report["id"]))

    deleted = as_alpha_admin.delete(f"{BOARDS}/{board['id']}")
    assert deleted.status_code == 204, deleted.text

    still_there = as_alpha_admin.get(f"{SAVED}/{report['id']}")
    assert still_there.status_code == 200, still_there.text

    now_deletable = as_alpha_admin.delete(f"{SAVED}/{report['id']}")
    assert now_deletable.status_code == 204, now_deletable.text


# --- Rendering: the gate ----------------------------------------------------


def test_a_shared_dashboard_shows_each_viewer_their_own_numbers(
    manager: ApiSession, rep: ApiSession
) -> None:
    """The gate for this feature.

    The manager owns two deals, saves a shared pipeline report, and puts it on
    a shared board. Both people open *the same board*. The manager sees their
    two deals; the rep, who owns none, sees zero. A dashboard is a lens, not a
    copy of somebody else's answer.
    """
    account_id = _account(manager, "Northwind Traders")
    _deal(manager, name="Deal one", account_id=account_id, value="40000.00")
    _deal(manager, name="Deal two", account_id=account_id, value="60000.00")

    report = _save(manager, name="Team pipeline", visibility="SHARED")
    board = _board(manager, "Team board", visibility="SHARED")
    _tile(manager, str(board["id"]), str(report["id"]))

    managers_view = manager.get(f"{BOARDS}/{board['id']}/data")
    reps_view = rep.get(f"{BOARDS}/{board['id']}/data")

    assert managers_view.status_code == 200, managers_view.text
    assert reps_view.status_code == 200, reps_view.text

    managers_tile = managers_view.json()["components"][0]
    reps_tile = reps_view.json()["components"][0]

    assert managers_tile["result"]["totals"]["deals"] == 2
    assert float(managers_tile["result"]["totals"]["value"]) == 100000.0
    assert reps_tile["result"]["totals"]["deals"] == 0
    assert float(reps_tile["result"]["totals"]["value"]) == 0.0


async def test_a_tile_the_viewer_cannot_read_is_marked_rather_than_fatal(
    session_factory: async_sessionmaker[AsyncSession],
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    manager: ApiSession,
) -> None:
    """One forbidden tile must not take the whole board down.

    The board below carries an opportunities report and a leads report. The
    viewer may read leads and not opportunities, so exactly one tile renders
    and the other says why — a 403 for the page would make a shared dashboard
    useless to the people it was shared with.
    """
    pipeline = _save(manager, name="Pipeline", visibility="SHARED")
    funnel = _save(manager, name="Funnel", key="lead-funnel", visibility="SHARED")
    board = _board(manager, "Mixed board", visibility="SHARED")
    _tile(manager, str(board["id"]), str(pipeline["id"]))
    _tile(manager, str(board["id"]), str(funnel["id"]))

    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await _only_permissions(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=["dashboard.VIEW", "reports.VIEW", "leads.VIEW"],
        name="Leads only",
    )
    viewer = ApiSession(client, integration_settings.api_prefix)
    viewer.login(alpha.member.email, organization_id=alpha.organization_id)

    rendered = viewer.get(f"{BOARDS}/{board['id']}/data")

    assert rendered.status_code == 200, rendered.text
    tiles = {tile["title"]: tile for tile in rendered.json()["components"]}
    assert tiles["Pipeline"]["result"] is None
    assert tiles["Pipeline"]["unavailable"] == "permission"
    assert tiles["Funnel"]["unavailable"] is None
    assert tiles["Funnel"]["result"]["key"] == "lead-funnel"


def test_a_tile_uses_its_reports_name_until_given_one(
    as_alpha_admin: ApiSession,
) -> None:
    """A renamed report renames its tiles, unless the tile overrode the title."""
    board = _board(as_alpha_admin, "Titles")
    report = _save(as_alpha_admin, name="Original name")
    _tile(as_alpha_admin, str(board["id"]), str(report["id"]))

    before = as_alpha_admin.get(f"{BOARDS}/{board['id']}/data")
    assert before.json()["components"][0]["title"] == "Original name"

    renamed = as_alpha_admin.patch(f"{SAVED}/{report['id']}", json={"name": "New name"})
    assert renamed.status_code == 200, renamed.text

    after = as_alpha_admin.get(f"{BOARDS}/{board['id']}/data")
    assert after.json()["components"][0]["title"] == "New name"


def test_an_empty_dashboard_renders_as_empty_not_as_an_error(
    as_alpha_admin: ApiSession,
) -> None:
    board = _board(as_alpha_admin, "Nothing here yet")

    rendered = as_alpha_admin.get(f"{BOARDS}/{board['id']}/data")

    assert rendered.status_code == 200, rendered.text
    assert rendered.json()["components"] == []


# --- Tenant isolation -------------------------------------------------------


def test_one_organizations_dashboards_never_reach_another(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    board = _board(as_alpha_admin, "Alpha's board", visibility="SHARED")

    other = ApiSession(client, integration_settings.api_prefix)
    other.login(beta.admin.email, organization_id=beta.organization_id)

    assert other.get(BOARDS).json()["data"] == []
    assert other.get(f"{BOARDS}/{board['id']}").status_code == 404


# --- Authorization ----------------------------------------------------------


async def test_building_a_dashboard_needs_the_dashboard_module(
    session_factory: async_sessionmaker[AsyncSession],
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    await _only_permissions(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=["reports.VIEW", "reports.CREATE"],
        name="Reports only",
    )
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)

    refused = session.post(BOARDS, json={"name": "Not allowed"})

    assert refused.status_code == 403, refused.text


# --- Audit ------------------------------------------------------------------


def test_dashboard_changes_are_recorded_under_the_dashboard_module(
    as_alpha_admin: ApiSession,
) -> None:
    """Filed under ``dashboard``, not the ``dashboards`` table name."""
    board = _board(as_alpha_admin, "Audited board")
    report = _save(as_alpha_admin, name="Pipeline")
    _tile(as_alpha_admin, str(board["id"]), str(report["id"]))

    entries = as_alpha_admin.get("/audit-logs?module=dashboard")

    assert entries.status_code == 200, entries.text
    types = {entry["entity_type"] for entry in entries.json()["data"]}
    assert "DASHBOARD" in types
    assert "DASHBOARD_COMPONENT" in types
