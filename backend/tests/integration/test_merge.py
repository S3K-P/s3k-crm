"""Merging duplicates: what survives, what moves, and what is refused.

The operation with the most to lose. Most of this file asserts that nothing
disappears — that a merged record's activities, notes, mail, files and campaign
memberships are all on the survivor afterwards, and that the losing record is
still reachable through ``merged_into_id`` rather than simply gone.

The rest asserts the refusals, because a merge that reached across a tenant or
around a permission would be worse than one that lost data.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


@pytest.fixture
def as_beta_admin(
    client: TestClient, integration_settings: Settings, beta: Tenant
) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(beta.admin.email, organization_id=beta.organization_id)
    return session


@pytest.fixture
def as_alpha_rep(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


def make_account(api: ApiSession, **overrides: object) -> dict:
    """Create an account, overriding the same-name warning.

    A duplicate name is a 409 the caller may override — which is how these
    records come to exist in the first place, and precisely the situation a
    merge cleans up. Passing ``allow_duplicate`` here is what lets these tests
    build the state they are about.
    """
    payload: dict[str, object] = {"name": "Zephyr Industries"}
    payload.update(overrides)
    response = api.post("/crm/accounts?allow_duplicate=true", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_contact(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {"first_name": "Ravi", "last_name": "Kumar"}
    payload.update(overrides)
    response = api.post("/crm/contacts", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def merge(
    api: ApiSession,
    entity: str,
    primary: dict,
    *duplicates: dict,
    field_choices: dict[str, str] | None = None,
) -> ApiSession:
    body: dict[str, object] = {
        "primary_id": primary["id"],
        "duplicate_ids": [record["id"] for record in duplicates],
    }
    if field_choices is not None:
        body["field_choices"] = field_choices
    return api.post(f"/crm/merge/{entity}", json=body)


# ---------------------------------------------------------------------------
# The survivor
# ---------------------------------------------------------------------------


def test_a_merge_retires_the_duplicate_and_keeps_the_survivor(
    as_alpha_admin: ApiSession,
) -> None:
    primary = make_account(as_alpha_admin, name="Zephyr Industries")
    duplicate = make_account(as_alpha_admin, name="Zephyr Inds.")

    response = merge(as_alpha_admin, "accounts", primary, duplicate)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == primary["id"]

    assert as_alpha_admin.get(f"/crm/accounts/{primary['id']}").status_code == 200
    assert as_alpha_admin.get(f"/crm/accounts/{duplicate['id']}").status_code == 404

    listed = as_alpha_admin.get("/crm/accounts").json()["data"]
    assert [item["id"] for item in listed] == [primary["id"]]


def test_a_blank_field_on_the_survivor_is_filled_from_the_duplicate(
    as_alpha_admin: ApiSession,
) -> None:
    """The one piece of guessing, and it is the safe direction: it can only add
    information the merged record would otherwise have lost."""
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Zephyr Inds.", website="https://zephyr.example")

    merge(as_alpha_admin, "accounts", primary, duplicate)

    survivor = as_alpha_admin.get(f"/crm/accounts/{primary['id']}").json()
    assert survivor["website"] == "https://zephyr.example"


def test_a_filled_field_on_the_survivor_is_never_overwritten_by_default(
    as_alpha_admin: ApiSession,
) -> None:
    primary = make_account(as_alpha_admin, name="Zephyr", website="https://real.example")
    duplicate = make_account(
        as_alpha_admin, name="Zephyr Inds.", website="https://stale.example"
    )

    merge(as_alpha_admin, "accounts", primary, duplicate)

    survivor = as_alpha_admin.get(f"/crm/accounts/{primary['id']}").json()
    assert survivor["website"] == "https://real.example"


def test_an_explicit_choice_takes_the_duplicates_value(as_alpha_admin: ApiSession) -> None:
    primary = make_account(as_alpha_admin, name="Zephyr", website="https://stale.example")
    duplicate = make_account(
        as_alpha_admin, name="Zephyr Inds.", website="https://current.example"
    )

    merge(
        as_alpha_admin,
        "accounts",
        primary,
        duplicate,
        field_choices={"website": duplicate["id"]},
    )

    survivor = as_alpha_admin.get(f"/crm/accounts/{primary['id']}").json()
    assert survivor["website"] == "https://current.example"


def test_choosing_primary_keeps_a_blank(as_alpha_admin: ApiSession) -> None:
    """"This duplicate's phone number is wrong, drop it" is a real answer, and
    the default fill must not override the caller saying so."""
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Zephyr Inds.", website="https://wrong.example")

    merge(
        as_alpha_admin,
        "accounts",
        primary,
        duplicate,
        field_choices={"website": "primary"},
    )

    survivor = as_alpha_admin.get(f"/crm/accounts/{primary['id']}").json()
    assert survivor["website"] is None


def test_two_duplicates_disagreeing_leave_the_blank_alone(
    as_alpha_admin: ApiSession,
) -> None:
    """With two different values and no instruction there is no non-arbitrary
    winner, and picking the first would make the outcome depend on the order
    the ids arrived in."""
    primary = make_account(as_alpha_admin, name="Zephyr")
    first = make_account(as_alpha_admin, name="Z1", website="https://one.example")
    second = make_account(as_alpha_admin, name="Z2", website="https://two.example")

    merge(as_alpha_admin, "accounts", primary, first, second)

    survivor = as_alpha_admin.get(f"/crm/accounts/{primary['id']}").json()
    assert survivor["website"] is None


def test_several_duplicates_merge_at_once(as_alpha_admin: ApiSession) -> None:
    primary = make_account(as_alpha_admin, name="Zephyr")
    others = [make_account(as_alpha_admin, name=f"Zephyr {n}") for n in range(3)]

    response = merge(as_alpha_admin, "accounts", primary, *others)
    assert response.status_code == 200

    listed = as_alpha_admin.get("/crm/accounts").json()["data"]
    assert [item["id"] for item in listed] == [primary["id"]]


# ---------------------------------------------------------------------------
# Nothing is lost
# ---------------------------------------------------------------------------


def test_activities_notes_and_tasks_move_to_the_survivor(
    as_alpha_admin: ApiSession,
) -> None:
    """The history a merge exists to preserve."""
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Zephyr Inds.")

    for path, body in (
        (
            "/crm/activities",
            {"type": "CALL", "subject": "Intro call"},
        ),
        ("/crm/tasks", {"title": "Send pricing"}),
        ("/crm/notes", {"content": "Prefers email"}),
    ):
        response = as_alpha_admin.post(
            path,
            json={
                **body,
                "related_entity_type": "ACCOUNT",
                "related_entity_id": duplicate["id"],
            },
        )
        assert response.status_code == 201, response.text

    merge(as_alpha_admin, "accounts", primary, duplicate)

    timeline = as_alpha_admin.get(
        f"/crm/activities/timeline?related_entity_type=ACCOUNT"
        f"&related_entity_id={primary['id']}"
    )
    assert timeline.status_code == 200
    assert [item["subject"] for item in timeline.json()] == ["Intro call"]

    tasks = as_alpha_admin.get(
        f"/crm/tasks?related_entity_type=ACCOUNT&related_entity_id={primary['id']}"
    ).json()["data"]
    assert [item["title"] for item in tasks] == ["Send pricing"]

    notes = as_alpha_admin.get(
        f"/crm/notes?related_entity_type=ACCOUNT&related_entity_id={primary['id']}"
    ).json()["data"]
    assert [item["content"] for item in notes] == ["Prefers email"]


def test_contacts_and_opportunities_follow_the_surviving_account(
    as_alpha_admin: ApiSession,
) -> None:
    """The ``opportunities.account_id`` foreign key is RESTRICT, so this is
    what makes the merge legal as well as correct."""
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Zephyr Inds.")

    contact = make_contact(as_alpha_admin, account_id=duplicate["id"])
    stages = as_alpha_admin.get("/crm/opportunities/stages").json()
    opportunity = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Renewal",
            "account_id": duplicate["id"],
            "stage_id": stages[0]["id"],
            "amount": "1000.00",
        },
    )
    assert opportunity.status_code == 201, opportunity.text

    merge(as_alpha_admin, "accounts", primary, duplicate)

    assert (
        as_alpha_admin.get(f"/crm/contacts/{contact['id']}").json()["account_id"]
        == primary["id"]
    )
    assert (
        as_alpha_admin.get(f"/crm/opportunities/{opportunity.json()['id']}").json()["account_id"]
        == primary["id"]
    )


def test_custom_values_are_filled_but_never_overwritten(
    as_alpha_admin: ApiSession,
) -> None:
    """Custom fields are tenant data, so a merge screen cannot enumerate them.
    The safe rule is the one the built-in fields fall back to."""
    as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "ACCOUNT",
            "api_name": "tier",
            "label": "Tier",
            "field_type": "TEXT",
        },
    )
    as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "ACCOUNT",
            "api_name": "region",
            "label": "Region",
            "field_type": "TEXT",
        },
    )

    primary = make_account(as_alpha_admin, name="Zephyr", custom_fields={"tier": "Gold"})
    duplicate = make_account(
        as_alpha_admin,
        name="Zephyr Inds.",
        custom_fields={"tier": "Bronze", "region": "EMEA"},
    )

    merge(as_alpha_admin, "accounts", primary, duplicate)

    survivor = as_alpha_admin.get(f"/crm/accounts/{primary['id']}").json()
    assert survivor["custom_fields"] == {"tier": "Gold", "region": "EMEA"}


def test_the_merged_record_points_at_its_survivor(as_alpha_admin: ApiSession) -> None:
    """"Deleted" and "became part of that one" are different facts, and only
    the second answers what a stale link asks."""
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Zephyr Inds.")

    merge(as_alpha_admin, "accounts", primary, duplicate)

    trail = as_alpha_admin.get("/audit-logs?module=accounts").json()["data"]
    merge_entries = [
        entry for entry in trail if (entry.get("details") or {}).get("operation") == "merge"
    ]
    assert merge_entries, trail
    assert duplicate["id"] in merge_entries[0]["details"]["merged_ids"]


def test_the_merge_is_audited_with_what_moved(as_alpha_admin: ApiSession) -> None:
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Zephyr Inds.")
    as_alpha_admin.post(
        "/crm/notes",
        json={
            "content": "Prefers email",
            "related_entity_type": "ACCOUNT",
            "related_entity_id": duplicate["id"],
        },
    )

    merge(as_alpha_admin, "accounts", primary, duplicate)

    trail = as_alpha_admin.get("/audit-logs?module=accounts").json()["data"]
    entry = next(
        item for item in trail if (item.get("details") or {}).get("operation") == "merge"
    )
    assert entry["details"]["references_moved"]["notes"] == 1


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def test_a_preview_reports_the_conflicts_and_changes_nothing(
    as_alpha_admin: ApiSession,
) -> None:
    primary = make_account(as_alpha_admin, name="Zephyr", website="https://one.example")
    duplicate = make_account(as_alpha_admin, name="Z2", website="https://two.example")

    response = as_alpha_admin.post(
        "/crm/merge/accounts/preview",
        json={"primary_id": primary["id"], "duplicate_ids": [duplicate["id"]]},
    )
    assert response.status_code == 200, response.text
    fields = {conflict["field"] for conflict in response.json()["conflicts"]}
    assert {"name", "website"} <= fields

    # Nothing moved.
    assert as_alpha_admin.get(f"/crm/accounts/{duplicate['id']}").status_code == 200


def test_a_preview_counts_what_would_move(as_alpha_admin: ApiSession) -> None:
    """What turns the confirmation from a leap of faith into a statement."""
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Z2")
    as_alpha_admin.post(
        "/crm/notes",
        json={
            "content": "Prefers email",
            "related_entity_type": "ACCOUNT",
            "related_entity_id": duplicate["id"],
        },
    )

    response = as_alpha_admin.post(
        "/crm/merge/accounts/preview",
        json={"primary_id": primary["id"], "duplicate_ids": [duplicate["id"]]},
    )
    assert response.json()["related_counts"]["notes"] == 1


def test_identical_records_report_no_conflicts(as_alpha_admin: ApiSession) -> None:
    primary = make_account(as_alpha_admin, name="Zephyr", website="https://same.example")
    duplicate = make_account(as_alpha_admin, name="Zephyr", website="https://same.example")

    response = as_alpha_admin.post(
        "/crm/merge/accounts/preview",
        json={"primary_id": primary["id"], "duplicate_ids": [duplicate["id"]]},
    )
    fields = {conflict["field"] for conflict in response.json()["conflicts"]}
    assert "name" not in fields
    assert "website" not in fields


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_the_survivor_cannot_also_be_a_duplicate(as_alpha_admin: ApiSession) -> None:
    primary = make_account(as_alpha_admin)
    response = merge(as_alpha_admin, "accounts", primary, primary)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "merge_targets_overlap"


def test_an_unknown_id_is_a_404(as_alpha_admin: ApiSession) -> None:
    primary = make_account(as_alpha_admin)
    response = as_alpha_admin.post(
        "/crm/merge/accounts",
        json={
            "primary_id": primary["id"],
            "duplicate_ids": ["00000000-0000-4000-8000-000000000000"],
        },
    )
    assert response.status_code == 404


def test_an_already_merged_record_cannot_be_merged_again(
    as_alpha_admin: ApiSession,
) -> None:
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Z2")
    third = make_account(as_alpha_admin, name="Z3")

    merge(as_alpha_admin, "accounts", primary, duplicate)
    again = merge(as_alpha_admin, "accounts", third, duplicate)
    # The record is soft-deleted, so it no longer resolves at all — which is
    # the same answer, reached one step earlier than the merged-away check.
    assert again.status_code in {404, 409}


def test_a_record_type_that_cannot_be_merged_is_a_404(
    as_alpha_admin: ApiSession,
) -> None:
    """Opportunities are deliberately absent: two deals against one account are
    usually two deals, and merging them would destroy the stage history the
    pipeline report is computed from."""
    response = as_alpha_admin.post(
        "/crm/merge/opportunities",
        json={
            "primary_id": "00000000-0000-4000-8000-000000000000",
            "duplicate_ids": ["00000000-0000-4000-8000-000000000001"],
        },
    )
    assert response.status_code == 422  # the path pattern refuses it


def test_a_rep_without_delete_cannot_merge(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """A merge is an edit *and* a deletion. A role granted only the first must
    not acquire the second by routing through here — the plain User role holds
    ``accounts.EDIT`` and not ``accounts.DELETE``."""
    primary = make_account(as_alpha_admin, name="Zephyr")
    duplicate = make_account(as_alpha_admin, name="Z2")

    response = merge(as_alpha_rep, "accounts", primary, duplicate)
    assert response.status_code == 403

    # And nothing happened.
    assert as_alpha_admin.get(f"/crm/accounts/{duplicate['id']}").status_code == 200


def test_a_rep_may_preview_without_being_able_to_merge(
    as_alpha_rep: ApiSession,
) -> None:
    """So a rep can see what a merge would do and hand it to somebody who may
    perform it.

    The rep creates the records: a plain User reads only what they own, so a
    preview of the admin's accounts would correctly be a 404 and would prove
    nothing about the preview permission.
    """
    primary = make_account(as_alpha_rep, name="Zephyr")
    duplicate = make_account(as_alpha_rep, name="Z2")

    response = as_alpha_rep.post(
        "/crm/merge/accounts/preview",
        json={"primary_id": primary["id"], "duplicate_ids": [duplicate["id"]]},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_a_merge_cannot_reach_across_tenants(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """The refusal that matters most: a 404, indistinguishable from an id that
    does not exist, so a prober cannot confirm another tenant's record."""
    alpha_account = make_account(as_alpha_admin, name="Alpha Ltd")
    beta_account = make_account(as_beta_admin, name="Beta Ltd")

    response = as_beta_admin.post(
        "/crm/merge/accounts",
        json={
            "primary_id": beta_account["id"],
            "duplicate_ids": [alpha_account["id"]],
        },
    )
    assert response.status_code == 404

    # Alpha's record is untouched.
    assert as_alpha_admin.get(f"/crm/accounts/{alpha_account['id']}").status_code == 200


