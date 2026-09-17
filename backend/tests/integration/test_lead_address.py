"""A lead's structured address (Checkpoint 9 — Zoho field/layout parity).

Leads had no address columns before this checkpoint; accounts and contacts
already did (`address_line1`, `city`, `state`, `postal_code`, `country`). This
is the minimal round-trip proof that the new columns are real, writable
through both create and update, and travel through the response the way every
other built-in column does — the generic `TenantScopedService` write path that
carries them needs no dedicated wiring, but the new columns themselves were
never exercised by a test until now.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import ApiSession

pytestmark = pytest.mark.integration


def test_an_address_is_stored_on_create_and_returned(as_alpha_admin: ApiSession) -> None:
    response = as_alpha_admin.post(
        "/crm/leads",
        json={
            "first_name": "Priya",
            "last_name": "Nair",
            "address_line1": "221B Baker Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India",
        },
    )
    assert response.status_code == 201, response.text
    lead = response.json()
    assert lead["address_line1"] == "221B Baker Street"
    assert lead["city"] == "Bengaluru"
    assert lead["state"] == "Karnataka"
    assert lead["postal_code"] == "560001"
    assert lead["country"] == "India"

    fetched = as_alpha_admin.get(f"/crm/leads/{lead['id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["city"] == "Bengaluru"


def test_an_address_can_be_set_and_cleared_on_update(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post(
        "/crm/leads", json={"first_name": "Arjun", "last_name": "Rao"}
    )
    assert created.status_code == 201, created.text
    lead_id = created.json()["id"]
    assert created.json()["address_line1"] is None

    updated = as_alpha_admin.patch(
        f"/crm/leads/{lead_id}", json={"city": "Pune", "country": "India"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["city"] == "Pune"
    assert updated.json()["country"] == "India"

    cleared = as_alpha_admin.patch(f"/crm/leads/{lead_id}", json={"city": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["city"] is None
    # A field not mentioned in the patch is left alone.
    assert cleared.json()["country"] == "India"
