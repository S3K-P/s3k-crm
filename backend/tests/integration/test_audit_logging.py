"""The audit trail, end to end against real PostgreSQL.

Split into the questions an auditor would actually ask of it:

**Is it recording?** Every create, update and delete, the CRM state transitions
that matter, and the authentication and access-control events — proven by
performing the action over HTTP and then reading the trail back over HTTP,
never by calling the audit service directly. A trail that only works when
poked by a test is not a trail.

**Can it be trusted?** Append-only is asserted against the database, as an
ordinary RLS-subject role, because a guarantee enforced only in Python is not
one. So is tenant isolation, which is checked twice — once through the API and
once in raw SQL with the application removed from the picture.

**Is it safe?** Passwords, hashes and tokens must be absent from the payloads
of exactly those events where they were in scope at the call site.

**Is it usable?** Filters, pagination and sorting, since a two-year trail
nobody can search is only nominally a compliance control.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.core.models import TENANT_SETTING
from app.core.request_context import REQUEST_ID_HEADER
from app.core.schema_audit import (
    TABLE_POLICY_SQL,
    TABLE_SECURITY_SQL,
    TENANT_COLUMN,
    audit_tenant_isolation,
    build_table_security,
    format_findings,
)
from app.platform.audit.models import APPEND_ONLY_TRIGGER
from app.platform.audit.redaction import REDACTED
from tests.integration.conftest import TEST_PASSWORD, ApiSession, Tenant

pytestmark = pytest.mark.integration

PLATFORM_SCHEMA = "platform"
AUDIT_TABLE = "audit_logs"

#: A role with neither BYPASSRLS nor table ownership — an application role, in
#: other words. The local development superuser ignores every policy, so
#: asserting isolation as that role would pass while proving nothing.
TEST_ROLE = "s3k_audit_probe_role"


# --- Helpers ----------------------------------------------------------------


def _entries(session: ApiSession, **params: object) -> list[dict[str, Any]]:
    """Read the trail over HTTP, the way the admin screen does."""
    response = session.get("/audit-logs", params=params)
    assert response.status_code == 200, response.text
    data: list[dict[str, Any]] = response.json()["data"]
    return data


def _actions(session: ApiSession, **params: object) -> list[str]:
    return [entry["action"] for entry in _entries(session, **params)]


def _only(entries: list[dict[str, Any]], action: str) -> dict[str, Any]:
    """The single entry for ``action``, failing loudly on none or several."""
    matching = [entry for entry in entries if entry["action"] == action]
    assert len(matching) == 1, f"expected exactly one {action}, got {len(matching)}"
    return matching[0]


@pytest.fixture
def as_alpha_manager(api: ApiSession, alpha: Tenant) -> ApiSession:
    """A Manager: full CRM control, and deliberately no ``audit.VIEW``."""
    api.login(alpha.manager.email, organization_id=alpha.organization_id)
    return api


@pytest.fixture
def as_beta_admin(client: TestClient, integration_settings: Settings, beta: Tenant) -> ApiSession:
    """A second organization's administrator, for the isolation tests."""
    session = ApiSession(client, integration_settings.api_prefix)
    session.login(beta.admin.email, organization_id=beta.organization_id)
    return session


@pytest_asyncio.fixture
async def owner_engine(integration_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(integration_settings.database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def tenant_engine(
    owner_engine: AsyncEngine, integration_settings: Settings
) -> AsyncIterator[AsyncEngine]:
    """An engine connected as an ordinary, RLS-subject, non-owning role."""
    # token_hex is [0-9a-f] only, so inlining it into DDL is injection-safe.
    # CREATE ROLE is DDL and cannot take bind parameters.
    password = secrets.token_hex(24)

    async with owner_engine.begin() as connection:
        await connection.execute(text(f"DROP ROLE IF EXISTS {TEST_ROLE}"))
        await connection.execute(
            text(
                f"CREATE ROLE {TEST_ROLE} LOGIN PASSWORD '{password}' "
                "NOSUPERUSER NOBYPASSRLS"
            )
        )
        await connection.execute(text(f"GRANT USAGE ON SCHEMA platform TO {TEST_ROLE}"))
        await connection.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON platform.audit_logs "
                f"TO {TEST_ROLE}"
            )
        )

    url = make_url(integration_settings.database_url).set(
        username=TEST_ROLE, password=password
    )
    engine = create_async_engine(url)
    try:
        yield engine
    finally:
        await engine.dispose()
        async with owner_engine.begin() as connection:
            await connection.execute(
                text(f"REVOKE ALL ON platform.audit_logs FROM {TEST_ROLE}")
            )
            await connection.execute(text(f"REVOKE USAGE ON SCHEMA platform FROM {TEST_ROLE}"))
            await connection.execute(text(f"DROP ROLE IF EXISTS {TEST_ROLE}"))


# =============================================================================
# Is it recording?
# =============================================================================