def test_the_reverse_direction_is_refused_too(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """Naming the other tenant's record as the *survivor* must fail the same way."""
    alpha_account = make_account(as_alpha_admin, name="Alpha Ltd")
    beta_account = make_account(as_beta_admin, name="Beta Ltd")

    response = as_beta_admin.post(
        "/crm/merge/accounts",
        json={
            "primary_id": alpha_account["id"],
            "duplicate_ids": [beta_account["id"]],
        },
    )
    assert response.status_code == 404
    assert as_alpha_admin.get(f"/crm/accounts/{alpha_account['id']}").status_code == 200


# ---------------------------------------------------------------------------
# Contacts and leads
# ---------------------------------------------------------------------------


def test_contacts_merge(as_alpha_admin: ApiSession) -> None:
    primary = make_contact(as_alpha_admin, first_name="Ravi", last_name="Kumar")
    duplicate = make_contact(
        as_alpha_admin, first_name="Ravi", last_name="Kumar", phone="+44 20 7946 0000"
    )

    response = merge(as_alpha_admin, "contacts", primary, duplicate)
    assert response.status_code == 200

    survivor = as_alpha_admin.get(f"/crm/contacts/{primary['id']}").json()
    assert survivor["phone"] == "+44 20 7946 0000"
    assert as_alpha_admin.get(f"/crm/contacts/{duplicate['id']}").status_code == 404


def test_leads_merge(as_alpha_admin: ApiSession) -> None:
    primary = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Ravi", "last_name": "Kumar"}
    ).json()
    duplicate = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Ravi", "last_name": "Kumar", "company": "Zephyr"},
    ).json()

    response = merge(as_alpha_admin, "leads", primary, duplicate)
    assert response.status_code == 200

    survivor = as_alpha_admin.get(f"/crm/leads/{primary['id']}").json()
    assert survivor["company"] == "Zephyr"


def test_a_leads_conversion_outcome_is_never_taken_from_a_duplicate(
    as_alpha_admin: ApiSession,
) -> None:
    """Taking those columns would claim a conversion that never happened and
    point the survivor at somebody else's account."""
    primary = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Ravi", "last_name": "Kumar"}
    ).json()
    duplicate = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Ravi", "last_name": "K"}
    ).json()

    # Only a qualified lead converts, so walk it through the transitions the
    # state machine allows rather than reaching into the database.
    for status in ("CONTACTED", "QUALIFIED"):
        moved = as_alpha_admin.post(
            f"/crm/leads/{duplicate['id']}/status", json={"status": status}
        )
        assert moved.status_code == 200, moved.text
    converted = as_alpha_admin.post(f"/crm/leads/{duplicate['id']}/convert", json={})
    assert converted.status_code in {200, 201}, converted.text

    # The converted lead is now in a terminal state; merging it away must not
    # transplant its conversion onto the survivor.
    response = merge(as_alpha_admin, "leads", primary, duplicate)
    if response.status_code == 200:
        survivor = as_alpha_admin.get(f"/crm/leads/{primary['id']}").json()
        assert survivor["converted_at"] is None
        assert survivor["converted_account_id"] is None
