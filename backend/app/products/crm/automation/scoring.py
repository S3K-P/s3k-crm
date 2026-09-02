"""Lead, contact and account scores, derived from facts already in the database.

Three rules this module holds itself to, because a score nobody trusts is worse
than no score:

* **Every score explains itself.** A number with no breakdown cannot be argued
  with, and a rep who disagrees with it and cannot see why simply stops looking
  at it. Each scorer returns its components alongside the total.
* **Nothing subjective is presented as fact.** These are weighted sums of
  observable things — is there an email address, has anybody called, is there
  open pipeline. They are called scores, not predictions, and no automation
  makes a decision on them.
* **The inputs are already true.** Nothing here invents data. It reads columns
  the CRM already maintains, which is what keeps a score reproducible: run it
  twice on unchanged data and it gives the same answer.

The weights are constants at the top of each scorer rather than configuration.
That is a deliberate first cut: a tenant-tunable weighting is a real feature,
and shipping the untunable version first means the numbers are comparable
across tenants while the model is still being judged.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.accounts.models import Account, AccountStatus
from app.products.crm.activities.models import Activity, ActivityStatus
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.opportunities.models import Opportunity

#: A record is "recently touched" if something happened within this window.
RECENT_ACTIVITY_DAYS = 30

#: An account with no activity for this long is a candidate for AT_RISK.
STALE_ACCOUNT_DAYS = 90


@dataclass(slots=True)
class Score:
    """A total plus the reasons for it."""

    value: int
    components: dict[str, int] = field(default_factory=dict)

    def add(self, reason: str, points: int) -> None:
        if points:
            self.components[reason] = self.components.get(reason, 0) + points
            self.value += points

    def clamp(self, low: int = 0, high: int = 100) -> Score:
        self.value = max(low, min(high, self.value))
        return self


#: Lead scoring weights. Contactability first, because a lead nobody can reach
#: is not a lead; then qualification progress, which is the strongest signal
#: there is; then engagement.
LEAD_WEIGHTS: dict[str, int] = {
    "has_email": 15,
    "has_phone": 10,
    "has_company": 10,
    "status_contacted": 10,
    "status_qualified": 30,
    "recent_activity": 15,
    "expected_deal_size": 10,
    # Negative: a source that produces nothing is worth knowing about, and a
    # score that can only go up ranks everything equally after a while.
    "no_contact_details": -20,
}


async def score_lead(session: AsyncSession, lead: Lead) -> Score:
    """Rank one lead by how workable it is.

    Deliberately not a probability. It answers "which of these should I call
    first", which is the question a rep actually has, and it is honest about
    being a heuristic.
    """
    score = Score(value=0)

    if lead.email:
        score.add("has_email", LEAD_WEIGHTS["has_email"])
    if lead.phone:
        score.add("has_phone", LEAD_WEIGHTS["has_phone"])
    if not lead.email and not lead.phone:
        score.add("no_contact_details", LEAD_WEIGHTS["no_contact_details"])
    if lead.company:
        score.add("has_company", LEAD_WEIGHTS["has_company"])

    if lead.status is LeadStatus.CONTACTED:
        score.add("status_contacted", LEAD_WEIGHTS["status_contacted"])
    elif lead.status is LeadStatus.QUALIFIED:
        score.add("status_qualified", LEAD_WEIGHTS["status_qualified"])

    if lead.expected_deal_size and lead.expected_deal_size > 0:
        score.add("expected_deal_size", LEAD_WEIGHTS["expected_deal_size"])

    if await _has_recent_activity(session, CrmEntityType.LEAD, lead.id, lead.organization_id):
        score.add("recent_activity", LEAD_WEIGHTS["recent_activity"])

    return score.clamp()


CONTACT_WEIGHTS: dict[str, int] = {
    "has_email": 20,
    "has_phone": 15,
    "has_account": 20,
    "has_job_title": 10,
    "recent_activity": 20,
    "on_open_opportunity": 15,
}


async def score_contact(session: AsyncSession, contact: Contact) -> Score:
    """Rank a contact by how reachable and how commercially involved they are."""
    score = Score(value=0)

    if contact.email:
        score.add("has_email", CONTACT_WEIGHTS["has_email"])
    if contact.phone or contact.mobile:
        score.add("has_phone", CONTACT_WEIGHTS["has_phone"])
    if contact.account_id:
        score.add("has_account", CONTACT_WEIGHTS["has_account"])
    if contact.job_title:
        score.add("has_job_title", CONTACT_WEIGHTS["has_job_title"])

    if await _has_recent_activity(
        session, CrmEntityType.CONTACT, contact.id, contact.organization_id
    ):
        score.add("recent_activity", CONTACT_WEIGHTS["recent_activity"])

    open_deals = await session.execute(
        select(func.count())
        .select_from(Opportunity)
        .where(
            Opportunity.organization_id == contact.organization_id,
            Opportunity.primary_contact_id == contact.id,
            Opportunity.deleted_at.is_(None),
            Opportunity.won_at.is_(None),
            Opportunity.lost_at.is_(None),
        )
    )
    if int(open_deals.scalar_one()) > 0:
        score.add("on_open_opportunity", CONTACT_WEIGHTS["on_open_opportunity"])

    return score.clamp()


ACCOUNT_WEIGHTS: dict[str, int] = {
    "base": 50,
    "open_pipeline": 20,
    "won_history": 15,
    "recent_activity": 15,
    "has_contacts": 10,
    "no_activity_90_days": -30,
    "lost_recently": -15,
}


async def score_account_health(session: AsyncSession, account: Account) -> Score:
    """How healthy this customer relationship looks.

    Starts at a neutral 50 rather than 0, because an account with no signal
    either way is not unhealthy — it is unknown, and scoring it zero would put
    a brand-new customer alongside one that just churned.
    """
    score = Score(value=0)
    score.add("base", ACCOUNT_WEIGHTS["base"])

    open_value = await session.execute(
        select(func.coalesce(func.sum(Opportunity.deal_value), 0)).where(
            Opportunity.organization_id == account.organization_id,
            Opportunity.account_id == account.id,
            Opportunity.deleted_at.is_(None),
            Opportunity.won_at.is_(None),
            Opportunity.lost_at.is_(None),
        )
    )
    if float(open_value.scalar_one() or 0) > 0:
        score.add("open_pipeline", ACCOUNT_WEIGHTS["open_pipeline"])

    won = await session.execute(
        select(func.count())
        .select_from(Opportunity)
        .where(
            Opportunity.organization_id == account.organization_id,
            Opportunity.account_id == account.id,
            Opportunity.deleted_at.is_(None),
            Opportunity.won_at.is_not(None),
        )
    )
    if int(won.scalar_one()) > 0:
        score.add("won_history", ACCOUNT_WEIGHTS["won_history"])

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=STALE_ACCOUNT_DAYS)
    recent_lost = await session.execute(
        select(func.count())
        .select_from(Opportunity)
        .where(
            Opportunity.organization_id == account.organization_id,
            Opportunity.account_id == account.id,
            Opportunity.deleted_at.is_(None),
            Opportunity.lost_at.is_not(None),
            Opportunity.lost_at >= cutoff,
        )
    )
    if int(recent_lost.scalar_one()) > 0:
        score.add("lost_recently", ACCOUNT_WEIGHTS["lost_recently"])

    contacts = await session.execute(
        select(func.count())
        .select_from(Contact)
        .where(
            Contact.organization_id == account.organization_id,
            Contact.account_id == account.id,
            Contact.deleted_at.is_(None),
        )
    )
    if int(contacts.scalar_one()) > 0:
        score.add("has_contacts", ACCOUNT_WEIGHTS["has_contacts"])

    if await _has_recent_activity(
        session, CrmEntityType.ACCOUNT, account.id, account.organization_id
    ):
        score.add("recent_activity", ACCOUNT_WEIGHTS["recent_activity"])
    elif await _is_stale(session, account):
        score.add("no_activity_90_days", ACCOUNT_WEIGHTS["no_activity_90_days"])

    return score.clamp()


def health_to_status(score: int, current: AccountStatus) -> AccountStatus:
    """Suggest a status from a health score, without overriding a human.

    ``ONBOARDING`` and ``CHURNED`` are left alone: both are decisions somebody
    made about the relationship, and a score has no business overruling either.
    The only automatic move is between ACTIVE and AT_RISK, which is precisely
    the judgement the score is competent to make.
    """
    if current in (AccountStatus.ONBOARDING, AccountStatus.CHURNED):
        return current
    return AccountStatus.AT_RISK if score < 40 else AccountStatus.ACTIVE


async def _has_recent_activity(
    session: AsyncSession,
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> bool:
    """Whether anything was logged against this record lately.

    One indexed count against ``ix_activities_organization_id_related`` rather
    than loading the timeline — the scorer only needs to know whether the count
    is zero.
    """
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=RECENT_ACTIVITY_DAYS)
    result = await session.execute(
        select(func.count())
        .select_from(Activity)
        .where(
            Activity.organization_id == organization_id,
            Activity.related_entity_type == entity_type,
            Activity.related_entity_id == entity_id,
            Activity.deleted_at.is_(None),
            Activity.status != ActivityStatus.CANCELLED,
            func.coalesce(Activity.completed_at, Activity.created_at) >= cutoff,
        )
    )
    return int(result.scalar_one()) > 0


async def _is_stale(session: AsyncSession, account: Account) -> bool:
    """No activity at all in the stale window, and old enough for that to mean something.

    The age check matters: an account created yesterday has no activity either,
    and penalising it would mark every new customer at risk on day one.
    """
    if account.created_at > dt.datetime.now(dt.UTC) - dt.timedelta(days=STALE_ACCOUNT_DAYS):
        return False
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=STALE_ACCOUNT_DAYS)
    result = await session.execute(
        select(func.count())
        .select_from(Activity)
        .where(
            Activity.organization_id == account.organization_id,
            Activity.related_entity_type == CrmEntityType.ACCOUNT,
            Activity.related_entity_id == account.id,
            Activity.deleted_at.is_(None),
            func.coalesce(Activity.completed_at, Activity.created_at) >= cutoff,
        )
    )
    return int(result.scalar_one()) == 0


def explain(score: Score) -> dict[str, Any]:
    """The score plus its breakdown, shaped for an API response."""
    return {
        "value": score.value,
        "components": [
            {"reason": reason, "points": points}
            for reason, points in sorted(
                score.components.items(), key=lambda item: -abs(item[1])
            )
        ],
    }


__all__ = [
    "ACCOUNT_WEIGHTS",
    "CONTACT_WEIGHTS",
    "LEAD_WEIGHTS",
    "RECENT_ACTIVITY_DAYS",
    "STALE_ACCOUNT_DAYS",
    "Score",
    "explain",
    "health_to_status",
    "score_account_health",
    "score_contact",
    "score_lead",
]
