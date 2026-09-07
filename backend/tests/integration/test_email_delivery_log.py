"""The administrator-facing delivery log: `GET /api/v1/email-deliveries`.

Read-only, gated on ``audit.VIEW``, and scoped to the caller's organization.
The interesting cases are the three ways a log like this leaks:

* **across tenants** — one organization reading another's recipients;
* **past the gate** — a member with CRM access reading who was emailed;
* **into the tenant from below** — the untenanted password-reset rows
  appearing in somebody's log because the endpoint forgot its organization.

The third is specific to this table and is the reason the policy is NULL-aware
(``app.platform.email.models``). It is tested here as well as in
``test_password_reset.py`` because the two ask different questions: that file
asks whether the *policy* hides the row, this one asks whether the *endpoint*
does.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.platform.email.models import EmailDelivery, EmailDeliveryStatus
from tests.integration.conftest import ApiSession, Tenant, scope_session_to

pytestmark = pytest.mark.integration

DELIVERIES = "/email-deliveries"


@pytest_asyncio.fixture(autouse=True)
async def clean_deliveries(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    async def wipe() -> None:
        async with session_factory() as session:
            await session.execute(text("DELETE FROM platform.email_deliveries"))
            await session.commit()

    await wipe()
    yield
    await wipe()


async def _seed(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    organization_id: uuid.UUID | None,
    to_address: str,
    template: str = "invitation",
    status: EmailDeliveryStatus = EmailDeliveryStatus.SENT,
    error: str | None = None,
) -> uuid.UUID:
    """Write one delivery row directly, as the worker would."""
    async with session_factory() as session:
        if organization_id is not None:
            await scope_session_to(session, organization_id)
        delivery = EmailDelivery(
            organization_id=organization_id,
            to_address=to_address,
            subject=f"Subject for {to_address}",
            template=template,
            provider="stub",
            status=status,
            error=error,
            sent_at=dt.datetime.now(dt.UTC)
            if status is EmailDeliveryStatus.SENT
            else None,
        )
        session.add(delivery)
        await session.commit()
        return delivery.id


# --- What an administrator sees ---------------------------------------------


async def test_an_administrator_sees_their_organizations_mail(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(
        session_factory,
        organization_id=alpha.organization_id,
        to_address="recruit@example.com",
    )

    listed = as_alpha_admin.get(DELIVERIES)
    assert listed.status_code == 200, listed.text

    body = listed.json()
    assert body["pagination"]["total"] == 1
    row = body["data"][0]
    assert row["to_address"] == "recruit@example.com"
    assert row["status"] == "SENT"
    assert row["provider"] == "stub"
    # The absent field is the point: storing a body would put an invitation
    # link — a bearer credential — where administrators can read it.
    assert "text_body" not in row
    assert "body" not in row


async def test_a_failure_says_why(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """"Failed" with no reason leaves an administrator nothing to act on."""
    await _seed(
        session_factory,
        organization_id=alpha.organization_id,
        to_address="bounced@example.com",
        status=EmailDeliveryStatus.FAILED,
        error="SMTPRecipientsRefused: 550 unknown mailbox",
    )

    row = as_alpha_admin.get(DELIVERIES).json()["data"][0]
    assert row["status"] == "FAILED"
    assert "550 unknown mailbox" in row["error"]


async def test_filters_are_applied_in_sql_not_in_the_browser(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The total has to describe the same set as the page.

    A client-side filter over one page would leave the count naming a
    different set than the rows beneath it — which is how "showing 25 of 4"
    happens.
    """
    await _seed(
        session_factory,
        organization_id=alpha.organization_id,
        to_address="sent@example.com",
    )
    await _seed(
        session_factory,
        organization_id=alpha.organization_id,
        to_address="failed@example.com",
        status=EmailDeliveryStatus.FAILED,
        error="boom",
    )
    await _seed(
        session_factory,
        organization_id=alpha.organization_id,
        to_address="reminder@example.com",
        template="meeting_reminder",
    )

    by_status = as_alpha_admin.get(f"{DELIVERIES}?status=FAILED").json()
    assert by_status["pagination"]["total"] == 1
    assert by_status["data"][0]["to_address"] == "failed@example.com"

    by_template = as_alpha_admin.get(f"{DELIVERIES}?template=meeting_reminder").json()
    assert by_template["pagination"]["total"] == 1

    by_recipient = as_alpha_admin.get(f"{DELIVERIES}?to_address=FAIL").json()
    assert by_recipient["pagination"]["total"] == 1, (
        "recipient search should be case-insensitive"
    )


