"""Stage 0 foundations from ``docs/S3K_CRM_Zoho_Analysis.md``.

Four corrections, each with the failure it prevents:

* **Ambiguous conversion linking.** Account names are deliberately not unique,
  so a name lookup can return several rows. Conversion used to take the first,
  which made the destination depend on insertion order.
* **The lead lifecycle (C8).** PROPOSAL_SENT and NEGOTIATION described selling,
  which happens on an Opportunity. A lead could reach them with no deal value,
  no close date and no place in a forecast.
* **Phone matching.** Fifty rows read and filtered in Python: unindexable, and
  wrong past the fiftieth contact.
* **Close date and terminal stamping.** A deal with no close date is invisible
  to forecasting; a deal created straight into a won stage stayed open forever.
"""

from __future__ import annotations

import uuid

import pytest

from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration


def _stage_id(session: ApiSession, name: str) -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


def _lead_at(session: ApiSession, status: str, **overrides: object) -> str:
    """Create a lead and walk it to ``status`` through legal transitions."""
    payload: dict[str, object] = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "company": "Analytical Engines",
        "email": f"ada-{uuid.uuid4().hex[:8]}@engines.example",
    }
    payload.update(overrides)
    created = session.post("/crm/leads", json=payload)
    assert created.status_code == 201, created.text
    lead_id = str(created.json()["id"])

    for step in ("CONTACTED", "QUALIFIED"):
        moved = session.post(f"/crm/leads/{lead_id}/status", json={"status": step})
        assert moved.status_code == 200, moved.text
        if step == status:
            break
    return lead_id


# --- Lead lifecycle: pipeline state has one home ----------------------------


@pytest.mark.parametrize("target", ["PROPOSAL_SENT", "NEGOTIATION"])
def test_a_lead_cannot_be_moved_into_a_selling_status(
    as_alpha_admin: ApiSession, target: str
) -> None:
    """Selling happens on the Opportunity, which owns value, date and history."""
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED")

    response = as_alpha_admin.post(f"/crm/leads/{lead_id}/status", json={"status": target})

    assert response.status_code == 422, response.text
    body = response.json()["error"]
    assert body["code"] == "invalid_lead_transition"
    # The allowed set is returned so a client can render the real options.
    assert target not in body["details"]["allowed"]


