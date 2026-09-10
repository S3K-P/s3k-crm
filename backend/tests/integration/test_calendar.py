"""The calendar: what lands on the grid, and where the day boundaries fall.

Timezones are the whole risk here, so most of this file is about them. A grid
built from a naive boundary is wrong by the user's offset — up to fourteen
hours, which moves entries between days — and it is wrong silently, in a way
that looks like missing data rather than like a bug.
"""

from __future__ import annotations

import datetime as dt
import uuid
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration

#: A fixed instant, so nothing here depends on when the suite runs.
BASE = dt.datetime(2026, 3, 4, 12, 0, tzinfo=dt.UTC)


def iso(moment: dt.datetime) -> str:
    """An instant, for a JSON body."""
    return moment.isoformat()


def q(moment: dt.datetime) -> str:
    """The same instant, percent-encoded for a *query string*.

    The ``+`` of a positive offset means "space" in a query string, so it has
    to be encoded. The API repairs the un-encoded form too — see
    ``CalendarRange._restore_plus_in_offset`` — but the tests send what a
    correct client sends, so a regression in that repair is caught by the one
    test written against it rather than by every test at once.
    """
    return quote(moment.isoformat(), safe="")


@pytest.fixture
def as_beta_admin(
    client: TestClient, integration_settings: Settings, beta: Tenant
) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(beta.admin.email, organization_id=beta.organization_id)
    return session


