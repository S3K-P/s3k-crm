"""Administrator app enablement, and the line it must not cross.

``PUT /products/apps/{code}/enablement`` is the only write the products module
exposes, and it exists in tension with ADR-011: entitlements are provisioned,
never self-served, precisely so an administrator cannot license their own
organization. What makes this endpoint safe is that it can only ever **narrow**
a grant that already exists.

So the tests that matter most here are the refusals:

* turning an app off blocks it in the **API**, not just the interface;
* an app the organization was never granted cannot be turned on, and the
  attempt creates nothing;
* one tenant's switch does not touch another's;
* an ordinary member cannot reach the switch at all.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.core.config import Settings
from tests.integration.conftest import ApiSession, Tenant

pytestmark = pytest.mark.integration

CRM_CODE = "s3k-crm"
#: A real catalogue row that no organization is entitled to. Using a code that
#: exists is deliberate: it proves the refusal comes from the missing
#: entitlement rather than from an unknown product.
UNLICENSED_CODE = "s3k-finance"


def _set_enabled(session: ApiSession, code: str, *, enabled: bool) -> Response:
    return session.request(
        "PUT", f"/products/apps/{code}/enablement", json={"enabled": enabled}
    )


# --- The launcher's view ----------------------------------------------------


def test_the_app_list_reports_the_crm_open_and_everything_else_coming_soon(
    as_alpha_admin: ApiSession,
) -> None:
    """One server-side verdict per app, which the UI renders rather than derives."""
    response = as_alpha_admin.get("/products/apps")

    assert response.status_code == 200
    by_code = {row["code"]: row for row in response.json()}
    assert by_code[CRM_CODE]["state"] == "OPEN"
    assert by_code[CRM_CODE]["route"] == "/dashboard"
    assert by_code[UNLICENSED_CODE]["state"] == "COMING_SOON"


def test_an_app_that_is_not_open_carries_no_route(
    as_alpha_admin: ApiSession,
) -> None:
    """A client that ignores ``state`` still has nowhere wrong to send anybody."""
    rows = as_alpha_admin.get("/products/apps").json()

    for row in rows:
        if row["state"] != "OPEN":
            assert row["route"] is None


def test_an_ordinary_member_can_still_see_which_apps_the_organization_has(
    as_alpha_member: ApiSession,
) -> None:
    """Membership, not a permission.

    Gating this on an admin permission would mean an ordinary user could not be
    told why a page is missing.
    """
    response = as_alpha_member.get("/products/apps")

    assert response.status_code == 200
    assert any(row["code"] == CRM_CODE for row in response.json())


# --- Turning an app off is a real control -----------------------------------


def test_turning_the_crm_off_blocks_its_api_not_just_its_navigation(
    as_alpha_admin: ApiSession,
) -> None:
    """The requirement Phase 8 states outright: hiding the UI is not enough."""
    assert as_alpha_admin.get("/crm/leads").status_code == 200

    disabled = _set_enabled(as_alpha_admin, CRM_CODE, enabled=False)
    assert disabled.status_code == 200

    refused = as_alpha_admin.get("/crm/leads")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "product_not_licensed"


def test_turning_the_crm_back_on_restores_access(
    as_alpha_admin: ApiSession,
) -> None:
    """Narrowing is reversible; that is what makes it not a revocation."""
    _set_enabled(as_alpha_admin, CRM_CODE, enabled=False)
    assert as_alpha_admin.get("/crm/leads").status_code == 403

    _set_enabled(as_alpha_admin, CRM_CODE, enabled=True)

    assert as_alpha_admin.get("/crm/leads").status_code == 200


def test_a_disabled_app_reports_disabled_rather_than_unlicensed(
    as_alpha_admin: ApiSession,
) -> None:
    """The admin screen has to be able to tell the two apart to offer it back."""
    _set_enabled(as_alpha_admin, CRM_CODE, enabled=False)

    row = next(
        item
        for item in as_alpha_admin.get("/products/apps").json()
        if item["code"] == CRM_CODE
    )

    assert row["state"] == "DISABLED"
    # Still licensed — the organization holds the grant, it is merely switched
    # off. Reporting NOT_LICENSED here would send an administrator to sales for
    # something they can fix themselves.
    assert row["entitled"] is True
    assert row["enabled"] is False


def test_one_organizations_switch_does_not_affect_another(
    as_alpha_admin: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    beta: Tenant,
) -> None:
    """Enablement is tenant data, and is scoped like all of it.

    Beta gets its **own** session rather than the shared ``api`` fixture: that
    fixture and ``as_alpha_admin`` are the same object, so reusing it would
    silently re-authenticate alpha's session instead of opening a second one.
    """
    _set_enabled(as_alpha_admin, CRM_CODE, enabled=False)

    beta_admin = ApiSession(client, integration_settings.api_prefix)
    beta_admin.login(beta.admin.email)

    assert beta_admin.get("/crm/leads").status_code == 200


# --- The escalation it must refuse ------------------------------------------


def test_an_app_the_organization_was_never_granted_cannot_be_turned_on(
    as_alpha_admin: ApiSession,
) -> None:
    """The ADR-011 boundary, attacked from the one write this module exposes.

    404 rather than 403 because there is nothing there — and, crucially, the
    call creates nothing, so a caller cannot bootstrap a licence by toggling.
    """
    response = _set_enabled(as_alpha_admin, UNLICENSED_CODE, enabled=True)

    assert response.status_code == 404

    apps = {row["code"]: row for row in as_alpha_admin.get("/products/apps").json()}
    assert apps[UNLICENSED_CODE]["entitled"] is False
    assert apps[UNLICENSED_CODE]["state"] == "COMING_SOON"


def test_a_product_code_that_does_not_exist_is_refused_the_same_way(
    as_alpha_admin: ApiSession,
) -> None:
    """No oracle: a made-up code and an unlicensed real one answer identically."""
    response = _set_enabled(as_alpha_admin, "s3k-not-a-product", enabled=True)

    assert response.status_code == 404


def test_an_ordinary_member_cannot_change_app_enablement(
    as_alpha_member: ApiSession,
) -> None:
    """Gated on ``organizations.EDIT``, which only Admin holds."""
    response = _set_enabled(as_alpha_member, CRM_CODE, enabled=False)

    assert response.status_code == 403


def test_a_member_cannot_disable_the_crm_for_everyone_else(
    as_alpha_member: ApiSession,
    client: TestClient,
    integration_settings: Settings,
    alpha: Tenant,
) -> None:
    """The refusal above has to be effective, not merely a status code.

    The administrator is a second, independent session for the reason given in
    ``test_one_organizations_switch_does_not_affect_another``: taking both
    ``as_alpha_member`` and ``as_alpha_admin`` yields one session logged in
    twice, and the member's request would be made as the administrator.
    """
    _set_enabled(as_alpha_member, CRM_CODE, enabled=False)

    admin = ApiSession(client, integration_settings.api_prefix)
    admin.login(alpha.admin.email)

    assert admin.get("/crm/leads").status_code == 200


def test_changing_enablement_requires_authentication(
    api: ApiSession,
) -> None:
    response = _set_enabled(api, CRM_CODE, enabled=False)

    assert response.status_code == 401