def test_a_qualified_lead_may_still_be_lost_or_unqualified(
    as_alpha_admin: ApiSession,
) -> None:
    """Shortening the lifecycle must not strip its exits."""
    for target in ("UNQUALIFIED", "LOST"):
        lead_id = _lead_at(as_alpha_admin, "QUALIFIED")
        response = as_alpha_admin.post(
            f"/crm/leads/{lead_id}/status",
            json={"status": target, "lost_reason": "Budget cut"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target


def test_converted_is_still_unreachable_by_editing_status(
    as_alpha_admin: ApiSession,
) -> None:
    """The rule that predates this change, re-pinned: conversion is a transaction."""
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED")

    response = as_alpha_admin.post(f"/crm/leads/{lead_id}/status", json={"status": "CONVERTED"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_lead_transition"


# --- Conversion refuses to guess between duplicates -------------------------


def test_conversion_links_a_single_matching_account(as_alpha_admin: ApiSession) -> None:
    """One match is unambiguous, so it is reused rather than duplicated."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Analytical Engines"})
    assert account.status_code == 201
    account_id = str(account.json()["id"])
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED")

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert converted.status_code == 201, converted.text
    assert str(converted.json()["account_id"]) == account_id


def test_conversion_refuses_to_choose_between_duplicate_accounts(
    as_alpha_admin: ApiSession,
) -> None:
    """Two accounts share a name, so which one to link is the user's call.

    Taking the first silently attached the lead's pipeline to whichever row
    happened to be inserted earlier.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Analytical Engines"})
    as_alpha_admin.post(
        "/crm/accounts?allow_duplicate=true", json={"name": "Analytical Engines"}
    )
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED")

    response = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert response.status_code == 409, response.text
    body = response.json()["error"]
    assert body["code"] == "ambiguous_conversion_match"
    assert body["details"]["field"] == "account_id"
    assert len(body["details"]["candidates"]) == 2


def test_an_explicit_account_id_resolves_the_ambiguity(
    as_alpha_admin: ApiSession,
) -> None:
    """The documented way out: name the record, exactly as the error says."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Analytical Engines"})
    chosen = as_alpha_admin.post(
        "/crm/accounts?allow_duplicate=true", json={"name": "Analytical Engines"}
    )
    chosen_id = str(chosen.json()["id"])
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED")

    response = as_alpha_admin.post(
        f"/crm/leads/{lead_id}/convert", json={"account_id": chosen_id}
    )

    assert response.status_code == 201, response.text
    assert str(response.json()["account_id"]) == chosen_id


# --- A company record must name a company ------------------------------------


def test_converting_a_lead_with_no_company_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    """Conversion used to name the Account after the person.

    That produced company records called "Ada Lovelace", indistinguishable
    from real companies once created. The requirement sits at conversion —
    where the Account is actually made — rather than on lead capture, because
    meeting someone before knowing their employer is ordinary.
    """
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED", company=None)

    response = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "company_required_for_conversion"


def test_a_company_less_lead_converts_when_given_an_account(
    as_alpha_admin: ApiSession,
) -> None:
    """The documented way through: name the company the person belongs to."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Known Employer Ltd"}).json()
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED", company=None)

    response = as_alpha_admin.post(
        f"/crm/leads/{lead_id}/convert", json={"account_id": str(account["id"])}
    )

    assert response.status_code == 201, response.text
    assert str(response.json()["account_id"]) == str(account["id"])


def test_suggestions_do_not_propose_a_person_named_account(
    as_alpha_admin: ApiSession,
) -> None:
    """The form must ask for a company, not pre-fill a person's name as one."""
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED", company=None)

    body = as_alpha_admin.get(f"/crm/leads/{lead_id}/conversion-suggestions").json()

    assert body["suggested_account_name"] == ""
    assert body["suggested_contact_name"] == "Ada Lovelace"


# --- One module per kind of record -------------------------------------------


@pytest.mark.parametrize(
    ("activity_type", "endpoint"), [("TASK", "/crm/tasks"), ("NOTE", "/crm/notes")]
)
def test_activity_types_with_their_own_module_are_refused(
    as_alpha_admin: ApiSession, activity_type: str, endpoint: str
) -> None:
    """Two ways to record one thing gives "how many tasks are open" two answers."""
    response = as_alpha_admin.post(
        "/crm/activities",
        json={"type": activity_type, "subject": "Wrong module"},
    )

    assert response.status_code == 422, response.text
    body = response.json()["error"]
    assert body["details"]["use_instead"] == endpoint


def test_the_activity_types_that_have_no_module_still_work(
    as_alpha_admin: ApiSession,
) -> None:
    """Guards the guard: the refusal must be narrow."""
    for activity_type in ("CALL", "EMAIL"):
        response = as_alpha_admin.post(
            "/crm/activities",
            json={"type": activity_type, "subject": f"A {activity_type.lower()}"},
        )
        assert response.status_code == 201, response.text


# --- Phone matching is indexed, and finds matches past the old cap -----------


def test_conversion_matches_a_contact_by_differently_formatted_phone(
    as_alpha_admin: ApiSession,
) -> None:
    """Punctuation and country prefix must not defeat the match."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Phone Format Ltd"}).json()
    existing = as_alpha_admin.post(
        "/crm/contacts",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "account_id": str(account["id"]),
            "phone": "+1 (555) 010-9999",
        },
    )
    assert existing.status_code == 201, existing.text
    contact_id = str(existing.json()["id"])

    lead_id = _lead_at(
        as_alpha_admin,
        "QUALIFIED",
        first_name="Grace",
        last_name="Hopper",
        company="Phone Format Ltd",
        email=None,
        phone="555.010.9999",
    )

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert converted.status_code == 201, converted.text
    assert str(converted.json()["contact_id"]) == contact_id


def test_phone_matching_reaches_past_the_first_fifty_contacts(
    as_alpha_admin: ApiSession,
) -> None:
    """The regression this fix exists for.

    The old implementation read the fifty oldest contacts and filtered them in
    Python, so a match on a later contact was invisible and conversion created
    a duplicate while reporting success. Fifty-one contacts is the smallest
    case that distinguishes the two implementations.
    """
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Fifty One Ltd"}).json()
    account_id = str(account["id"])
    for index in range(50):
        filler = as_alpha_admin.post(
            "/crm/contacts",
            json={
                "first_name": "Filler",
                "last_name": f"Number{index}",
                "account_id": account_id,
                "phone": f"555020{index:04d}",
            },
        )
        assert filler.status_code == 201, filler.text

    target = as_alpha_admin.post(
        "/crm/contacts",
        json={
            "first_name": "Katherine",
            "last_name": "Johnson",
            "account_id": account_id,
            "phone": "555 077 1234",
        },
    )
    assert target.status_code == 201, target.text
    target_id = str(target.json()["id"])

    lead_id = _lead_at(
        as_alpha_admin,
        "QUALIFIED",
        first_name="Katherine",
        last_name="Johnson",
        company="Fifty One Ltd",
        email=None,
        phone="(555) 077-1234",
    )

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert converted.status_code == 201, converted.text
    assert str(converted.json()["contact_id"]) == target_id


def test_contacts_without_a_phone_do_not_match_each_other(
    as_alpha_admin: ApiSession,
) -> None:
    """``nullif`` earns its place: empty normalizes to NULL, not to ''.

    Without it every phone-less contact would share the empty string and
    compare equal, so conversion would link a lead to an unrelated person.
    """
    account = as_alpha_admin.post("/crm/accounts", json={"name": "No Phone Ltd"}).json()
    for index in range(2):
        created = as_alpha_admin.post(
            "/crm/contacts",
            json={
                "first_name": "Silent",
                "last_name": f"Partner{index}",
                "account_id": str(account["id"]),
            },
        )
        assert created.status_code == 201, created.text

    lead_id = _lead_at(
        as_alpha_admin,
        "QUALIFIED",
        first_name="Brand",
        last_name="New",
        company="No Phone Ltd",
        email=None,
    )

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    # A fresh contact, not one of the two phone-less ones.
    assert converted.status_code == 201, converted.text
    contact = as_alpha_admin.get(f"/crm/contacts/{converted.json()['contact_id']}").json()
    assert contact["first_name"] == "Brand"


# --- Close date and terminal stamping ---------------------------------------


def test_an_opportunity_cannot_be_created_without_a_close_date(
    as_alpha_admin: ApiSession,
) -> None:
    """No date means no forecast period, so the deal silently leaves the numbers."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Dateless Ltd"}).json()

    response = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Dateless deal",
            "account_id": str(account["id"]),
            "stage_id": _stage_id(as_alpha_admin, "Qualification"),
        },
    )

    assert response.status_code == 422