async def test_the_summary_counts_every_state_including_the_empty_ones(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A summary that omits FAILED when nothing failed reads like a bug.

    "No failures" and "failures were not counted" must not look the same.
    """
    await _seed(
        session_factory,
        organization_id=alpha.organization_id,
        to_address="one@example.com",
    )

    summary = as_alpha_admin.get(f"{DELIVERIES}/summary")
    assert summary.status_code == 200, summary.text

    body = summary.json()
    assert body["counts"] == {"PENDING": 0, "SENT": 1, "FAILED": 0, "SUPPRESSED": 0}
    assert body["templates"] == ["invitation"]


# --- The three ways it could leak -------------------------------------------


async def test_one_organization_cannot_read_anothers_recipients(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    beta: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Tenant isolation, asserted on the endpoint rather than the policy.

    The recipient list is a customer list. RLS filters underneath and the
    repository filters explicitly on top; this proves the pair of them from
    outside.
    """
    await _seed(
        session_factory, organization_id=alpha.organization_id, to_address="mine@example.com"
    )
    await _seed(
        session_factory, organization_id=beta.organization_id, to_address="theirs@example.com"
    )

    body = as_alpha_admin.get(DELIVERIES).json()

    addresses = {row["to_address"] for row in body["data"]}
    assert addresses == {"mine@example.com"}
    assert body["pagination"]["total"] == 1, (
        "the count leaked the other tenant's rows"
    )


async def test_a_member_without_audit_view_is_refused(
    as_alpha_member: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The log names everyone this organization has emailed.

    That is not something a CRM seat should carry by default — the seeded
    *User* role holds CRM modules only.
    """
    await _seed(
        session_factory, organization_id=alpha.organization_id, to_address="private@example.com"
    )

    refused = as_alpha_member.get(DELIVERIES)
    assert refused.status_code == 403, refused.text


async def test_untenanted_deliveries_never_appear_in_a_tenants_log(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A password reset is not this organization's mail.

    It is addressed to a global identity, so the row carries no organization
    and must stay out of every tenant's view — including the view belonging to
    the organization the person happens to be a member of. An administrator
    who could see it would learn that a colleague is recovering their account,
    which is between that person and the product.
    """
    await _seed(
        session_factory,
        organization_id=None,
        to_address=alpha.member.email,
        template="password_reset",
    )
    await _seed(
        session_factory,
        organization_id=alpha.organization_id,
        to_address="ordinary@example.com",
    )

    body = as_alpha_admin.get(DELIVERIES).json()

    assert body["pagination"]["total"] == 1
    assert {row["to_address"] for row in body["data"]} == {"ordinary@example.com"}

    summary = as_alpha_admin.get(f"{DELIVERIES}/summary").json()
    assert summary["counts"]["SENT"] == 1
    assert "password_reset" not in summary["templates"]


# --- Ordering and paging ----------------------------------------------------


async def test_an_unknown_sort_column_falls_back_rather_than_failing(
    as_alpha_admin: ApiSession,
    alpha: Tenant,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The allow-list exists so a stranger cannot choose a slow query.

    Rejecting with a 500 would be worse than ignoring it: the sort is a
    convenience, and an ORDER BY on an unindexed column over a growing log is
    the thing being prevented.
    """
    await _seed(
        session_factory, organization_id=alpha.organization_id, to_address="a@example.com"
    )

    listed = as_alpha_admin.get(f"{DELIVERIES}?sort_by=error;DROP")
    assert listed.status_code == 200, listed.text
    assert listed.json()["pagination"]["total"] == 1
