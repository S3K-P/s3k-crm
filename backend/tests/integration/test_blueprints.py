"""Blueprints: configuring a process, and what it then refuses.

Two halves, and the second matters more. The first is that an unsatisfiable or
meaningless configuration cannot be saved. The second is that a saved one is
actually enforced on the state-change path — and, critically, that it *narrows*
what the product allows and never widens it.
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


def make_blueprint(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {"name": "Lead process", "field": "LEAD_STATUS"}
    payload.update(overrides)
    response = api.post("/crm/blueprints", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def add_transition(api: ApiSession, blueprint: dict, **overrides: object) -> dict:
    payload: dict[str, object] = {"from_state": "NEW", "to_state": "CONTACTED"}
    payload.update(overrides)
    response = api.post(f"/crm/blueprints/{blueprint['id']}/transitions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def activate(api: ApiSession, blueprint: dict) -> None:
    response = api.patch(f"/crm/blueprints/{blueprint['id']}", json={"is_active": True})
    assert response.status_code == 200, response.text


def make_lead(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {"first_name": "Ravi", "last_name": "Kumar"}
    payload.update(overrides)
    response = api.post("/crm/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def move(api: ApiSession, lead: dict, status: str, **extra: object) -> object:
    return api.post(f"/crm/leads/{lead['id']}/status", json={"status": status, **extra})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_a_blueprint_is_created_inactive(as_alpha_admin: ApiSession) -> None:
    """Activation is the moment a process starts refusing people's work, so it
    is never done in the request that creates an empty blueprint."""
    blueprint = make_blueprint(as_alpha_admin)
    assert blueprint["is_active"] is False
    assert blueprint["entity_type"] == "LEAD"


def test_the_entity_type_is_derived_not_taken_from_the_body(
    as_alpha_admin: ApiSession,
) -> None:
    """A blueprint claiming to govern a lead's status on an opportunity is not
    a state the schema should be able to reach."""
    blueprint = make_blueprint(as_alpha_admin, entity_type="OPPORTUNITY")
    assert blueprint["entity_type"] == "LEAD"


def test_a_duplicate_name_is_a_conflict(as_alpha_admin: ApiSession) -> None:
    make_blueprint(as_alpha_admin)
    again = as_alpha_admin.post(
        "/crm/blueprints", json={"name": "Lead process", "field": "LEAD_STATUS"}
    )
    assert again.status_code == 409


def test_the_field_cannot_be_changed(as_alpha_admin: ApiSession) -> None:
    """Its moves name states of that field; changing it would leave every one
    describing something that cannot happen."""
    blueprint = make_blueprint(as_alpha_admin)
    response = as_alpha_admin.patch(
        f"/crm/blueprints/{blueprint['id']}", json={"field": "OPPORTUNITY_STAGE"}
    )
    assert response.status_code == 422


def test_states_are_read_from_the_source_of_truth(as_alpha_admin: ApiSession) -> None:
    lead_states = as_alpha_admin.get("/crm/blueprints/states?field=LEAD_STATUS").json()
    assert {entry["value"] for entry in lead_states["states"]} >= {"NEW", "CONTACTED"}

    stages = as_alpha_admin.get("/crm/blueprints/states?field=OPPORTUNITY_STAGE").json()
    # The tenant's seeded pipeline, not a hard-coded list.
    assert stages["states"], stages


def test_an_unknown_state_is_refused(as_alpha_admin: ApiSession) -> None:
    blueprint = make_blueprint(as_alpha_admin)
    response = as_alpha_admin.post(
        f"/crm/blueprints/{blueprint['id']}/transitions",
        json={"from_state": "NEW", "to_state": "TELEPORTED"},
    )
    assert response.status_code == 422


def test_a_move_the_built_in_machine_refuses_cannot_be_configured(
    as_alpha_admin: ApiSession,
) -> None:
    """The central property. A rule for an impossible move could never fire,
    and its author would reasonably believe they had enabled something."""
    blueprint = make_blueprint(as_alpha_admin)
    response = as_alpha_admin.post(
        f"/crm/blueprints/{blueprint['id']}/transitions",
        json={"from_state": "NEW", "to_state": "QUALIFIED"},
    )
    assert response.status_code == 422
    assert "narrows" in response.text


def test_converted_cannot_be_configured(as_alpha_admin: ApiSession) -> None:
    """A lead reaches CONVERTED only through conversion, which creates the
    account and contact — so a blueprint must not appear to offer it."""
    blueprint = make_blueprint(as_alpha_admin)
    response = as_alpha_admin.post(
        f"/crm/blueprints/{blueprint['id']}/transitions",
        json={"from_state": "QUALIFIED", "to_state": "CONVERTED"},
    )
    assert response.status_code == 422


def test_a_duplicate_move_is_a_conflict(as_alpha_admin: ApiSession) -> None:
    blueprint = make_blueprint(as_alpha_admin)
    add_transition(as_alpha_admin, blueprint)
    again = as_alpha_admin.post(
        f"/crm/blueprints/{blueprint['id']}/transitions",
        json={"from_state": "NEW", "to_state": "CONTACTED"},
    )
    assert again.status_code == 409


def test_a_required_field_that_does_not_exist_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    """A rule naming a field the record has not got can never be satisfied,
    which would make the move permanently impossible."""
    blueprint = make_blueprint(as_alpha_admin)
    response = as_alpha_admin.post(
        f"/crm/blueprints/{blueprint['id']}/transitions",
        json={"from_state": "NEW", "to_state": "CONTACTED", "required_fields": ["nonsense"]},
    )
    assert response.status_code == 422


def test_a_custom_field_may_be_required(as_alpha_admin: ApiSession) -> None:
    """A process saying "the region must be set first" is exactly what a
    tenant-defined field is for."""
    as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": "region",
            "label": "Region",
            "field_type": "TEXT",
        },
    )
    blueprint = make_blueprint(as_alpha_admin)
    transition = add_transition(as_alpha_admin, blueprint, required_fields=["region"])
    assert transition["required_fields"] == ["region"]


def test_a_permission_that_does_not_exist_is_refused(as_alpha_admin: ApiSession) -> None:
    """``has_permission`` would answer no for everybody, administrators
    included, so the rule could never be satisfied."""
    blueprint = make_blueprint(as_alpha_admin)
    response = as_alpha_admin.post(
        f"/crm/blueprints/{blueprint['id']}/transitions",
        json={
            "from_state": "NEW",
            "to_state": "CONTACTED",
            "required_permission": "leads.TELEPORT",
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


def test_a_blueprint_with_no_moves_cannot_be_activated(
    as_alpha_admin: ApiSession,
) -> None:
    """It would constrain nothing, so activating it says something untrue."""
    blueprint = make_blueprint(as_alpha_admin)
    response = as_alpha_admin.patch(
        f"/crm/blueprints/{blueprint['id']}", json={"is_active": True}
    )
    assert response.status_code == 422


def test_only_one_blueprint_may_be_active_per_field(as_alpha_admin: ApiSession) -> None:
    """Two active processes over one column is not a configuration with an
    interpretation — which would win would depend on row order."""
    first = make_blueprint(as_alpha_admin, name="First")
    add_transition(as_alpha_admin, first)
    activate(as_alpha_admin, first)

    second = make_blueprint(as_alpha_admin, name="Second")
    add_transition(as_alpha_admin, second)
    response = as_alpha_admin.patch(
        f"/crm/blueprints/{second['id']}", json={"is_active": True}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "blueprint_already_active"


def test_two_blueprints_on_different_fields_may_both_be_active(
    as_alpha_admin: ApiSession,
) -> None:
    leads = make_blueprint(as_alpha_admin, name="Leads")
    add_transition(as_alpha_admin, leads)
    activate(as_alpha_admin, leads)

    stages = as_alpha_admin.get("/crm/blueprints/states?field=OPPORTUNITY_STAGE").json()[
        "states"
    ]
    deals = make_blueprint(as_alpha_admin, name="Deals", field="OPPORTUNITY_STAGE")
    add_transition(
        as_alpha_admin, deals, from_state="*", to_state=stages[1]["value"]
    )
    activate(as_alpha_admin, deals)


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


def test_an_inactive_blueprint_constrains_nothing(as_alpha_admin: ApiSession) -> None:
    blueprint = make_blueprint(as_alpha_admin)
    add_transition(as_alpha_admin, blueprint, required_fields=["company"])
    # Not activated.

    lead = make_lead(as_alpha_admin)
    assert move(as_alpha_admin, lead, "CONTACTED").status_code == 200


def test_a_required_field_blocks_the_move_until_it_is_filled(
    as_alpha_admin: ApiSession,
) -> None:
    blueprint = make_blueprint(as_alpha_admin)
    add_transition(as_alpha_admin, blueprint, required_fields=["company"])
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    blocked = move(as_alpha_admin, lead, "CONTACTED")
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "blueprint_transition_blocked"
    assert "company" in blocked.text

    as_alpha_admin.patch(f"/crm/leads/{lead['id']}", json={"company": "Zephyr"})
    assert move(as_alpha_admin, lead, "CONTACTED").status_code == 200


def test_a_required_custom_field_blocks_the_move(as_alpha_admin: ApiSession) -> None:
    """A blueprint sees the whole record, built-in columns and tenant-defined
    ones alike."""
    as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": "region",
            "label": "Region",
            "field_type": "TEXT",
        },
    )
    blueprint = make_blueprint(as_alpha_admin)
    add_transition(as_alpha_admin, blueprint, required_fields=["region"])
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    assert move(as_alpha_admin, lead, "CONTACTED").status_code == 422

    as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"custom_fields": {"region": "EMEA"}}
    )
    assert move(as_alpha_admin, lead, "CONTACTED").status_code == 200


def test_a_required_note_blocks_the_move(as_alpha_admin: ApiSession) -> None:
    blueprint = make_blueprint(as_alpha_admin, name="Loss process")
    add_transition(as_alpha_admin, blueprint, from_state="NEW", to_state="LOST", require_note=True)
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    assert move(as_alpha_admin, lead, "LOST").status_code == 422
    assert move(as_alpha_admin, lead, "LOST", lost_reason="Budget cut").status_code == 200


def test_a_required_permission_blocks_a_rep(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """The rep holds ``leads.EDIT`` — the route's own requirement — but not the
    ``leads.DELETE`` the process additionally demands."""
    blueprint = make_blueprint(as_alpha_admin, name="Guarded process")
    add_transition(
        as_alpha_admin,
        blueprint,
        from_state="NEW",
        to_state="LOST",
        required_permission="leads.DELETE",
    )
    activate(as_alpha_admin, blueprint)

    lead = as_alpha_rep.post(
        "/crm/leads", json={"first_name": "Ravi", "last_name": "Kumar"}
    ).json()

    blocked = move(as_alpha_rep, lead, "LOST", lost_reason="Gone quiet")
    assert blocked.status_code == 422
    assert "leads.DELETE" in blocked.text


def test_a_move_from_the_wrong_state_is_refused(as_alpha_admin: ApiSession) -> None:
    """The blueprint has an opinion about LOST and says how it is reached; the
    record is not coming from there."""
    blueprint = make_blueprint(as_alpha_admin, name="Strict")
    add_transition(as_alpha_admin, blueprint, from_state="CONTACTED", to_state="LOST")
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    blocked = move(as_alpha_admin, lead, "LOST", lost_reason="Gone quiet")
    assert blocked.status_code == 422
    assert blocked.json()["error"]["details"]["allowed_from"] == ["CONTACTED"]


def test_a_destination_the_blueprint_never_mentions_stays_open(
    as_alpha_admin: ApiSession,
) -> None:
    """The compatibility rule. An administrator who describes half their
    process has described half their process, not a wall around the rest — a
    blueprint that blocked everything unmentioned would freeze every record in
    the tenant the moment it was activated."""
    blueprint = make_blueprint(as_alpha_admin, name="Partial")
    add_transition(as_alpha_admin, blueprint, from_state="NEW", to_state="CONTACTED")
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    # UNQUALIFIED is never mentioned, so it is not constrained.
    assert move(as_alpha_admin, lead, "UNQUALIFIED", lost_reason="Wrong fit").status_code == 200


def test_a_blueprint_cannot_widen_the_built_in_machine(
    as_alpha_admin: ApiSession,
) -> None:
    """The whole design in one assertion. Even with a wildcard rule for every
    destination it can reach, an illegal move stays illegal — the built-in
    check runs first and a blueprint only ever removes from what it allows."""
    blueprint = make_blueprint(as_alpha_admin, name="Permissive")
    add_transition(as_alpha_admin, blueprint, from_state="*", to_state="CONTACTED")
    add_transition(as_alpha_admin, blueprint, from_state="*", to_state="LOST")
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    # NEW → QUALIFIED is refused by LEAD_TRANSITIONS, and no configuration can
    # change that.
    refused = move(as_alpha_admin, lead, "QUALIFIED")
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "invalid_lead_transition"


def test_deactivating_releases_the_constraint(as_alpha_admin: ApiSession) -> None:
    """The escape hatch: a process that turns out to block work has to be
    removable now."""
    blueprint = make_blueprint(as_alpha_admin)
    add_transition(as_alpha_admin, blueprint, required_fields=["company"])
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    assert move(as_alpha_admin, lead, "CONTACTED").status_code == 422

    as_alpha_admin.patch(f"/crm/blueprints/{blueprint['id']}", json={"is_active": False})
    assert move(as_alpha_admin, lead, "CONTACTED").status_code == 200


def test_removing_the_last_rule_for_a_state_reopens_it(
    as_alpha_admin: ApiSession,
) -> None:
    blueprint = make_blueprint(as_alpha_admin, name="Strict")
    transition = add_transition(
        as_alpha_admin, blueprint, from_state="CONTACTED", to_state="LOST"
    )
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    assert move(as_alpha_admin, lead, "LOST", lost_reason="x").status_code == 422

    removed = as_alpha_admin.delete(
        f"/crm/blueprints/{blueprint['id']}/transitions/{transition['id']}"
    )
    assert removed.status_code == 204
    assert move(as_alpha_admin, lead, "LOST", lost_reason="x").status_code == 200


def test_deleting_a_blueprint_releases_it_immediately(
    as_alpha_admin: ApiSession,
) -> None:
    blueprint = make_blueprint(as_alpha_admin)
    add_transition(as_alpha_admin, blueprint, required_fields=["company"])
    activate(as_alpha_admin, blueprint)

    lead = make_lead(as_alpha_admin)
    assert move(as_alpha_admin, lead, "CONTACTED").status_code == 422

    assert as_alpha_admin.delete(f"/crm/blueprints/{blueprint['id']}").status_code == 204
    assert move(as_alpha_admin, lead, "CONTACTED").status_code == 200


# ---------------------------------------------------------------------------
# Permissions and isolation
# ---------------------------------------------------------------------------


def test_a_rep_may_read_the_process_but_not_change_it(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """A rep whose move was refused has to be able to see the rule that stopped
    them; configuring one is administration."""
    make_blueprint(as_alpha_admin)

    assert as_alpha_rep.get("/crm/blueprints").status_code == 200
    created = as_alpha_rep.post(
        "/crm/blueprints", json={"name": "Sneaky", "field": "LEAD_STATUS"}
    )
    assert created.status_code == 403


def test_a_rep_may_not_add_a_transition(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    blueprint = make_blueprint(as_alpha_admin)
    response = as_alpha_rep.post(
        f"/crm/blueprints/{blueprint['id']}/transitions",
        json={"from_state": "NEW", "to_state": "CONTACTED"},
    )
    assert response.status_code == 403


def test_one_tenants_blueprints_are_invisible_to_another(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    make_blueprint(as_alpha_admin)
    assert as_beta_admin.get("/crm/blueprints").json() == []


def test_another_tenants_blueprint_cannot_be_read_or_changed(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    blueprint = make_blueprint(as_alpha_admin)

    assert as_beta_admin.get(f"/crm/blueprints/{blueprint['id']}").status_code == 404
    assert (
        as_beta_admin.patch(
            f"/crm/blueprints/{blueprint['id']}", json={"name": "Hijacked"}
        ).status_code
        == 404
    )
    assert as_beta_admin.delete(f"/crm/blueprints/{blueprint['id']}").status_code == 404


def test_one_tenants_process_does_not_constrain_another(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """The isolation that matters for this feature: a configuration is a
    tenant's own, and must not reach across."""
    blueprint = make_blueprint(as_alpha_admin)
    add_transition(as_alpha_admin, blueprint, required_fields=["company"])
    activate(as_alpha_admin, blueprint)

    beta_lead = make_lead(as_beta_admin)
    assert move(as_beta_admin, beta_lead, "CONTACTED").status_code == 200


def test_a_transition_of_another_blueprint_cannot_be_edited_through_this_one(
    as_alpha_admin: ApiSession,
) -> None:
    """A real id with the wrong parent must be a 404, not an edit."""
    first = make_blueprint(as_alpha_admin, name="First")
    second = make_blueprint(as_alpha_admin, name="Second")
    stranger = add_transition(as_alpha_admin, second)

    response = as_alpha_admin.patch(
        f"/crm/blueprints/{first['id']}/transitions/{stranger['id']}",
        json={"name": "Hijacked"},
    )
    assert response.status_code == 404


def test_configuring_a_blueprint_is_audited(as_alpha_admin: ApiSession) -> None:
    blueprint = make_blueprint(as_alpha_admin)
    add_transition(as_alpha_admin, blueprint)

    trail = as_alpha_admin.get("/audit-logs?module=blueprints").json()["data"]
    assert any(entry["entity_type"] == "BLUEPRINT" for entry in trail), trail
