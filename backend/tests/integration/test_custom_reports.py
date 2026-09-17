"""The custom (ad-hoc) report builder (Checkpoint 5).

Real PostgreSQL, real RLS, every assertion through HTTP — the same standard
``test_reports.py`` holds the built-in catalogue to, because a custom report
runs through the identical four-step security model (see
``reports/custom.py``'s module docstring): resolve the definition, authorize
against the entity's own module, resolve ``RecordVisibility`` for that module,
aggregate inside PostgreSQL. Nothing here should behave more loosely than the
catalogue simply because the shape came from a request body instead of
reviewed code — that is the whole point of the allow-list in
``reports/fields.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant, grant_custom_role, membership_id_for

pytestmark = pytest.mark.integration

REPORTS = "/crm/reports"


# --- Fixtures ----------------------------------------------------------------


@pytest.fixture
def rep(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)
    return session


@pytest.fixture
def manager(client: TestClient, integration_settings: Settings, alpha: Tenant) -> ApiSession:
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.manager.email, organization_id=alpha.organization_id)
    return session


def _stage_id(session: ApiSession, name: str = "Qualification") -> str:
    stages = session.get("/crm/opportunities/stages").json()
    return str(next(stage["id"] for stage in stages if stage["name"] == name))


def _account(session: ApiSession, name: str) -> str:
    created = session.post("/crm/accounts", json={"name": name})
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _deal(
    session: ApiSession, *, name: str, account_id: str, value: str, stage: str = "Qualification"
) -> str:
    created = session.post(
        "/crm/opportunities",
        json={
            "name": name,
            "account_id": account_id,
            "stage_id": _stage_id(session, stage),
            "deal_value": value,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


def _lead(
    session: ApiSession, *, first_name: str, last_name: str, status: str | None = None
) -> str:
    created = session.post("/crm/leads", json={"first_name": first_name, "last_name": last_name})
    assert created.status_code == 201, created.text
    lead_id = created.json()["id"]
    if status is not None:
        moved = session.post(f"/crm/leads/{lead_id}/status", json={"status": status})
        assert moved.status_code == 200, moved.text
    return str(lead_id)


def _preview(session: ApiSession, definition: dict, **params: object) -> dict:
    response = session.post(f"{REPORTS}/custom/preview", json={"definition": definition, **params})
    assert response.status_code == 200, response.text
    result: dict = response.json()
    return result


# --- Row-listing reports ------------------------------------------------------


def test_a_row_listing_report_selects_exactly_the_requested_fields(
    as_alpha_admin: ApiSession,
) -> None:
    _lead(as_alpha_admin, first_name="Priya", last_name="Nair")

    result = _preview(
        as_alpha_admin,
        {"entity": "LEAD", "fields": ["first_name", "last_name", "status"]},
    )

    assert {column["key"] for column in result["columns"]} == {
        "first_name",
        "last_name",
        "status",
    }
    assert any(row["first_name"] == "Priya" for row in result["rows"])


def test_an_unknown_field_is_a_422_not_a_500(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        f"{REPORTS}/custom/preview",
        json={"definition": {"entity": "LEAD", "fields": ["not_a_real_field"]}},
    )

    assert response.status_code == 422, response.text


def test_a_row_listing_report_needs_at_least_one_field_or_a_group(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.post(
        f"{REPORTS}/custom/preview",
        json={"definition": {"entity": "LEAD", "fields": []}},
    )

    assert response.status_code == 422, response.text


# --- Grouped / aggregated reports --------------------------------------------


def test_a_grouped_report_matches_the_built_in_pipeline_by_stage(
    as_alpha_admin: ApiSession,
) -> None:
    """The same question the catalogue's own report answers, asked ad hoc."""
    account = _account(as_alpha_admin, "Aggregate Co")
    _deal(as_alpha_admin, name="Deal One", account_id=account, value="1000")
    _deal(as_alpha_admin, name="Deal Two", account_id=account, value="2500")

    result = _preview(
        as_alpha_admin,
        {
            "entity": "OPPORTUNITY",
            "group_by": "stage",
            "aggregations": [{"op": "COUNT"}, {"field": "deal_value", "op": "SUM"}],
            "chart_kind": "BAR",
        },
    )

    row = next(r for r in result["rows"] if r["group"] == "Qualification")
    assert row["all__count"] >= 2
    assert float(row["deal_value__sum"]) >= 3500.0
    assert result["chart"] == {
        "kind": "BAR",
        "category_key": "group",
        "value_key": "all__count",
    }


