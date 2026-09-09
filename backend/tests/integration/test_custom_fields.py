"""Custom fields and picklists over HTTP: the API, permissions, isolation.

The unit suite proves what one value is coerced to. This proves the things that
only exist once a database and a request are involved: that a definition
reaches the record form, that a value survives a round trip, that a retired
option does not erase the records holding it, that a rep cannot define fields,
and that one tenant's configuration is invisible to another.
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
    """A second signed-in session, for the tenant-isolation tests.

    Built here rather than reusing ``api``: the shared session object holds one
    token, so logging in as beta through it would silently sign the alpha
    fixtures out from under the test.
    """
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(beta.admin.email, organization_id=beta.organization_id)
    return session


@pytest.fixture
def as_alpha_rep(
    client: TestClient, integration_settings: Settings, alpha: Tenant
) -> ApiSession:
    """A rep's session that does not collide with ``as_alpha_admin``.

    ``as_alpha_admin`` and ``as_alpha_member`` are two logins through the *same*
    ``ApiSession`` object, so a test requesting both gets whichever signed in
    last for both of them. Any test that needs an administrator and a rep at
    once has to build the second session itself.
    """
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


def make_picklist(
    api: ApiSession, *, api_name: str = "region", options: list[str] | None = None
) -> dict:
    response = api.post(
        "/crm/picklists",
        json={
            "name": api_name.title(),
            "api_name": api_name,
            "options": [
                {"value": value, "position": index}
                for index, value in enumerate(options or ["EMEA", "APAC"])
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_field(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {
        "entity_type": "LEAD",
        "api_name": "territory",
        "label": "Territory",
        "field_type": "TEXT",
    }
    payload.update(overrides)
    response = api.post("/crm/custom-fields", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def make_lead(api: ApiSession, **overrides: object) -> dict:
    payload: dict[str, object] = {"first_name": "Ravi", "last_name": "Kumar"}
    payload.update(overrides)
    response = api.post("/crm/leads", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------


def test_a_field_can_be_defined_and_appears_on_the_entity_schema(
    as_alpha_admin: ApiSession,
) -> None:
    make_field(as_alpha_admin)

    schema = as_alpha_admin.get("/crm/custom-fields/schema/LEAD")
    assert schema.status_code == 200
    names = [field["api_name"] for field in schema.json()["fields"]]
    assert names == ["territory"]


def test_a_duplicate_api_name_on_the_same_entity_is_a_conflict(
    as_alpha_admin: ApiSession,
) -> None:
    make_field(as_alpha_admin)
    again = as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": "territory",
            "label": "Territory (again)",
            "field_type": "TEXT",
        },
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "duplicate_api_name"


def test_the_same_api_name_on_a_different_entity_is_allowed(
    as_alpha_admin: ApiSession,
) -> None:
    """Uniqueness is per record type: "Region" on leads and on accounts differ."""
    make_field(as_alpha_admin)
    make_field(as_alpha_admin, entity_type="ACCOUNT")


@pytest.mark.parametrize("reserved", ["id", "owner_id", "custom_fields", "created_at"])
def test_a_reserved_api_name_is_refused(as_alpha_admin: ApiSession, reserved: str) -> None:
    """A custom ``owner_id`` would shadow the built-in wherever the two merge."""
    response = as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": reserved,
            "label": "Shadow",
            "field_type": "TEXT",
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("api_name", ["1territory", "terr itory", "terr-itory", "terr.itory"])
def test_a_malformed_api_name_is_refused(as_alpha_admin: ApiSession, api_name: str) -> None:
    response = as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": api_name,
            "label": "Bad",
            "field_type": "TEXT",
        },
    )
    assert response.status_code == 422


def test_the_api_name_and_type_cannot_be_changed_after_creation(
    as_alpha_admin: ApiSession,
) -> None:
    """Both would strand the values already stored; the API says so rather than
    silently ignoring the change and reporting success."""
    field = make_field(as_alpha_admin)

    renamed = as_alpha_admin.patch(
        f"/crm/custom-fields/{field['id']}", json={"api_name": "region"}
    )
    assert renamed.status_code == 422

    retyped = as_alpha_admin.patch(
        f"/crm/custom-fields/{field['id']}", json={"field_type": "NUMBER"}
    )
    assert retyped.status_code == 422


def test_an_api_name_is_normalized_to_lower_case(as_alpha_admin: ApiSession) -> None:
    """Typing "Territory" into the admin form is not an error, it is a label
    the machine name is derived from."""
    field = make_field(as_alpha_admin, api_name="Territory")
    assert field["api_name"] == "territory"


def test_a_picklist_field_must_name_a_picklist(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": "region",
            "label": "Region",
            "field_type": "PICKLIST",
        },
    )
    assert response.status_code == 422


def test_a_text_field_may_not_name_a_picklist(as_alpha_admin: ApiSession) -> None:
    picklist = make_picklist(as_alpha_admin)
    response = as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": "region",
            "label": "Region",
            "field_type": "TEXT",
            "picklist_id": picklist["id"],
        },
    )
    assert response.status_code == 422


def test_a_default_the_field_would_reject_is_refused(as_alpha_admin: ApiSession) -> None:
    """Otherwise every later record creation fails with a 500 instead."""
    response = as_alpha_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": "score",
            "label": "Score",
            "field_type": "NUMBER",
            "default_value": "not a number",
        },
    )
    assert response.status_code == 422


def test_fields_can_be_reordered(as_alpha_admin: ApiSession) -> None:
    first = make_field(as_alpha_admin, api_name="alpha", label="Alpha")
    second = make_field(as_alpha_admin, api_name="beta", label="Beta")

    response = as_alpha_admin.post(
        "/crm/custom-fields/reorder",
        json={"entity_type": "LEAD", "order": [second["id"], first["id"]]},
    )
    assert response.status_code == 200
    assert [f["api_name"] for f in response.json()] == ["beta", "alpha"]

    schema = as_alpha_admin.get("/crm/custom-fields/schema/LEAD")
    assert [f["api_name"] for f in schema.json()["fields"]] == ["beta", "alpha"]


def test_a_partial_reorder_is_refused(as_alpha_admin: ApiSession) -> None:
    """"The ids I sent, then everything else somehow" is not an order anybody chose."""
    first = make_field(as_alpha_admin, api_name="alpha", label="Alpha")
    make_field(as_alpha_admin, api_name="beta", label="Beta")

    response = as_alpha_admin.post(
        "/crm/custom-fields/reorder",
        json={"entity_type": "LEAD", "order": [first["id"]]},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Values on a record
# ---------------------------------------------------------------------------


def test_a_value_survives_a_create_and_a_read(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin)
    lead = make_lead(as_alpha_admin, custom_fields={"territory": "North"})
    assert lead["custom_fields"] == {"territory": "North"}

    fetched = as_alpha_admin.get(f"/crm/leads/{lead['id']}")
    assert fetched.json()["custom_fields"] == {"territory": "North"}


def test_an_unknown_field_is_refused(as_alpha_admin: ApiSession) -> None:
    """Silently dropping it would report success for data that was not stored."""
    response = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "R", "last_name": "K", "custom_fields": {"nope": "x"}},
    )
    assert response.status_code == 422
    assert "nope" in response.text


def test_a_value_is_validated_against_its_definition(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin, api_name="score", label="Score", field_type="NUMBER")
    response = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "R", "last_name": "K", "custom_fields": {"score": "many"}},
    )
    assert response.status_code == 422


def test_a_required_field_must_be_supplied_on_create(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin, is_required=True)
    response = as_alpha_admin.post("/crm/leads", json={"first_name": "R", "last_name": "K"})
    assert response.status_code == 422
    assert "territory" in response.text


def test_a_default_is_applied_when_no_value_is_given(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin, default_value="Unassigned")
    lead = make_lead(as_alpha_admin)
    assert lead["custom_fields"] == {"territory": "Unassigned"}


def test_a_supplied_value_overrides_the_default(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin, default_value="Unassigned")
    lead = make_lead(as_alpha_admin, custom_fields={"territory": "North"})
    assert lead["custom_fields"] == {"territory": "North"}


def test_a_patch_of_a_built_in_column_leaves_custom_values_alone(
    as_alpha_admin: ApiSession,
) -> None:
    """The regression that would otherwise wipe a record's custom fields on
    every ordinary edit."""
    make_field(as_alpha_admin)
    lead = make_lead(as_alpha_admin, custom_fields={"territory": "North"})

    patched = as_alpha_admin.patch(f"/crm/leads/{lead['id']}", json={"company": "Zephyr"})
    assert patched.status_code == 200
    assert patched.json()["custom_fields"] == {"territory": "North"}


def test_a_patch_merges_rather_than_replaces_the_document(
    as_alpha_admin: ApiSession,
) -> None:
    make_field(as_alpha_admin, api_name="alpha", label="Alpha")
    make_field(as_alpha_admin, api_name="beta", label="Beta")
    lead = make_lead(as_alpha_admin, custom_fields={"alpha": "1", "beta": "2"})

    patched = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"custom_fields": {"alpha": "9"}}
    )
    assert patched.json()["custom_fields"] == {"alpha": "9", "beta": "2"}


def test_an_empty_value_clears_one_field(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin)
    lead = make_lead(as_alpha_admin, custom_fields={"territory": "North"})

    patched = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"custom_fields": {"territory": ""}}
    )
    assert patched.json()["custom_fields"] == {}


def test_a_field_made_required_later_does_not_make_old_records_uneditable(
    as_alpha_admin: ApiSession,
) -> None:
    """Requiredness is enforced where the user can act on it, not retroactively."""
    field = make_field(as_alpha_admin)
    lead = make_lead(as_alpha_admin)

    as_alpha_admin.patch(f"/crm/custom-fields/{field['id']}", json={"is_required": True})

    patched = as_alpha_admin.patch(f"/crm/leads/{lead['id']}", json={"company": "Zephyr"})
    assert patched.status_code == 200


def test_clearing_a_required_field_in_the_request_in_front_of_you_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    make_field(as_alpha_admin, is_required=True)
    lead = make_lead(as_alpha_admin, custom_fields={"territory": "North"})

    patched = as_alpha_admin.patch(
        f"/crm/leads/{lead['id']}", json={"custom_fields": {"territory": ""}}
    )
    assert patched.status_code == 422


def test_every_supported_record_type_carries_custom_fields(
    as_alpha_admin: ApiSession,
) -> None:
    """One check per entity, so a record type that silently lost the wiring
    fails here rather than in production."""
    make_field(as_alpha_admin, entity_type="ACCOUNT", api_name="tier", label="Tier")
    account = as_alpha_admin.post(
        "/crm/accounts", json={"name": "Zephyr", "custom_fields": {"tier": "Gold"}}
    )
    assert account.status_code == 201
    assert account.json()["custom_fields"] == {"tier": "Gold"}

    make_field(as_alpha_admin, entity_type="CONTACT", api_name="tier", label="Tier")
    contact = as_alpha_admin.post(
        "/crm/contacts",
        json={"first_name": "A", "last_name": "B", "custom_fields": {"tier": "Gold"}},
    )
    assert contact.status_code == 201
    assert contact.json()["custom_fields"] == {"tier": "Gold"}

    make_field(as_alpha_admin, entity_type="CAMPAIGN", api_name="tier", label="Tier")
    campaign = as_alpha_admin.post(
        "/crm/campaigns",
        json={"name": "Spring", "type": "EMAIL", "custom_fields": {"tier": "Gold"}},
    )
    assert campaign.status_code == 201
    assert campaign.json()["custom_fields"] == {"tier": "Gold"}


# ---------------------------------------------------------------------------
# Picklists
# ---------------------------------------------------------------------------


def test_a_picklist_field_accepts_only_its_options(as_alpha_admin: ApiSession) -> None:
    picklist = make_picklist(as_alpha_admin)
    make_field(
        as_alpha_admin,
        api_name="region",
        label="Region",
        field_type="PICKLIST",
        picklist_id=picklist["id"],
    )

    ok = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "R", "last_name": "K", "custom_fields": {"region": "EMEA"}},
    )
    assert ok.status_code == 201

    bad = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "R", "last_name": "K", "custom_fields": {"region": "LATAM"}},
    )
    assert bad.status_code == 422


def test_deactivating_an_option_does_not_disturb_the_records_holding_it(
    as_alpha_admin: ApiSession,
) -> None:
    """The requirement the whole storage design exists to satisfy.

    A retired option keeps rendering on the records that already hold it, and
    editing an *unrelated* field on such a record must not strip it.
    """
    picklist = make_picklist(as_alpha_admin)
    make_field(
        as_alpha_admin,
        api_name="region",
        label="Region",
        field_type="PICKLIST",
        picklist_id=picklist["id"],
    )
    lead = make_lead(as_alpha_admin, custom_fields={"region": "EMEA"})

    detail = as_alpha_admin.get(f"/crm/picklists/{picklist['id']}").json()
    emea = next(option for option in detail["options"] if option["value"] == "EMEA")
    deactivated = as_alpha_admin.patch(
        f"/crm/picklists/{picklist['id']}/options/{emea['id']}",
        json={"is_active": False},
    )
    assert deactivated.status_code == 200

    # Still stored, still returned.
    assert as_alpha_admin.get(f"/crm/leads/{lead['id']}").json()["custom_fields"] == {
        "region": "EMEA"
    }
    # Still stored after an unrelated edit.
    patched = as_alpha_admin.patch(f"/crm/leads/{lead['id']}", json={"company": "Zephyr"})
    assert patched.json()["custom_fields"] == {"region": "EMEA"}
    # But no longer selectable.
    rejected = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "S", "last_name": "T", "custom_fields": {"region": "EMEA"}},
    )
    assert rejected.status_code == 422


def test_deleting_an_option_does_not_disturb_the_records_holding_it(
    as_alpha_admin: ApiSession,
) -> None:
    picklist = make_picklist(as_alpha_admin)
    make_field(
        as_alpha_admin,
        api_name="region",
        label="Region",
        field_type="PICKLIST",
        picklist_id=picklist["id"],
    )
    lead = make_lead(as_alpha_admin, custom_fields={"region": "EMEA"})

    detail = as_alpha_admin.get(f"/crm/picklists/{picklist['id']}").json()
    emea = next(option for option in detail["options"] if option["value"] == "EMEA")
    removed = as_alpha_admin.delete(
        f"/crm/picklists/{picklist['id']}/options/{emea['id']}"
    )
    assert removed.status_code == 204

    assert as_alpha_admin.get(f"/crm/leads/{lead['id']}").json()["custom_fields"] == {
        "region": "EMEA"
    }


def test_relabelling_an_option_leaves_stored_values_untouched(
    as_alpha_admin: ApiSession,
) -> None:
    """Which is the point of separating ``value`` from ``label``."""
    picklist = make_picklist(as_alpha_admin)
    make_field(
        as_alpha_admin,
        api_name="region",
        label="Region",
        field_type="PICKLIST",
        picklist_id=picklist["id"],
    )
    lead = make_lead(as_alpha_admin, custom_fields={"region": "EMEA"})

    detail = as_alpha_admin.get(f"/crm/picklists/{picklist['id']}").json()
    emea = next(option for option in detail["options"] if option["value"] == "EMEA")
    as_alpha_admin.patch(
        f"/crm/picklists/{picklist['id']}/options/{emea['id']}",
        json={"label": "Europe, Middle East & Africa"},
    )

    assert as_alpha_admin.get(f"/crm/leads/{lead['id']}").json()["custom_fields"] == {
        "region": "EMEA"
    }


def test_a_picklist_still_used_by_a_field_cannot_be_archived(
    as_alpha_admin: ApiSession,
) -> None:
    picklist = make_picklist(as_alpha_admin)
    make_field(
        as_alpha_admin,
        api_name="region",
        label="Region",
        field_type="PICKLIST",
        picklist_id=picklist["id"],
    )
    response = as_alpha_admin.delete(f"/crm/picklists/{picklist['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "picklist_in_use"
    # The refusal names what to change.
    assert "Region" in response.json()["error"]["message"]


def test_at_most_one_option_is_the_default(as_alpha_admin: ApiSession) -> None:
    picklist = make_picklist(as_alpha_admin)
    detail = as_alpha_admin.get(f"/crm/picklists/{picklist['id']}").json()
    first, second = detail["options"][0], detail["options"][1]

    as_alpha_admin.patch(
        f"/crm/picklists/{picklist['id']}/options/{first['id']}", json={"is_default": True}
    )
    as_alpha_admin.patch(
        f"/crm/picklists/{picklist['id']}/options/{second['id']}", json={"is_default": True}
    )

    refreshed = as_alpha_admin.get(f"/crm/picklists/{picklist['id']}").json()
    defaults = [option for option in refreshed["options"] if option["is_default"]]
    assert [option["value"] for option in defaults] == [second["value"]]


def test_an_option_of_another_list_cannot_be_edited_through_this_one(
    as_alpha_admin: ApiSession,
) -> None:
    """A real option id with the wrong parent must be a 404, not an edit."""
    first = make_picklist(as_alpha_admin, api_name="region")
    second = make_picklist(as_alpha_admin, api_name="segment", options=["SMB"])
    stranger = as_alpha_admin.get(f"/crm/picklists/{second['id']}").json()["options"][0]

    response = as_alpha_admin.patch(
        f"/crm/picklists/{first['id']}/options/{stranger['id']}", json={"label": "Hijacked"}
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Filtering and sorting
# ---------------------------------------------------------------------------


def test_a_list_can_be_filtered_by_a_custom_field(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin)
    make_lead(as_alpha_admin, first_name="North", custom_fields={"territory": "North"})
    make_lead(as_alpha_admin, first_name="South", custom_fields={"territory": "South"})

    response = as_alpha_admin.get("/crm/leads?cf_territory=North")
    assert response.status_code == 200
    assert [lead["first_name"] for lead in response.json()["data"]] == ["North"]


def test_a_numeric_filter_compares_numerically_not_as_text(
    as_alpha_admin: ApiSession,
) -> None:
    """The defect a text comparison would hide: "100" sorts before "9"."""
    make_field(as_alpha_admin, api_name="score", label="Score", field_type="NUMBER")
    make_lead(as_alpha_admin, first_name="Nine", custom_fields={"score": 9})
    make_lead(as_alpha_admin, first_name="Hundred", custom_fields={"score": 100})

    response = as_alpha_admin.get("/crm/leads?cf_score__gte=50")
    assert [lead["first_name"] for lead in response.json()["data"]] == ["Hundred"]


def test_a_list_can_be_sorted_by_a_custom_field(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin, api_name="score", label="Score", field_type="NUMBER")
    make_lead(as_alpha_admin, first_name="Nine", custom_fields={"score": 9})
    make_lead(as_alpha_admin, first_name="Hundred", custom_fields={"score": 100})

    response = as_alpha_admin.get("/crm/leads?sort_by=cf_score&sort_dir=asc")
    assert [lead["first_name"] for lead in response.json()["data"]] == ["Nine", "Hundred"]


def test_a_negation_filter_includes_records_with_no_value(
    as_alpha_admin: ApiSession,
) -> None:
    """``IS DISTINCT FROM``: "not North" must not silently drop the unfilled."""
    make_field(as_alpha_admin)
    make_lead(as_alpha_admin, first_name="North", custom_fields={"territory": "North"})
    make_lead(as_alpha_admin, first_name="Unset")

    response = as_alpha_admin.get("/crm/leads?cf_territory__ne=North")
    assert [lead["first_name"] for lead in response.json()["data"]] == ["Unset"]


def test_presence_filters_work(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin)
    make_lead(as_alpha_admin, first_name="Set", custom_fields={"territory": "North"})
    make_lead(as_alpha_admin, first_name="Unset")

    empty = as_alpha_admin.get("/crm/leads?cf_territory__is_empty=1")
    assert [lead["first_name"] for lead in empty.json()["data"]] == ["Unset"]

    filled = as_alpha_admin.get("/crm/leads?cf_territory__is_not_empty=1")
    assert [lead["first_name"] for lead in filled.json()["data"]] == ["Set"]


def test_a_multi_picklist_filter_matches_containment(as_alpha_admin: ApiSession) -> None:
    picklist = make_picklist(as_alpha_admin)
    make_field(
        as_alpha_admin,
        api_name="regions",
        label="Regions",
        field_type="MULTI_PICKLIST",
        picklist_id=picklist["id"],
    )
    make_lead(as_alpha_admin, first_name="Both", custom_fields={"regions": ["EMEA", "APAC"]})
    make_lead(as_alpha_admin, first_name="Apac", custom_fields={"regions": ["APAC"]})

    response = as_alpha_admin.get("/crm/leads?cf_regions=EMEA")
    assert [lead["first_name"] for lead in response.json()["data"]] == ["Both"]


def test_an_unknown_filter_field_is_refused(as_alpha_admin: ApiSession) -> None:
    """Rather than being ignored, which would return the unfiltered list and
    look like the filter matched everything."""
    response = as_alpha_admin.get("/crm/leads?cf_nonexistent=x")
    assert response.status_code == 422


def test_an_unknown_operator_is_refused(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin)
    response = as_alpha_admin.get("/crm/leads?cf_territory__spork=x")
    assert response.status_code == 422


def test_an_operator_that_does_not_apply_to_the_type_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    make_field(as_alpha_admin, api_name="flag", label="Flag", field_type="BOOLEAN")
    response = as_alpha_admin.get("/crm/leads?cf_flag__gte=1")
    assert response.status_code == 422


def test_a_malformed_stored_value_does_not_break_the_list(
    as_alpha_admin: ApiSession,
) -> None:
    """A NUMBER field that once held text — through an import, or a definition
    added after the data — must not fail the whole list query for everyone.

    Written by creating the value under a TEXT field and then retiring it in
    favour of a NUMBER field of the same name, which is the realistic route to
    a document whose shape no longer matches its definition.
    """
    text_field = make_field(as_alpha_admin, api_name="score", label="Score")
    make_lead(as_alpha_admin, first_name="Bad", custom_fields={"score": "n/a"})
    as_alpha_admin.delete(f"/crm/custom-fields/{text_field['id']}")

    make_field(as_alpha_admin, api_name="score", label="Score", field_type="NUMBER")
    make_lead(as_alpha_admin, first_name="Good", custom_fields={"score": 10})

    response = as_alpha_admin.get("/crm/leads?cf_score__gte=5")
    assert response.status_code == 200
    assert [lead["first_name"] for lead in response.json()["data"]] == ["Good"]


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_a_rep_may_read_the_configuration_but_not_change_it(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """Reading the definitions is what makes a form drawable; defining them is
    administration."""
    make_field(as_alpha_admin)

    assert as_alpha_rep.get("/crm/custom-fields/schema/LEAD").status_code == 200
    assert as_alpha_rep.get("/crm/picklists").status_code == 200

    created = as_alpha_rep.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": "sneaky",
            "label": "Sneaky",
            "field_type": "TEXT",
        },
    )
    assert created.status_code == 403


def test_a_rep_may_not_create_or_edit_a_picklist(as_alpha_member: ApiSession) -> None:
    response = as_alpha_member.post(
        "/crm/picklists", json={"name": "Region", "api_name": "region"}
    )
    assert response.status_code == 403


def test_a_rep_may_still_write_custom_values_on_a_record_they_may_edit(
    as_alpha_admin: ApiSession, as_alpha_rep: ApiSession
) -> None:
    """``custom_fields.VIEW`` is read-only over the *configuration*; writing a
    record's values is governed by that record's own module permission."""
    make_field(as_alpha_admin)
    lead = as_alpha_rep.post(
        "/crm/leads",
        json={"first_name": "R", "last_name": "K", "custom_fields": {"territory": "North"}},
    )
    assert lead.status_code == 201
    assert lead.json()["custom_fields"] == {"territory": "North"}


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_one_tenants_definitions_are_invisible_to_another(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    make_field(as_alpha_admin)

    beta_schema = as_beta_admin.get("/crm/custom-fields/schema/LEAD")
    assert beta_schema.json()["fields"] == []
    assert as_beta_admin.get("/crm/custom-fields").json() == []


def test_another_tenants_field_cannot_be_read_or_edited(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """A guessed identifier from another tenant is a 404, indistinguishable
    from one that does not exist."""
    field = make_field(as_alpha_admin)

    assert as_beta_admin.get(f"/crm/custom-fields/{field['id']}").status_code == 404
    assert (
        as_beta_admin.patch(
            f"/crm/custom-fields/{field['id']}", json={"label": "Hijacked"}
        ).status_code
        == 404
    )
    assert as_beta_admin.delete(f"/crm/custom-fields/{field['id']}").status_code == 404


def test_another_tenants_picklist_cannot_be_read_or_edited(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    picklist = make_picklist(as_alpha_admin)

    assert as_beta_admin.get(f"/crm/picklists/{picklist['id']}").status_code == 404
    assert (
        as_beta_admin.post(
            f"/crm/picklists/{picklist['id']}/options", json={"value": "LATAM"}
        ).status_code
        == 404
    )


def test_a_field_cannot_be_pointed_at_another_tenants_picklist(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """The one place a cross-tenant reference could be smuggled in through a
    *body* rather than a URL."""
    alpha_picklist = make_picklist(as_alpha_admin)

    response = as_beta_admin.post(
        "/crm/custom-fields",
        json={
            "entity_type": "LEAD",
            "api_name": "region",
            "label": "Region",
            "field_type": "PICKLIST",
            "picklist_id": alpha_picklist["id"],
        },
    )
    assert response.status_code == 422


def test_a_tenant_cannot_write_a_value_for_another_tenants_field(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    make_field(as_alpha_admin)
    response = as_beta_admin.post(
        "/crm/leads",
        json={"first_name": "R", "last_name": "K", "custom_fields": {"territory": "North"}},
    )
    assert response.status_code == 422


def test_the_same_api_name_in_two_tenants_holds_two_independent_values(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    make_field(as_alpha_admin)
    make_field(as_beta_admin)

    alpha_lead = make_lead(as_alpha_admin, custom_fields={"territory": "North"})
    beta_lead = make_lead(as_beta_admin, custom_fields={"territory": "South"})

    assert as_alpha_admin.get(f"/crm/leads/{alpha_lead['id']}").json()["custom_fields"] == {
        "territory": "North"
    }
    assert as_beta_admin.get(f"/crm/leads/{beta_lead['id']}").json()["custom_fields"] == {
        "territory": "South"
    }
    # And neither can see the other's record at all.
    assert as_beta_admin.get(f"/crm/leads/{alpha_lead['id']}").status_code == 404


def test_a_custom_filter_cannot_reach_across_tenants(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    make_field(as_alpha_admin)
    make_field(as_beta_admin)
    make_lead(as_alpha_admin, first_name="Alpha", custom_fields={"territory": "North"})
    make_lead(as_beta_admin, first_name="Beta", custom_fields={"territory": "North"})

    response = as_alpha_admin.get("/crm/leads?cf_territory=North")
    assert [lead["first_name"] for lead in response.json()["data"]] == ["Alpha"]


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_defining_a_field_is_audited(as_alpha_admin: ApiSession) -> None:
    make_field(as_alpha_admin)
    trail = as_alpha_admin.get("/audit-logs?module=custom_fields")
    assert trail.status_code == 200
    entries = trail.json()["data"]
    assert any(entry["entity_type"] == "CUSTOM_FIELD" for entry in entries), entries
