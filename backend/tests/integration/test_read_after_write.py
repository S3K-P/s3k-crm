"""A write is durable by the time the client is told it succeeded.

This is the one guarantee an API implies without ever stating: if ``POST``
returns 201, the record is there. Getting it wrong does not look like a bug —
it looks like "the list sometimes doesn't refresh", it happens more under load,
and it is invisible to any test that does not deliberately look.

**The defect these tests pin.** FastAPI keeps two exit stacks per request, and
a dependency with ``yield`` lands on the *request* stack by default — closed
after ``await response(...)``, which is after the response bytes have gone to
the client. The session dependency's ``COMMIT`` therefore ran after the caller
had already been told the write succeeded. A client reading back immediately
could race it. ``app.core.database.DbSession`` declares ``scope="function"``,
which moves the close to the stack that is drained *before* the response is
sent.

The first test asserts the property. The second asserts the mechanism, because
the property is timing-dependent enough that it could pass by luck on a fast
machine — and a future FastAPI upgrade that changed the default would flip the
mechanism silently while the timing test stayed green for months.
"""

from __future__ import annotations

import pytest
from fastapi import Depends
from fastapi.params import Depends as DependsParam

from app.core.database import DbSession, get_db_session
from tests.integration.conftest import ApiSession

pytestmark = pytest.mark.integration


def test_a_created_record_is_visible_to_the_very_next_read(
    as_alpha_admin: ApiSession,
) -> None:
    """POST, then GET, with nothing in between.

    Repeated, because a commit-after-response race is a race: one round trip
    could pass on a quiet machine while the defect is fully present.
    """
    for index in range(25):
        created = as_alpha_admin.post(
            "/crm/accounts?allow_duplicate=true", json={"name": f"Read-after-write {index}"}
        )
        assert created.status_code == 201, created.text

        fetched = as_alpha_admin.get(f"/crm/accounts/{created.json()['id']}")
        assert fetched.status_code == 200, (
            "A record was not readable immediately after its own creation "
            "returned 201 — the transaction is committing after the response."
        )


def test_a_mutation_is_visible_in_the_next_list(as_alpha_admin: ApiSession) -> None:
    """The flow the UI actually performs: mutate, then refetch the list.

    A stale list here is what a user reports as "I saved it and it disappeared".
    """
    for index in range(15):
        name = f"Refetch {index}"
        created = as_alpha_admin.post(
            "/crm/accounts?allow_duplicate=true", json={"name": name}
        )
        assert created.status_code == 201

        listed = as_alpha_admin.get(f"/crm/accounts?search={name}").json()["data"]
        assert [item["name"] for item in listed] == [name], (
            "A newly created record was missing from the list read immediately "
            "after creating it."
        )


def test_an_update_is_visible_to_the_very_next_read(as_alpha_admin: ApiSession) -> None:
    created = as_alpha_admin.post(
        "/crm/accounts?allow_duplicate=true", json={"name": "Before"}
    ).json()

    for index in range(15):
        expected = f"After {index}"
        patched = as_alpha_admin.patch(
            f"/crm/accounts/{created['id']}", json={"name": expected}
        )
        assert patched.status_code == 200

        fetched = as_alpha_admin.get(f"/crm/accounts/{created['id']}")
        assert fetched.json()["name"] == expected, (
            "A read immediately after an update saw the previous value."
        )


def test_a_delete_is_visible_to_the_very_next_read(as_alpha_admin: ApiSession) -> None:
    for index in range(15):
        created = as_alpha_admin.post(
            "/crm/accounts?allow_duplicate=true", json={"name": f"Doomed {index}"}
        ).json()
        assert as_alpha_admin.delete(f"/crm/accounts/{created['id']}").status_code == 204
        assert as_alpha_admin.get(f"/crm/accounts/{created['id']}").status_code == 404, (
            "A record was still readable immediately after its deletion returned 204."
        )


def test_the_session_dependency_closes_before_the_response_is_sent() -> None:
    """The mechanism, asserted directly.

    ``scope="function"`` is what puts the session on the exit stack FastAPI
    drains *before* sending the response. Without it the default is the request
    stack, drained after — and every test above would go back to passing or
    failing on timing rather than on correctness.

    Checked here rather than trusted to a comment because it is a single
    keyword argument on one line, it has no visible effect in development, and
    nothing else in the suite would notice its removal.
    """
    marker = DbSession.__metadata__[0]
    assert isinstance(marker, DependsParam)
    assert marker.dependency is get_db_session
    assert marker.scope == "function", (
        "The database session must be declared with scope='function' so its "
        "COMMIT runs before the response is sent. Without it a client that "
        "reads back immediately after a write can observe the state from "
        "before its own change."
    )


def test_the_default_dependency_scope_is_still_the_late_one() -> None:
    """Guards the *reason* the keyword above is needed.

    If a future FastAPI made ``function`` the default, ``scope="function"``
    would become redundant and somebody would eventually remove it — correctly.
    If instead the meaning of the keyword changed, this fails and says so
    before the guarantee is quietly lost.
    """
    assert Depends(get_db_session).scope is None, (
        "FastAPI's default dependency scope has changed. Re-check that "
        "app.core.database.DbSession still commits before the response is sent."
    )