def test_a_grouped_report_needs_at_least_one_aggregation(
    as_alpha_admin: ApiSession,
) -> None:
    response = as_alpha_admin.post(
        f"{REPORTS}/custom/preview",
        json={"definition": {"entity": "OPPORTUNITY", "group_by": "stage", "aggregations": []}},
    )

    assert response.status_code == 422, response.text


def test_an_aggregation_illegal_for_the_fields_type_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    """``SUM`` over a text column ('stage') has no meaning."""
    response = as_alpha_admin.post(
        f"{REPORTS}/custom/preview",
        json={
            "definition": {
                "entity": "OPPORTUNITY",
                "group_by": "stage",
                "aggregations": [{"field": "stage", "op": "SUM"}],
            }
        },
    )

    assert response.status_code == 422, response.text


def test_group_by_interval_only_applies_to_a_date_field(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        f"{REPORTS}/custom/preview",
        json={
            "definition": {
                "entity": "OPPORTUNITY",
                "group_by": "stage",
                "group_by_interval": "month",
                "aggregations": [{"op": "COUNT"}],
            }
        },
    )

    assert response.status_code == 422, response.text


def test_revenue_by_month_groups_by_date_trunc(as_alpha_admin: ApiSession) -> None:
    """The trend the checkpoint asks for by name, produced generically."""
    account = _account(as_alpha_admin, "Trend Co")
    deal_id = _deal(as_alpha_admin, name="Trend Deal", account_id=account, value="5000")
    won = as_alpha_admin.post(
        f"/crm/opportunities/{deal_id}/stage",
        json={"stage_id": _stage_id(as_alpha_admin, "Closed Won")},
    )
    assert won.status_code == 200, won.text

    result = _preview(
        as_alpha_admin,
        {
            "entity": "OPPORTUNITY",
            "group_by": "won_at",
            "group_by_interval": "month",
            "filters": {
                "logic": "AND",
                "conditions": [{"field": "won_at", "operator": "is_not_empty"}],
            },
            "aggregations": [{"field": "deal_value", "op": "SUM"}],
        },
    )

    assert any(float(row["deal_value__sum"]) >= 5000.0 for row in result["rows"])
    assert all(
        column["type"] in ("DATE",) for column in result["columns"] if column["key"] == "group"
    )


# --- Filters: operators and AND/OR combination -------------------------------


def test_and_logic_requires_every_condition(as_alpha_admin: ApiSession) -> None:
    _lead(as_alpha_admin, first_name="Match", last_name="Both", status="CONTACTED")
    _lead(as_alpha_admin, first_name="Match", last_name="OnlyName")

    result = _preview(
        as_alpha_admin,
        {
            "entity": "LEAD",
            "fields": ["first_name", "last_name"],
            "filters": {
                "logic": "AND",
                "conditions": [
                    {"field": "first_name", "operator": "eq", "value": "Match"},
                    {"field": "status", "operator": "eq", "value": "CONTACTED"},
                ],
            },
        },
    )

    last_names = {row["last_name"] for row in result["rows"]}
    assert last_names == {"Both"}


def test_or_logic_matches_either_condition(as_alpha_admin: ApiSession) -> None:
    _lead(as_alpha_admin, first_name="Alpha", last_name="One")
    _lead(as_alpha_admin, first_name="Beta", last_name="Two")
    _lead(as_alpha_admin, first_name="Gamma", last_name="Three")

    result = _preview(
        as_alpha_admin,
        {
            "entity": "LEAD",
            "fields": ["first_name"],
            "filters": {
                "logic": "OR",
                "conditions": [
                    {"field": "first_name", "operator": "eq", "value": "Alpha"},
                    {"field": "first_name", "operator": "eq", "value": "Beta"},
                ],
            },
        },
    )

    names = {row["first_name"] for row in result["rows"]}
    assert names == {"Alpha", "Beta"}


def test_between_operator_narrows_a_numeric_range(as_alpha_admin: ApiSession) -> None:
    account = _account(as_alpha_admin, "Range Co")
    _deal(as_alpha_admin, name="Cheap", account_id=account, value="100")
    _deal(as_alpha_admin, name="Mid", account_id=account, value="500")
    _deal(as_alpha_admin, name="Expensive", account_id=account, value="9000")

    result = _preview(
        as_alpha_admin,
        {
            "entity": "OPPORTUNITY",
            "fields": ["name", "deal_value"],
            "filters": {
                "logic": "AND",
                "conditions": [
                    {"field": "deal_value", "operator": "between", "value": [200, 6000]}
                ],
            },
        },
    )

    names = {row["name"] for row in result["rows"]}
    assert "Mid" in names
    assert "Cheap" not in names
    assert "Expensive" not in names