def test_a_close_date_cannot_be_cleared_by_a_patch(as_alpha_admin: ApiSession) -> None:
    """A 400-shaped mistake must not surface as an IntegrityError 500."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Keep The Date Ltd"}).json()
    created = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Dated deal",
            "account_id": str(account["id"]),
            "stage_id": _stage_id(as_alpha_admin, "Qualification"),
            "expected_close_date": "2026-12-31",
        },
    )
    assert created.status_code == 201, created.text

    response = as_alpha_admin.patch(
        f"/crm/opportunities/{created.json()['id']}",
        json={"expected_close_date": None},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "close_date_required"


def test_creating_a_deal_takes_the_probability_of_its_stage(
    as_alpha_admin: ApiSession,
) -> None:
    """A created deal must match an identical one that arrived by transition."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Probability Ltd"}).json()
    stages = as_alpha_admin.get("/crm/opportunities/stages").json()
    proposal = next(stage for stage in stages if stage["name"] == "Proposal")

    created = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Derived probability",
            "account_id": str(account["id"]),
            "stage_id": str(proposal["id"]),
            "expected_close_date": "2026-12-31",
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["win_probability"] == proposal["default_probability"]


def test_an_explicit_probability_still_wins(as_alpha_admin: ApiSession) -> None:
    """The stage default is a default, not an override."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Long Shot Ltd"}).json()

    created = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Rep knows better",
            "account_id": str(account["id"]),
            "stage_id": _stage_id(as_alpha_admin, "Proposal"),
            "expected_close_date": "2026-12-31",
            "win_probability": 5,
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["win_probability"] == 5


def test_creating_a_deal_directly_into_a_won_stage_closes_it(
    as_alpha_admin: ApiSession,
) -> None:
    """Importing historical deals does exactly this; an open row would inflate pipeline."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Backfill Ltd"}).json()

    created = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Already won",
            "account_id": str(account["id"]),
            "stage_id": _stage_id(as_alpha_admin, "Closed Won"),
            "expected_close_date": "2026-01-31",
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["won_at"] is not None
    assert created.json()["lost_at"] is None