def make_meeting(
    api: ApiSession,
    *,
    start: dt.datetime,
    end: dt.datetime | None = None,
    subject: str = "Discovery call",
) -> dict:
    detail: dict[str, object] = {"meeting_type": "PHONE", "start_time": iso(start)}
    if end is not None:
        detail["end_time"] = iso(end)
    response = api.post(
        "/crm/activities",
        json={"type": "MEETING", "subject": subject, "meeting": detail},
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_task(api: ApiSession, *, due: dt.datetime, title: str = "Send proposal") -> dict:
    response = api.post("/crm/tasks", json={"title": title, "due_date": iso(due)})
    assert response.status_code == 201, response.text
    return response.json()


def read(api: ApiSession, *, start: dt.datetime, end: dt.datetime, **params: str) -> dict:
    query = "&".join(
        [f"start={q(start)}", f"end={q(end)}", *(f"{k}={v}" for k, v in params.items())]
    )
    response = api.get(f"/crm/calendar?{query}")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# What lands on the grid
# ---------------------------------------------------------------------------


def test_a_meeting_and_a_task_share_one_timeline(as_alpha_admin: ApiSession) -> None:
    make_meeting(as_alpha_admin, start=BASE, end=BASE + dt.timedelta(hours=1))
    make_task(as_alpha_admin, due=BASE + dt.timedelta(hours=2))

    body = read(
        as_alpha_admin,
        start=BASE - dt.timedelta(days=1),
        end=BASE + dt.timedelta(days=1),
    )
    sources = [entry["source"] for entry in body["entries"]]
    assert sorted(sources) == ["MEETING", "TASK"]


def test_entries_are_sorted_across_both_sources(as_alpha_admin: ApiSession) -> None:
    """They arrive from two queries, each ordered within itself; a grid that
    groups by day needs one sequence."""
    make_task(as_alpha_admin, due=BASE + dt.timedelta(hours=3), title="Later task")
    make_meeting(as_alpha_admin, start=BASE + dt.timedelta(hours=1), subject="Earlier call")

    body = read(as_alpha_admin, start=BASE, end=BASE + dt.timedelta(days=1))
    assert [entry["title"] for entry in body["entries"]] == ["Earlier call", "Later task"]


def test_a_task_is_marked_all_day(as_alpha_admin: ApiSession) -> None:
    """A due date is a deadline, not an appointment: placing it at whatever
    time the column holds would imply a precision nobody entered."""
    make_task(as_alpha_admin, due=BASE)
    body = read(
        as_alpha_admin,
        start=BASE - dt.timedelta(hours=1),
        end=BASE + dt.timedelta(hours=1),
    )
    assert body["entries"][0]["all_day"] is True
    assert body["entries"][0]["end"] is None


def test_a_meeting_with_no_end_time_is_a_point(as_alpha_admin: ApiSession) -> None:
    """Not filled with a guessed duration — the grid draws what the record says."""
    make_meeting(as_alpha_admin, start=BASE)
    body = read(
        as_alpha_admin,
        start=BASE - dt.timedelta(hours=1),
        end=BASE + dt.timedelta(hours=1),
    )
    assert body["entries"][0]["end"] is None
    assert body["entries"][0]["all_day"] is False


def test_a_task_with_no_due_date_is_not_on_the_grid(as_alpha_admin: ApiSession) -> None:
    """It is not scheduled; putting it on a day nobody chose would make the
    grid claim something the record does not say."""
    created = as_alpha_admin.post("/crm/tasks", json={"title": "Someday"})
    assert created.status_code == 201

    body = read(
        as_alpha_admin,
        start=BASE - dt.timedelta(days=30),
        end=BASE + dt.timedelta(days=30),
    )
    assert body["entries"] == []


def test_sources_can_be_narrowed(as_alpha_admin: ApiSession) -> None:
    make_meeting(as_alpha_admin, start=BASE)
    make_task(as_alpha_admin, due=BASE)

    body = read(
        as_alpha_admin,
        start=BASE - dt.timedelta(days=1),
        end=BASE + dt.timedelta(days=1),
        source="TASK",
    )
    assert [entry["source"] for entry in body["entries"]] == ["TASK"]


def test_an_unknown_source_falls_back_to_everything(as_alpha_admin: ApiSession) -> None:
    """A client sending a source this version does not know should get a
    calendar, not a 422."""
    make_meeting(as_alpha_admin, start=BASE)
    body = read(
        as_alpha_admin,
        start=BASE - dt.timedelta(days=1),
        end=BASE + dt.timedelta(days=1),
        source="BIRTHDAY",
    )
    assert len(body["entries"]) == 1


# ---------------------------------------------------------------------------
# Window boundaries
# ---------------------------------------------------------------------------


def test_the_window_is_half_open(as_alpha_admin: ApiSession) -> None:
    """``[start, end)``: an entry exactly on the upper boundary belongs to the
    *next* window, so two consecutive requests cannot double-count it."""
    make_meeting(as_alpha_admin, start=BASE, subject="On the lower edge")
    make_meeting(as_alpha_admin, start=BASE + dt.timedelta(hours=1), subject="On the upper edge")

    body = read(as_alpha_admin, start=BASE, end=BASE + dt.timedelta(hours=1))
    assert [entry["title"] for entry in body["entries"]] == ["On the lower edge"]


def test_a_meeting_overlapping_the_window_start_is_included(
    as_alpha_admin: ApiSession,
) -> None:
    """A Monday-morning view has to show the call that began on Sunday night."""
    make_meeting(
        as_alpha_admin,
        start=BASE - dt.timedelta(hours=2),
        end=BASE + dt.timedelta(hours=2),
        subject="Straddles the boundary",
    )
    body = read(as_alpha_admin, start=BASE, end=BASE + dt.timedelta(hours=1))
    assert [entry["title"] for entry in body["entries"]] == ["Straddles the boundary"]


def test_a_naive_boundary_is_refused(as_alpha_admin: ApiSession) -> None:
    """The failure this exists to prevent is silent: a grid built from a naive
    boundary is wrong by the user's offset and looks like missing data."""
    response = as_alpha_admin.get(
        "/crm/calendar?start=2026-03-01T00:00:00&end=2026-03-31T00:00:00"
    )
    assert response.status_code == 422


def test_an_inverted_window_is_refused(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get(
        f"/crm/calendar?start={q(BASE)}&end={q(BASE - dt.timedelta(days=1))}"
    )
    assert response.status_code == 422


def test_an_absurd_window_is_refused(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get(
        f"/crm/calendar?start={q(BASE)}&end={q(BASE + dt.timedelta(days=4000))}"
    )
    assert response.status_code == 422


def test_a_non_utc_window_finds_the_same_entries(as_alpha_admin: ApiSession) -> None:
    """The client sends its user's local month; the server compares instants.
    The same meeting must be found whichever offset the window carries."""
    make_meeting(as_alpha_admin, start=BASE, subject="Noon UTC")

    kolkata = dt.timezone(dt.timedelta(hours=5, minutes=30))
    body = read(
        as_alpha_admin,
        start=(BASE - dt.timedelta(hours=1)).astimezone(kolkata),
        end=(BASE + dt.timedelta(hours=1)).astimezone(kolkata),
    )
    assert [entry["title"] for entry in body["entries"]] == ["Noon UTC"]


def test_a_window_across_a_date_line_offset_selects_the_right_day(
    as_alpha_admin: ApiSession,
) -> None:
    """The case a "date" parameter would get wrong.

    A meeting at 23:00 UTC on the 4th is on the *5th* for a +14:00 user, and
    their "5 March" window has to contain it. Because the client sends
    instants, it does — where a server-side date would have used its own idea
    of a day boundary and dropped it.
    """
    make_meeting(as_alpha_admin, start=dt.datetime(2026, 3, 4, 23, 0, tzinfo=dt.UTC))

    kiritimati = dt.timezone(dt.timedelta(hours=14))
    local_day_start = dt.datetime(2026, 3, 5, 0, 0, tzinfo=kiritimati)
    body = read(as_alpha_admin, start=local_day_start, end=local_day_start + dt.timedelta(days=1))
    assert len(body["entries"]) == 1


# ---------------------------------------------------------------------------
# Permissions and isolation
# ---------------------------------------------------------------------------


def test_a_rep_sees_only_their_own_tasks(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """Tasks are owner-scoped, and the calendar must not become the one screen
    where that stops being true."""
    admin = ApiSession(client, integration_settings.api_prefix)
    admin.login(alpha.admin.email, organization_id=alpha.organization_id)
    make_task(admin, due=BASE, title="The admin's task")

    rep = ApiSession(client, integration_settings.api_prefix)
    rep.login(alpha.member.email, organization_id=alpha.organization_id)
    make_task(rep, due=BASE, title="The rep's task")

    body = read(rep, start=BASE - dt.timedelta(days=1), end=BASE + dt.timedelta(days=1))
    titles = [entry["title"] for entry in body["entries"]]
    assert "The rep's task" in titles
    assert "The admin's task" not in titles


def test_owner_id_narrows_but_cannot_widen(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> None:
    """Passing a colleague's id is applied on top of visibility, not instead
    of it, so it can only ever return less."""
    admin = ApiSession(client, integration_settings.api_prefix)
    admin.login(alpha.admin.email, organization_id=alpha.organization_id)
    make_task(admin, due=BASE, title="The admin's task")

    rep = ApiSession(client, integration_settings.api_prefix)
    rep.login(alpha.member.email, organization_id=alpha.organization_id)

    body = read(
        rep,
        start=BASE - dt.timedelta(days=1),
        end=BASE + dt.timedelta(days=1),
        owner_id=str(alpha.admin.user_id),
    )
    assert body["entries"] == []


def test_one_tenants_calendar_is_invisible_to_another(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    make_meeting(as_alpha_admin, start=BASE, subject="Alpha call")
    make_task(as_alpha_admin, due=BASE, title="Alpha task")

    body = read(as_beta_admin, start=BASE - dt.timedelta(days=1), end=BASE + dt.timedelta(days=1))
    assert body["entries"] == []


def test_an_archived_meeting_leaves_the_grid(as_alpha_admin: ApiSession) -> None:
    meeting = make_meeting(as_alpha_admin, start=BASE)
    assert as_alpha_admin.delete(f"/crm/activities/{meeting['id']}").status_code == 204

    body = read(
        as_alpha_admin,
        start=BASE - dt.timedelta(days=1),
        end=BASE + dt.timedelta(days=1),
    )
    assert body["entries"] == []


def test_an_entry_carries_its_related_record(as_alpha_admin: ApiSession) -> None:
    """What makes clicking a box go somewhere."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Zephyr"}).json()
    response = as_alpha_admin.post(
        "/crm/activities",
        json={
            "type": "MEETING",
            "subject": "Zephyr review",
            "related_entity_type": "ACCOUNT",
            "related_entity_id": account["id"],
            "meeting": {"meeting_type": "PHONE", "start_time": iso(BASE)},
        },
    )
    assert response.status_code == 201, response.text

    body = read(
        as_alpha_admin,
        start=BASE - dt.timedelta(days=1),
        end=BASE + dt.timedelta(days=1),
    )
    entry = body["entries"][0]
    assert entry["related_entity_type"] == "ACCOUNT"
    assert uuid.UUID(entry["related_entity_id"]) == uuid.UUID(account["id"])