def test_starts_with_and_ends_with(as_alpha_admin: ApiSession) -> None:
    _lead(as_alpha_admin, first_name="Zephyr", last_name="Industries")

    starts = _preview(
        as_alpha_admin,
        {
            "entity": "LEAD",
            "fields": ["last_name"],
            "filters": {
                "logic": "AND",
                "conditions": [{"field": "last_name", "operator": "starts_with", "value": "Indus"}],
            },
        },
    )
    ends = _preview(
        as_alpha_admin,
        {
            "entity": "LEAD",
            "fields": ["last_name"],
            "filters": {
                "logic": "AND",
                "conditions": [{"field": "last_name", "operator": "ends_with", "value": "ries"}],
            },
        },
    )

    assert any(row["last_name"] == "Industries" for row in starts["rows"])
    assert any(row["last_name"] == "Industries" for row in ends["rows"])


def test_relative_date_reuses_report_period_resolution(as_alpha_admin: ApiSession) -> None:
    """``{"relative": "TODAY"}`` must find a lead created moments ago."""
    _lead(as_alpha_admin, first_name="Fresh", last_name="Today")

    result = _preview(
        as_alpha_admin,
        {
            "entity": "LEAD",
            "fields": ["first_name"],
            "filters": {
                "logic": "AND",
                "conditions": [
                    {
                        "field": "created_at",
                        "operator": "eq",
                        "value": {"relative": "TODAY"},
                    }
                ],
            },
        },
    )

    assert any(row["first_name"] == "Fresh" for row in result["rows"])


def test_an_illegal_operator_for_the_column_type_is_refused(
    as_alpha_admin: ApiSession,
) -> None:
    """``contains`` on a currency figure has no meaning."""
    response = as_alpha_admin.post(
        f"{REPORTS}/custom/preview",
        json={
            "definition": {
                "entity": "OPPORTUNITY",
                "fields": ["name"],
                "filters": {
                    "logic": "AND",
                    "conditions": [{"field": "deal_value", "operator": "contains", "value": "5"}],
                },
            }
        },
    )

    assert response.status_code == 422, response.text


# --- Custom-field filters ------------------------------------------------------


def _custom_field(session: ApiSession, *, entity_type: str, api_name: str, field_type: str) -> None:
    created = session.post(
        "/crm/custom-fields",
        json={
            "entity_type": entity_type,
            "api_name": api_name,
            "label": api_name.replace("_", " ").title(),
            "field_type": field_type,
        },
    )
    assert created.status_code == 201, created.text


def test_a_custom_field_condition_filters_the_report(as_alpha_admin: ApiSession) -> None:
    _custom_field(as_alpha_admin, entity_type="LEAD", api_name="region", field_type="TEXT")
    matching = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Emea",
            "last_name": "Lead",
            "custom_fields": {"region": "EMEA"},
        },
    )
    assert matching.status_code == 201, matching.text
    as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Other",
            "last_name": "Lead",
            "custom_fields": {"region": "APAC"},
        },
    )

    result = _preview(
        as_alpha_admin,
        {
            "entity": "LEAD",
            "fields": ["first_name"],
            "filters": {
                "logic": "AND",
                "conditions": [{"field": "custom:region", "operator": "eq", "value": "EMEA"}],
            },
        },
    )

    names = {row["first_name"] for row in result["rows"]}
    assert "Emea" in names
    assert "Other" not in names


def test_an_unknown_custom_field_is_refused_at_run_time(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        f"{REPORTS}/custom/preview",
        json={
            "definition": {
                "entity": "LEAD",
                "fields": ["first_name"],
                "filters": {
                    "logic": "AND",
                    "conditions": [
                        {"field": "custom:no_such_field", "operator": "eq", "value": "x"}
                    ],
                },
            }
        },
    )

    assert response.status_code == 422, response.text


# --- Available fields ---------------------------------------------------------


def test_available_fields_includes_custom_fields(as_alpha_admin: ApiSession) -> None:
    _custom_field(
        as_alpha_admin, entity_type="OPPORTUNITY", api_name="deal_tier", field_type="TEXT"
    )

    response = as_alpha_admin.get(f"{REPORTS}/custom/fields", params={"entity": "OPPORTUNITY"})

    assert response.status_code == 200, response.text
    fields = response.json()
    keys = {field["key"] for field in fields}
    assert "deal_value" in keys
    assert "custom:deal_tier" in keys
    custom_entry = next(f for f in fields if f["key"] == "custom:deal_tier")
    assert custom_entry["is_custom"] is True