def test_creating_a_deal_into_a_lost_stage_requires_a_reason(
    as_alpha_admin: ApiSession,
) -> None:
    """The same rule ``change_stage`` applies — loss analysis needs the reason."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "Lost Cause Ltd"}).json()
    payload: dict[str, object] = {
        "name": "Already lost",
        "account_id": str(account["id"]),
        "stage_id": _stage_id(as_alpha_admin, "Closed Lost"),
        "expected_close_date": "2026-01-31",
    }

    refused = as_alpha_admin.post("/crm/opportunities", json=payload)
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "loss_reason_required"

    accepted = as_alpha_admin.post(
        "/crm/opportunities", json={**payload, "loss_reason": "Chose a competitor"}
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["lost_at"] is not None


def test_creation_records_the_opening_stage_in_history(
    as_alpha_admin: ApiSession,
) -> None:
    """Without this the first stage is the one a deal never entered."""
    account = as_alpha_admin.post("/crm/accounts", json={"name": "History Ltd"}).json()
    stage_id = _stage_id(as_alpha_admin, "Qualification")
    created = as_alpha_admin.post(
        "/crm/opportunities",
        json={
            "name": "Traceable",
            "account_id": str(account["id"]),
            "stage_id": stage_id,
            "expected_close_date": "2026-12-31",
        },
    )
    assert created.status_code == 201, created.text

    history = as_alpha_admin.get(
        f"/crm/opportunities/{created.json()['id']}/history"
    ).json()

    assert len(history) == 1
    assert history[0]["from_stage_id"] is None
    assert str(history[0]["to_stage_id"]) == stage_id


def test_conversion_cannot_borrow_another_tenants_pipeline_stage(
    api: ApiSession, alpha: Tenant, beta: Tenant
) -> None:
    """A cross-tenant hole this stage closed.

    ``convert`` passed ``stage_id`` straight from the request body to the new
    Opportunity with no organization check, and the foreign key is on
    ``pipeline_stages.id`` alone — so a caller who knew a stage id from another
    tenant could attach their deal to that tenant's pipeline. Resolution is now
    organization-scoped, and an unresolvable id is a 404 whether it is missing
    or simply somebody else's.
    """
    api.login(beta.admin.email, organization_id=beta.organization_id)
    foreign_stage = _stage_id(api, "Qualification")

    api.login(alpha.admin.email, organization_id=alpha.organization_id)
    lead_id = _lead_at(api, "QUALIFIED")

    response = api.post(f"/crm/leads/{lead_id}/convert", json={"stage_id": foreign_stage})

    assert response.status_code == 404, response.text
    # The lead must be untouched: a refused conversion cannot half-happen.
    assert api.get(f"/crm/leads/{lead_id}").json()["status"] == "QUALIFIED"


def test_conversion_supplies_a_close_date_and_stage_probability(
    as_alpha_admin: ApiSession,
) -> None:
    """Conversion must not be the one path that produces a forecast-less deal."""
    lead_id = _lead_at(as_alpha_admin, "QUALIFIED")

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={})

    assert converted.status_code == 201, converted.text
    opportunity_id = converted.json()["opportunity_id"]
    assert opportunity_id is not None
    deal = as_alpha_admin.get(f"/crm/opportunities/{opportunity_id}").json()
    assert deal["expected_close_date"] is not None
    assert deal["win_probability"] is not None

    history = as_alpha_admin.get(f"/crm/opportunities/{opportunity_id}/history").json()
    assert len(history) == 1
    assert history[0]["from_stage_id"] is None