def test_creating_a_record_is_audited(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post("/crm/accounts", json={"name": "Audited Ltd"})
    assert created.status_code == 201
    account_id = created.json()["id"]

    entry = _only(_entries(as_alpha_admin, module="accounts"), "CREATED")

    assert entry["entity_type"] == "ACCOUNT"
    assert entry["entity_id"] == account_id
    assert entry["entity_label"] == "Audited Ltd"
    assert entry["status"] == "SUCCESS"
    assert entry["actor_id"] is not None
    assert entry["details"]["values"]["name"] == "Audited Ltd"


def test_an_update_records_a_field_level_diff(as_alpha_admin: ApiSession) -> None:
    """Both sides, so "who changed it *from* what" is answerable."""
    account_id = as_alpha_admin.post(
        "/crm/accounts", json={"name": "Diffed Ltd", "industry": "Retail"}
    ).json()["id"]

    as_alpha_admin.patch(f"/crm/accounts/{account_id}", json={"industry": "Manufacturing"})

    entry = _only(_entries(as_alpha_admin, module="accounts"), "UPDATED")
    changes = entry["details"]["changes"]

    assert changes == {"industry": {"from": "Retail", "to": "Manufacturing"}}


def test_an_update_that_changes_nothing_records_nothing(
    as_alpha_admin: ApiSession,
) -> None:
    """A save button pressed twice must not produce two records.

    Without this the trail fills with entries that describe no change, and the
    edits that did happen become impossible to find.
    """
    account_id = as_alpha_admin.post(
        "/crm/accounts", json={"name": "Idempotent Ltd", "industry": "Retail"}
    ).json()["id"]

    as_alpha_admin.patch(f"/crm/accounts/{account_id}", json={"industry": "Retail"})

    assert "UPDATED" not in _actions(as_alpha_admin, module="accounts")


def test_deleting_a_record_is_audited(as_alpha_admin: ApiSession) -> None:
    account_id = as_alpha_admin.post("/crm/accounts", json={"name": "Doomed Ltd"}).json()["id"]

    assert as_alpha_admin.delete(f"/crm/accounts/{account_id}").status_code == 204

    entry = _only(_entries(as_alpha_admin, module="accounts"), "DELETED")

    assert entry["entity_id"] == account_id
    # The label is captured at write time, so the trail still names the record
    # after it has been archived out of the list screens.
    assert entry["entity_label"] == "Doomed Ltd"
    assert entry["details"]["soft"] is True


def test_every_crm_module_writes_through_the_same_hook(
    as_alpha_admin: ApiSession,
) -> None:
    """The reason auditing lives in ``TenantScopedService`` rather than in each
    controller: a module that forgot to call it would be invisible here.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Coverage Ltd"})
    as_alpha_admin.post("/crm/contacts", json={"first_name": "Ada", "last_name": "Lovelace"})
    as_alpha_admin.post("/crm/leads", json={"first_name": "Alan", "last_name": "Turing"})
    as_alpha_admin.post("/crm/lead-sources", json={"name": "Referral"})

    modules = {entry["module"] for entry in _entries(as_alpha_admin, action="CREATED")}

    assert {"accounts", "contacts", "leads", "lead_sources"} <= modules


def test_a_lead_status_change_is_its_own_action(as_alpha_admin: ApiSession) -> None:
    """Not buried in a generic UPDATE: pipeline movement is what gets reviewed."""
    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Grace", "last_name": "Hopper"}
    ).json()["id"]

    as_alpha_admin.post(f"/crm/leads/{lead_id}/status", json={"status": "CONTACTED"})

    entry = _only(_entries(as_alpha_admin, module="leads"), "LEAD_STATUS_CHANGED")

    assert entry["details"]["from"] == "NEW"
    assert entry["details"]["to"] == "CONTACTED"
    assert entry["entity_id"] == lead_id


def test_lead_conversion_is_audited_with_everything_it_created(
    as_alpha_admin: ApiSession,
) -> None:
    """Conversion writes three records in one transaction; this ties them together."""
    lead_id = as_alpha_admin.post(
        "/crm/leads",
        json={"first_name": "Grace", "last_name": "Hopper", "company": "Hopper Systems"},
    ).json()["id"]
    for status in ("CONTACTED", "QUALIFIED"):
        as_alpha_admin.post(f"/crm/leads/{lead_id}/status", json={"status": status})

    converted = as_alpha_admin.post(f"/crm/leads/{lead_id}/convert", json={}).json()

    entry = _only(_entries(as_alpha_admin, module="leads"), "LEAD_CONVERTED")

    assert entry["details"]["account_id"] == converted["account_id"]
    assert entry["details"]["contact_id"] == converted["contact_id"]
    assert entry["details"]["opportunity_id"] == converted["opportunity_id"]


def test_an_opportunity_stage_change_is_audited(as_alpha_admin: ApiSession) -> None:
    stages = as_alpha_admin.get("/crm/opportunities/stages").json()
    account_id = as_alpha_admin.post("/crm/accounts", json={"name": "Deal Co"}).json()["id"]
    opportunity_id = as_alpha_admin.post(
        "/crm/opportunities",
        json={"name": "Big Deal", "account_id": account_id, "stage_id": stages[0]["id"]},
    ).json()["id"]

    moved = as_alpha_admin.post(
        f"/crm/opportunities/{opportunity_id}/stage", json={"stage_id": stages[1]["id"]}
    )
    assert moved.status_code == 200, moved.text

    entry = _only(
        _entries(as_alpha_admin, module="opportunities"), "OPPORTUNITY_STAGE_CHANGED"
    )

    assert entry["details"]["to_stage_id"] == stages[1]["id"]
    assert entry["details"]["from_stage_id"] == stages[0]["id"]


# --- Authentication and access control --------------------------------------


def test_a_successful_sign_in_is_audited(as_alpha_admin: ApiSession) -> None:
    entry = _only(_entries(as_alpha_admin, module="auth"), "LOGIN_SUCCEEDED")

    assert entry["status"] == "SUCCESS"
    assert entry["entity_type"] == "USER"
    assert entry["ip_address"] is not None


def test_a_rejected_sign_in_survives_the_rollback_that_follows_it(
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    as_alpha_admin: ApiSession,
) -> None:
    """The case that makes out-of-band writing necessary.

    A rejected sign-in raises, which rolls the request transaction back. An
    audit record written inside that transaction would be discarded with it —
    so failed sign-ins, the single most important thing an audit trail records,
    would be the one class of event it never captured.
    """
    rejected = client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={"email": alpha.member.email, "password": "wrong-password-entirely"},
    )
    assert rejected.status_code == 401

    entry = _only(_entries(as_alpha_admin, action="LOGIN_FAILED"), "LOGIN_FAILED")

    assert entry["status"] == "FAILURE"
    assert entry["details"]["reason"] == "bad_password"
    assert entry["entity_label"] == alpha.member.email


def test_signing_out_is_audited(as_alpha_admin: ApiSession) -> None:
    assert as_alpha_admin.post("/auth/logout").status_code == 204

    assert "LOGOUT" in _actions(as_alpha_admin, module="auth")


def test_granting_a_role_is_audited_with_what_it_grants(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """"Who gave this person Admin?" is the question this answers."""
    members = as_alpha_admin.get("/organizations/current/members").json()["data"]
    member = next(m for m in members if m["user_id"] == str(alpha.member.user_id))
    roles = as_alpha_admin.get("/roles").json()
    admin_role = next(role for role in roles if role["name"] == "Admin")

    granted = as_alpha_admin.post(
        "/roles/assignments",
        json={"membership_id": member["id"], "role_id": admin_role["id"]},
    )
    assert granted.status_code == 204, granted.text

    entry = _only(_entries(as_alpha_admin, module="roles"), "ROLE_ASSIGNED")

    assert entry["entity_label"] == "Admin"
    assert entry["details"]["membership_id"] == member["id"]
    # The permissions are resolved at write time, so the record still says what
    # the grant conferred even if the role is edited afterwards.
    assert "audit.VIEW" in entry["details"]["permissions"]


def test_revoking_a_role_is_audited(as_alpha_admin: ApiSession, alpha: Tenant) -> None:
    members = as_alpha_admin.get("/organizations/current/members").json()["data"]
    member = next(m for m in members if m["user_id"] == str(alpha.member.user_id))
    user_role = next(role for role in member["role_details"] if role["name"] == "User")

    revoked = as_alpha_admin.post(
        "/roles/assignments/revoke",
        json={"membership_id": member["id"], "role_id": user_role["id"]},
    )
    assert revoked.status_code == 204, revoked.text

    assert "ROLE_REVOKED" in _actions(as_alpha_admin, module="roles")


def test_suspending_a_member_is_audited_with_both_statuses(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Suspension cuts access on the very next request, with no in-app trace.

    The trail is where the person and their administrator find out why.
    """
    suspended = as_alpha_admin.post(
        f"/organizations/current/members/{alpha.member.user_id}/status",
        json={"status": "SUSPENDED"},
    )
    assert suspended.status_code == 200, suspended.text

    entry = _only(_entries(as_alpha_admin, action="MEMBER_STATUS_CHANGED"), "MEMBER_STATUS_CHANGED")

    assert entry["details"]["from"] == "ACTIVE"
    assert entry["details"]["to"] == "SUSPENDED"
    assert entry["entity_id"] == str(alpha.member.user_id)


def test_provisioning_a_user_is_audited(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post(
        "/organizations/current/users",
        json={
            "email": "newcomer@alpha.example",
            "first_name": "New",
            "last_name": "Comer",
            "password": TEST_PASSWORD,
        },
    )
    assert created.status_code == 201, created.text

    actions = _actions(as_alpha_admin, module="users")

    assert "USER_PROVISIONED" in actions
    assert "MEMBER_ADDED" in actions


def test_an_administrator_resetting_a_password_is_audited_against_them(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """Taking over an account must name the person who did it, not just the subject."""
    reset = as_alpha_admin.post(
        f"/organizations/current/members/{alpha.member.user_id}/reset-password",
        json={"new_password": "An0therStr0ngPass!"},
    )
    assert reset.status_code == 204, reset.text

    entry = _only(
        _entries(as_alpha_admin, action="PASSWORD_RESET_BY_ADMIN"),
        "PASSWORD_RESET_BY_ADMIN",
    )

    assert entry["actor_id"] == str(alpha.admin.user_id)
    assert entry["entity_id"] == str(alpha.member.user_id)


def test_a_record_carries_the_request_correlation_id(
    client: TestClient, integration_settings: Settings, as_alpha_admin: ApiSession
) -> None:
    """So a trail entry can be joined to the application logs for that request."""
    correlation = str(uuid.uuid4())

    # Driven through the raw client: ``ApiSession`` supplies its own headers,
    # and this test is specifically about adding one to them.
    created = client.post(
        f"{integration_settings.api_prefix}/crm/accounts",
        json={"name": "Correlated Ltd"},
        headers={**as_alpha_admin.headers(), REQUEST_ID_HEADER: correlation},
    )
    assert created.status_code == 201, created.text

    entry = _only(_entries(as_alpha_admin, module="accounts"), "CREATED")

    assert entry["request_id"] == correlation


# =============================================================================
# Is it safe? — nothing sensitive is captured
# =============================================================================


def test_a_failed_sign_in_stores_no_trace_of_the_password(
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    as_alpha_admin: ApiSession,
) -> None:
    """The attempted password is in scope at the call site and must not survive.

    A wrong password is very often a *right* password for another system, so
    capturing it would turn the audit screen into a credential harvest.
    """
    attempted = "TotallyWr0ngPassword!"
    client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={"email": alpha.member.email, "password": attempted},
    )

    trail = str(_entries(as_alpha_admin))

    assert attempted not in trail


def test_a_successful_sign_in_stores_no_credential(
    as_alpha_admin: ApiSession,
) -> None:
    trail = str(_entries(as_alpha_admin, module="auth"))

    assert TEST_PASSWORD not in trail
    assert "argon2" not in trail


def test_a_password_reset_stores_no_password(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    replacement = "Repl4cementPass!"
    as_alpha_admin.post(
        f"/organizations/current/members/{alpha.member.user_id}/reset-password",
        json={"new_password": replacement},
    )

    trail = str(_entries(as_alpha_admin, action="PASSWORD_RESET_BY_ADMIN"))

    assert replacement not in trail


def test_a_password_change_records_the_event_without_either_password(
    client: TestClient,
    integration_settings: Settings,
    as_alpha_admin: ApiSession,
    alpha: Tenant,
) -> None:
    """Both the old and the new password are in scope at the call site here.

    Read back by a *second* administrator, because changing a password revokes
    every session the account holds — including the one that made the change,
    which is the intended behaviour and not something to work around.
    """
    roles = as_alpha_admin.get("/roles").json()
    admin_role = next(role for role in roles if role["name"] == "Admin")
    provisioned = as_alpha_admin.post(
        "/organizations/current/users",
        json={
            "email": "second.admin@alpha.example",
            "first_name": "Second",
            "last_name": "Admin",
            "password": TEST_PASSWORD,
            "role_id": admin_role["id"],
        },
    )
    assert provisioned.status_code == 201, provisioned.text

    replacement = "Ch4ngedItMyself!"
    changed = as_alpha_admin.post(
        "/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": replacement},
    )
    assert changed.status_code == 204, changed.text

    observer = ApiSession(client, integration_settings.api_prefix)
    observer.login("second.admin@alpha.example", organization_id=alpha.organization_id)
    entries = _entries(observer, action="PASSWORD_CHANGED")

    assert len(entries) == 1
    assert entries[0]["actor_id"] == str(alpha.admin.user_id)
    assert replacement not in str(entries)
    assert TEST_PASSWORD not in str(entries)


def test_free_text_bodies_are_summarised_rather_than_copied(
    as_alpha_admin: ApiSession,
) -> None:
    """A private note must not be reproduced into a permanent, admin-readable table.

    The *fact* of the change is still auditable — length plus a digest — which
    is what an investigator needs without the trail becoming a second copy of
    everyone's notes.
    """
    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Quiet", "last_name": "Lead"}
    ).json()["id"]
    confidential = "Contract blocked: their counsel is threatening litigation."

    as_alpha_admin.patch(f"/crm/leads/{lead_id}", json={"notes": confidential})

    entry = _only(_entries(as_alpha_admin, module="leads"), "UPDATED")
    recorded = entry["details"]["changes"]["notes"]["to"]

    assert confidential not in str(entry)
    assert recorded.startswith("<text:")
    assert "sha256:" in recorded


def test_an_email_in_a_diff_is_masked(as_alpha_admin: ApiSession) -> None:
    """Doc 13: email is PII, masked in audit logs. The domain survives."""
    contact_id = as_alpha_admin.post(
        "/crm/contacts",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@analytical.example"},
    ).json()["id"]

    as_alpha_admin.patch(f"/crm/contacts/{contact_id}", json={"email": "ada.l@analytical.example"})

    entry = _only(_entries(as_alpha_admin, module="contacts"), "UPDATED")
    change = entry["details"]["changes"]["email"]

    assert change["from"] == "a***@analytical.example"
    assert change["to"] == "a***@analytical.example"
    assert "ada.l@analytical.example" not in str(entry)


def test_provisioning_a_user_stores_no_trace_of_the_initial_password(
    as_alpha_admin: ApiSession,
) -> None:
    """An administrator sets the first password; the trail records the account,
    not the credential."""
    as_alpha_admin.post(
        "/organizations/current/users",
        json={
            "email": "secretive@alpha.example",
            "first_name": "Secret",
            "last_name": "Ive",
            "password": "N0tInTheTrail!",
        },
    )

    entry = _only(_entries(as_alpha_admin, module="users"), "USER_PROVISIONED")

    assert "N0tInTheTrail!" not in str(entry)
    # The account is still identifiable — over-redaction would leave a record
    # that cannot answer which user was created.
    assert entry["entity_label"] == "secretive@alpha.example"
    assert REDACTED not in str(entry["details"])


# =============================================================================
# Can it be trusted? — authorization
# =============================================================================


def test_an_unauthenticated_caller_cannot_read_the_trail(
    client: TestClient, integration_settings: Settings
) -> None:
    response = client.get(f"{integration_settings.api_prefix}/audit-logs")

    assert response.status_code == 401


def test_an_ordinary_member_cannot_read_the_trail(as_alpha_member: ApiSession) -> None:
    """The User role holds CRM permissions and no ``audit.VIEW``."""
    response = as_alpha_member.get("/audit-logs")

    assert response.status_code == 403


def test_a_manager_cannot_read_the_trail(as_alpha_manager: ApiSession) -> None:
    """Deliberate: Manager runs the pipeline, and the trail records *their* actions too.

    ``_manager_permissions`` grants the CRM modules plus ``users.VIEW`` and
    ``organizations.VIEW`` — not ``audit.VIEW``. If this ever starts passing,
    somebody has widened the Manager template and the separation between the
    people being audited and the people reading the audit has gone.
    """
    response = as_alpha_manager.get("/audit-logs")

    assert response.status_code == 403


def test_an_administrator_can_read_the_trail(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.get("/audit-logs")

    assert response.status_code == 200
    assert "data" in response.json()


def test_a_member_cannot_read_a_single_entry_either(
    client: TestClient,
    integration_settings: Settings,
    as_alpha_admin: ApiSession,
    alpha: Tenant,
) -> None:
    """The detail route is gated identically — no unprotected side door.

    The member signs in on their own :class:`ApiSession` rather than through
    the shared ``as_alpha_member`` fixture: both fixtures wrap the *same*
    session object, so requesting them together would have the second login
    overwrite the first token and quietly test one principal twice.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Peeked At Ltd"})
    entry_id = _entries(as_alpha_admin)[0]["id"]

    member = ApiSession(client, integration_settings.api_prefix)
    member.login(alpha.member.email, organization_id=alpha.organization_id)

    assert member.get(f"/audit-logs/{entry_id}").status_code == 403


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("POST", ""), ("PATCH", "/{id}"), ("DELETE", "/{id}"), ("PUT", "/{id}")],
)
def test_the_api_offers_no_way_to_write_to_the_trail(
    as_alpha_admin: ApiSession, method: str, suffix: str
) -> None:
    """Not even an administrator gets a write route, because none exists.

    405 (or 404 for an unrouted path) rather than 403: the point is that the
    operation is absent from the API surface, not merely unauthorized.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Immutable Ltd"})
    entry_id = _entries(as_alpha_admin)[0]["id"]
    path = "/audit-logs" + suffix.format(id=entry_id)

    response = as_alpha_admin.request(method, path, json={"action": "TAMPERED"})

    assert response.status_code in (404, 405), response.text


# =============================================================================
# Can it be trusted? — tenant isolation
# =============================================================================


def test_an_administrator_sees_only_their_own_organizations_trail(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Alpha Only Ltd"})
    as_beta_admin.post("/crm/accounts", json={"name": "Beta Only Ltd"})

    alpha_labels = {entry["entity_label"] for entry in _entries(as_alpha_admin)}
    beta_labels = {entry["entity_label"] for entry in _entries(as_beta_admin)}

    assert "Alpha Only Ltd" in alpha_labels
    assert "Beta Only Ltd" not in alpha_labels
    assert "Beta Only Ltd" in beta_labels
    assert "Alpha Only Ltd" not in beta_labels


def test_every_row_returned_carries_the_callers_own_organization(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession, alpha: Tenant
) -> None:
    """Stronger than checking the labels: no foreign row appears at all."""
    as_beta_admin.post("/crm/accounts", json={"name": "Beta Noise Ltd"})
    as_alpha_admin.post("/crm/accounts", json={"name": "Alpha Ltd"})

    organizations = {entry["organization_id"] for entry in _entries(as_alpha_admin)}

    assert organizations == {str(alpha.organization_id)}


def test_another_tenants_entry_id_is_not_found_rather_than_forbidden(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """403 would confirm the id is real, which is itself a disclosure."""
    as_beta_admin.post("/crm/accounts", json={"name": "Beta Secret Ltd"})
    beta_entry_id = _entries(as_beta_admin)[0]["id"]

    response = as_alpha_admin.get(f"/audit-logs/{beta_entry_id}")

    assert response.status_code == 404


def test_filtering_by_another_tenants_entity_id_returns_nothing(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """A filter is applied *on top of* the organization predicate, never instead."""
    beta_account_id = as_beta_admin.post(
        "/crm/accounts", json={"name": "Beta Target Ltd"}
    ).json()["id"]

    assert _entries(as_alpha_admin, entity_id=beta_account_id) == []


def test_filtering_by_another_tenants_actor_returns_nothing(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession, beta: Tenant
) -> None:
    as_beta_admin.post("/crm/accounts", json={"name": "Beta Actor Ltd"})

    assert _entries(as_alpha_admin, actor_id=str(beta.admin.user_id)) == []


def test_the_filter_options_do_not_describe_another_tenants_activity(
    as_alpha_admin: ApiSession, as_beta_admin: ApiSession
) -> None:
    """Even the dropdown contents are tenant data: which actions an
    organization has performed says something about it."""
    beta_lead_id = as_beta_admin.post(
        "/crm/leads", json={"first_name": "Beta", "last_name": "Lead"}
    ).json()["id"]
    as_beta_admin.post(f"/crm/leads/{beta_lead_id}/status", json={"status": "CONTACTED"})

    options = as_alpha_admin.get("/audit-logs/filters").json()

    assert "LEAD_STATUS_CHANGED" not in options["actions"]
    assert "LEAD" not in options["entity_types"]


async def test_the_audit_table_passes_the_rls_schema_audit(
    owner_engine: AsyncEngine,
) -> None:
    """The catalogue half: the policy is present, forced and scoped correctly.

    ``platform.audit_logs`` holds tenant data as surely as any ``crm`` table,
    so it is held to the same discovered-not-listed standard
    (:mod:`app.core.schema_audit`).
    """
    async with owner_engine.connect() as connection:
        tables = (
            (
                await connection.execute(
                    TABLE_SECURITY_SQL,
                    {"schema": PLATFORM_SCHEMA, "column": TENANT_COLUMN},
                )
            )
            .mappings()
            .all()
        )
        policies = (
            (await connection.execute(TABLE_POLICY_SQL, {"schema": PLATFORM_SCHEMA}))
            .mappings()
            .all()
        )

    discovered = {
        table.name: table
        for table in build_table_security(PLATFORM_SCHEMA, tables, policies)
    }
    audit_logs = discovered.get(AUDIT_TABLE)

    assert audit_logs is not None, "platform.audit_logs does not exist"
    assert audit_logs.rls_enabled and audit_logs.rls_forced

    findings = audit_tenant_isolation((audit_logs,), exemptions={})

    assert not findings, format_findings(findings)


async def test_rls_denies_a_cross_tenant_read_with_the_application_removed(
    tenant_engine: AsyncEngine, alpha: Tenant, beta: Tenant, as_alpha_admin: ApiSession
) -> None:
    """The behavioural half, in raw SQL as an ordinary role.

    A policy can be present and still be wrong; a catalogue query cannot tell.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Isolated Ltd"})

    async with tenant_engine.connect() as connection:
        await connection.execute(
            text("SELECT set_config(:setting, :value, false)"),
            {"setting": TENANT_SETTING, "value": str(beta.organization_id)},
        )
        visible = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM platform.audit_logs "
                    "WHERE organization_id = :organization_id"
                ),
                {"organization_id": alpha.organization_id},
            )
        ).scalar_one()

    assert visible == 0


async def test_rls_denies_writing_a_record_into_another_tenant(
    tenant_engine: AsyncEngine, alpha: Tenant, beta: Tenant
) -> None:
    """``WITH CHECK`` matters as much as ``USING``: a forged entry attributed to
    another organization would let one tenant plant evidence in another's trail.
    """
    async with tenant_engine.connect() as connection, connection.begin():
        await connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": str(beta.organization_id)},
        )
        with pytest.raises(DBAPIError):
            await connection.execute(
                text(
                    "INSERT INTO platform.audit_logs "
                    "(organization_id, action, module) "
                    "VALUES (:organization_id, 'FORGED', 'auth')"
                ),
                {"organization_id": alpha.organization_id},
            )


async def test_an_unscoped_connection_sees_no_records_at_all(
    tenant_engine: AsyncEngine, as_alpha_admin: ApiSession
) -> None:
    """Fail closed: no tenant context must mean no rows, never all rows."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Unscoped Probe Ltd"})

    async with tenant_engine.connect() as connection:
        visible = (
            await connection.execute(text("SELECT count(*) FROM platform.audit_logs"))
        ).scalar_one()

    assert visible == 0


# =============================================================================
# Can it be trusted? — immutability
# =============================================================================


async def test_an_application_role_cannot_update_a_record(
    tenant_engine: AsyncEngine, alpha: Tenant, as_alpha_admin: ApiSession
) -> None:
    """The guarantee that makes the table evidence rather than a log.

    Enforced by a trigger rather than by withholding an RLS policy, because
    RLS is ignored entirely by superusers and ``BYPASSRLS`` roles.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Tamper Target Ltd"})

    async with tenant_engine.connect() as connection, connection.begin():
        await connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": str(alpha.organization_id)},
        )
        with pytest.raises(DBAPIError, match="append-only"):
            await connection.execute(
                text("UPDATE platform.audit_logs SET action = 'REWRITTEN'")
            )


async def test_an_application_role_cannot_delete_a_record(
    tenant_engine: AsyncEngine, alpha: Tenant, as_alpha_admin: ApiSession
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Delete Target Ltd"})

    async with tenant_engine.connect() as connection, connection.begin():
        await connection.execute(
            text("SELECT set_config(:setting, :value, true)"),
            {"setting": TENANT_SETTING, "value": str(alpha.organization_id)},
        )
        with pytest.raises(DBAPIError, match="append-only"):
            await connection.execute(text("DELETE FROM platform.audit_logs"))


async def test_even_the_table_owner_cannot_rewrite_a_record(
    owner_engine: AsyncEngine, as_alpha_admin: ApiSession
) -> None:
    """The role the application connects as in development is a superuser.

    RLS would not apply to it at all, so if immutability rested on policies
    this would silently succeed. The trigger is what makes it fail.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Owner Tamper Ltd"})

    async with owner_engine.connect() as connection, connection.begin():
        with pytest.raises(DBAPIError, match="append-only"):
            await connection.execute(
                text("UPDATE platform.audit_logs SET action = 'REWRITTEN'")
            )


async def test_the_table_cannot_be_truncated(
    owner_engine: AsyncEngine, as_alpha_admin: ApiSession
) -> None:
    """TRUNCATE fires no row-level trigger and would empty the whole trail."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Truncate Target Ltd"})

    async with owner_engine.connect() as connection, connection.begin():
        with pytest.raises(DBAPIError, match="append-only"):
            await connection.execute(text("TRUNCATE platform.audit_logs"))


async def test_both_append_only_triggers_are_attached(owner_engine: AsyncEngine) -> None:
    """Guards the guard: a dropped trigger would make every test above vacuous.

    They are asserted by name because the integration fixture disables one of
    them to clean between tests — if the re-enable were ever removed, the
    checks would still "pass" against an unprotected table.
    """
    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT tgname, tgenabled FROM pg_trigger "
                    "WHERE tgrelid = 'platform.audit_logs'::regclass "
                    "AND NOT tgisinternal"
                )
            )
        ).all()

    # ``pg_trigger.tgenabled`` is PostgreSQL's internal ``"char"`` type, which
    # asyncpg hands back as a single byte rather than as ``str``.
    triggers = {name: enabled.decode() for name, enabled in rows}

    assert APPEND_ONLY_TRIGGER in triggers
    assert f"{APPEND_ONLY_TRIGGER}_truncate" in triggers
    # 'O' is "enabled, origin" — the normal state. 'D' would mean the cleanup
    # fixture left it switched off.
    assert set(triggers.values()) == {"O"}


# =============================================================================
# Is it usable? — filtering, pagination, sorting
# =============================================================================


def test_filtering_by_action_narrows_the_result(as_alpha_admin: ApiSession) -> None:
    account_id = as_alpha_admin.post("/crm/accounts", json={"name": "Filtered Ltd"}).json()["id"]
    as_alpha_admin.patch(f"/crm/accounts/{account_id}", json={"industry": "Mining"})

    assert set(_actions(as_alpha_admin, action="UPDATED")) == {"UPDATED"}


def test_filtering_by_entity_returns_one_records_whole_history(
    as_alpha_admin: ApiSession,
) -> None:
    """The "what happened to this record?" query the composite index serves."""
    account_id = as_alpha_admin.post("/crm/accounts", json={"name": "Traced Ltd"}).json()["id"]
    as_alpha_admin.patch(f"/crm/accounts/{account_id}", json={"industry": "Mining"})
    as_alpha_admin.delete(f"/crm/accounts/{account_id}")
    as_alpha_admin.post("/crm/accounts", json={"name": "Unrelated Ltd"})

    entries = _entries(as_alpha_admin, entity_type="ACCOUNT", entity_id=account_id)

    assert {entry["action"] for entry in entries} == {"CREATED", "UPDATED", "DELETED"}
    assert all(entry["entity_id"] == account_id for entry in entries)


def test_filtering_by_actor_returns_only_that_persons_actions(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "By Admin Ltd"})

    entries = _entries(as_alpha_admin, actor_id=str(alpha.admin.user_id))

    assert entries
    assert all(entry["actor_id"] == str(alpha.admin.user_id) for entry in entries)


def test_filtering_by_status_isolates_the_failures(
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
    as_alpha_admin: ApiSession,
) -> None:
    """"Show me everything that failed" — the first query after an incident."""
    client.post(
        f"{integration_settings.api_prefix}/auth/login",
        json={"email": alpha.member.email, "password": "definitely-not-it"},
    )

    entries = _entries(as_alpha_admin, status="FAILURE")

    assert entries
    assert all(entry["status"] == "FAILURE" for entry in entries)


def test_a_date_range_excludes_everything_outside_it(
    as_alpha_admin: ApiSession,
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Dated Ltd"})

    in_future = _entries(as_alpha_admin, occurred_from="2099-01-01T00:00:00Z")
    up_to_past = _entries(as_alpha_admin, occurred_to="2000-01-01T00:00:00Z")
    spanning = _entries(
        as_alpha_admin,
        occurred_from="2000-01-01T00:00:00Z",
        occurred_to="2099-01-01T00:00:00Z",
    )

    assert in_future == []
    assert up_to_past == []
    assert spanning


def test_pagination_splits_the_trail_without_losing_or_repeating_rows(
    as_alpha_admin: ApiSession,
) -> None:
    for index in range(7):
        as_alpha_admin.post("/crm/accounts", json={"name": f"Paged {index} Ltd"})

    first = as_alpha_admin.get(
        "/audit-logs", params={"action": "CREATED", "page": 1, "page_size": 3}
    ).json()
    second = as_alpha_admin.get(
        "/audit-logs", params={"action": "CREATED", "page": 2, "page_size": 3}
    ).json()

    assert first["pagination"]["total"] == 7
    assert first["pagination"]["total_pages"] == 3
    assert first["pagination"]["has_more"] is True
    assert len(first["data"]) == 3
    assert len(second["data"]) == 3

    first_ids = {entry["id"] for entry in first["data"]}
    second_ids = {entry["id"] for entry in second["data"]}

    assert not (first_ids & second_ids), "a row appeared on two pages"


def test_the_last_page_reports_that_there_is_no_more(
    as_alpha_admin: ApiSession,
) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Only One Ltd"})

    page = as_alpha_admin.get(
        "/audit-logs", params={"action": "CREATED", "page": 1, "page_size": 25}
    ).json()

    assert page["pagination"]["has_more"] is False


def test_the_trail_reads_newest_first_by_default(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "Older Ltd"})
    as_alpha_admin.post("/crm/accounts", json={"name": "Newer Ltd"})

    labels = [entry["entity_label"] for entry in _entries(as_alpha_admin, action="CREATED")]

    assert labels[:2] == ["Newer Ltd", "Older Ltd"]


def test_sorting_can_be_reversed(as_alpha_admin: ApiSession) -> None:
    as_alpha_admin.post("/crm/accounts", json={"name": "First Ltd"})
    as_alpha_admin.post("/crm/accounts", json={"name": "Second Ltd"})

    labels = [
        entry["entity_label"]
        for entry in _entries(
            as_alpha_admin, action="CREATED", sort_by="created_at", sort_dir="asc"
        )
    ]

    assert labels[:2] == ["First Ltd", "Second Ltd"]


def test_an_unknown_sort_column_falls_back_instead_of_reaching_the_query(
    as_alpha_admin: ApiSession,
) -> None:
    """``sort_by`` arrives from the query string and is resolved against an
    allow-list, so an unknown or hostile value cannot influence the SQL."""
    as_alpha_admin.post("/crm/accounts", json={"name": "Safely Sorted Ltd"})

    response = as_alpha_admin.get(
        "/audit-logs", params={"sort_by": "details; DROP TABLE platform.audit_logs"}
    )

    assert response.status_code == 200
    assert response.json()["data"]


def test_an_oversized_page_is_rejected_rather_than_served(
    as_alpha_admin: ApiSession,
) -> None:
    """The trail is the largest table in the schema; unbounded reads are a DoS."""
    response = as_alpha_admin.get("/audit-logs", params={"page_size": 5000})

    assert response.status_code == 422


def test_the_filter_options_describe_this_organizations_own_trail(
    as_alpha_admin: ApiSession,
) -> None:
    lead_id = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Filter", "last_name": "Source"}
    ).json()["id"]
    as_alpha_admin.post(f"/crm/leads/{lead_id}/status", json={"status": "CONTACTED"})

    options = as_alpha_admin.get("/audit-logs/filters").json()

    assert "LEAD_STATUS_CHANGED" in options["actions"]
    assert "LEAD" in options["entity_types"]
    assert set(options["statuses"]) == {"SUCCESS", "FAILURE", "DENIED"}
    assert options["recording_since"] is not None


def test_an_entry_resolves_its_actor_to_a_person(
    as_alpha_admin: ApiSession, alpha: Tenant
) -> None:
    """``actor_id`` alone is unreadable; the screen needs a name and address.

    Joined at read time rather than copied into the row, so a renamed user does
    not leave the trail quoting a stale identity.
    """
    as_alpha_admin.post("/crm/accounts", json={"name": "Attributed Ltd"})

    entry = _only(_entries(as_alpha_admin, module="accounts"), "CREATED")

    assert entry["actor_email"] == alpha.admin.email
    assert entry["actor_name"]