def test_activities_have_no_custom_fields(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get(f"{REPORTS}/custom/fields", params={"entity": "ACTIVITY"})

    assert response.status_code == 200, response.text
    assert all(not field["is_custom"] for field in response.json())


# --- Authorization and record visibility --------------------------------------


async def test_a_custom_report_requires_view_on_its_entitys_module(
    session_factory: async_sessionmaker[AsyncSession],
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    """No ``reports`` permission exists — the entity's own ``VIEW`` is it,
    exactly as it is for the built-in catalogue (see ``test_reports.py``'s
    identical assertion for ``/{key}/run``)."""
    membership_id = await membership_id_for(session_factory, alpha.member.user_id)
    async with session_factory() as db:
        await db.execute(
            sql("DELETE FROM platform.membership_roles WHERE membership_id = :membership"),
            {"membership": membership_id},
        )
        await db.commit()
    await grant_custom_role(
        session_factory,
        organization_id=alpha.organization_id,
        membership_id=membership_id,
        codes=["leads.VIEW"],
        name="Leads only (custom reports)",
    )

    session = ApiSession(client, integration_settings.api_prefix)
    session.login(alpha.member.email, organization_id=alpha.organization_id)

    permitted = session.post(
        f"{REPORTS}/custom/preview",
        json={"definition": {"entity": "LEAD", "fields": ["first_name"]}},
    )
    refused = session.post(
        f"{REPORTS}/custom/preview",
        json={"definition": {"entity": "OPPORTUNITY", "fields": ["name"]}},
    )

    assert permitted.status_code == 200, permitted.text
    assert refused.status_code == 403


def test_a_rep_and_a_manager_see_different_totals(rep: ApiSession, manager: ApiSession) -> None:
    """The phase gate, for the ad-hoc engine — same as the catalogue's own."""
    rep_account = _account(rep, "Rep Custom Ltd")
    _deal(rep, name="Rep Deal", account_id=rep_account, value="1000")
    manager_account = _account(manager, "Manager Custom Ltd")
    _deal(manager, name="Manager Deal", account_id=manager_account, value="4000")

    rep_result = _preview(
        rep,
        {
            "entity": "OPPORTUNITY",
            "group_by": "stage",
            "aggregations": [{"field": "deal_value", "op": "SUM"}],
        },
    )
    manager_result = _preview(
        manager,
        {
            "entity": "OPPORTUNITY",
            "group_by": "stage",
            "aggregations": [{"field": "deal_value", "op": "SUM"}],
        },
    )

    rep_total = sum(float(row["deal_value__sum"]) for row in rep_result["rows"])
    manager_total = sum(float(row["deal_value__sum"]) for row in manager_result["rows"])

    assert rep_total < manager_total
    assert rep_total >= 1000.0


# --- Save / edit / run / delete -----------------------------------------------


def test_a_custom_report_can_be_saved_and_run(as_alpha_admin: ApiSession) -> None:
    _lead(as_alpha_admin, first_name="Saved", last_name="Custom")

    created = as_alpha_admin.post(
        f"{REPORTS}/saved",
        json={
            "name": "My custom leads",
            "period": "ALL_TIME",
            "visibility": "PRIVATE",
            "custom_definition": {
                "entity": "LEAD",
                "fields": ["first_name", "last_name"],
            },
        },
    )
    assert created.status_code == 201, created.text
    saved_id = created.json()["id"]
    assert created.json()["base_report_key"] is None

    run = as_alpha_admin.post(f"{REPORTS}/saved/{saved_id}/run")
    assert run.status_code == 200, run.text
    assert any(row["first_name"] == "Saved" for row in run.json()["rows"])


def test_saving_requires_exactly_one_definition(as_alpha_admin: ApiSession) -> None:
    both = as_alpha_admin.post(
        f"{REPORTS}/saved",
        json={
            "name": "Bad report",
            "period": "ALL_TIME",
            "visibility": "PRIVATE",
            "base_report_key": "pipeline-by-stage",
            "custom_definition": {"entity": "LEAD", "fields": ["first_name"]},
        },
    )
    neither = as_alpha_admin.post(
        f"{REPORTS}/saved",
        json={"name": "Bad report 2", "period": "ALL_TIME", "visibility": "PRIVATE"},
    )

    assert both.status_code == 422, both.text
    assert neither.status_code == 422, neither.text


def test_a_custom_reports_kind_cannot_be_changed_by_patch(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post(
        f"{REPORTS}/saved",
        json={
            "name": "Kind-locked report",
            "period": "ALL_TIME",
            "visibility": "PRIVATE",
            "custom_definition": {"entity": "LEAD", "fields": ["first_name"]},
        },
    )
    assert created.status_code == 201, created.text
    saved_id = created.json()["id"]

    changed = as_alpha_admin.patch(
        f"{REPORTS}/saved/{saved_id}", json={"base_report_key": "lead-funnel"}
    )

    assert changed.status_code == 409, changed.text
