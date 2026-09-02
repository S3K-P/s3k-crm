"""The CRM's background jobs.

Each handler receives a session already scoped to the job's organization — the
runner applies the tenant setting before calling, so RLS is active and a
handler that forgets to filter still cannot see another tenant's rows.

Every handler is **idempotent**: running it twice in a row produces the same
state as running it once. That is what makes retries safe, and it is why they
are written as "recompute from source" rather than "apply a delta".

Handlers return a summary dict, which lands on the job row. It is what an
operator reads to answer "did last night's scoring actually do anything", and
what the tests assert on.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.jobs.models import Job
from app.platform.jobs.service import Cadence, Schedule
from app.products.crm.accounts.models import Account
from app.products.crm.automation.models import AutomationSettings
from app.products.crm.automation.scoring import (
    health_to_status,
    score_account_health,
    score_contact,
    score_lead,
)
from app.products.crm.campaigns.service import CampaignService
from app.products.crm.common import CrmEntityType, Priority
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.opportunities.models import Opportunity
from app.products.crm.tasks.models import Task, TaskStatus

logger = structlog.get_logger(__name__)

# --- Job type names ----------------------------------------------------------
#
# Namespaced so the queue's job_type column is readable in a database client
# and so a Platform job could never collide with a CRM one.
SCORE_LEADS = "crm.score_leads"
SCORE_CONTACTS = "crm.score_contacts"
SCORE_ACCOUNT_HEALTH = "crm.score_account_health"
RECOMPUTE_CAMPAIGN_METRICS = "crm.recompute_campaign_metrics"
STALE_OPPORTUNITY_NUDGE = "crm.stale_opportunity_nudge"
STALE_LEAD_NUDGE = "crm.stale_lead_nudge"
CLOSING_SOON_REMINDER = "crm.closing_soon_reminder"

#: Batch ceiling per run. A tenant with a hundred thousand leads should not
#: hold one transaction open while all of them are scored; the job simply picks
#: up where it left off on the next tick, ordered by how stale the score is.
BATCH_SIZE = 500

#: A deal closing within this many days is worth a reminder.
CLOSING_SOON_DAYS = 7


async def get_settings(session: AsyncSession, organization_id: uuid.UUID) -> AutomationSettings:
    """This organization's automation switches, created on first use.

    Defaults are conservative (see ``AutomationSettings``): scoring off,
    reminders on. An organization that has never opened the settings screen
    therefore gets exactly the behaviour it had before automation existed.
    """
    result = await session.execute(
        select(AutomationSettings).where(
            AutomationSettings.organization_id == organization_id,
            AutomationSettings.deleted_at.is_(None),
        )
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = AutomationSettings(organization_id=organization_id)
        session.add(settings)
        await session.flush()
    return settings


# --- Scoring -----------------------------------------------------------------


async def score_leads(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Recompute ``ai_score`` for a batch of leads."""
    settings = await get_settings(session, job.organization_id)
    if not settings.lead_scoring_enabled:
        return {"skipped": "lead scoring disabled for this organization"}

    result = await session.execute(
        select(Lead)
        .where(
            Lead.organization_id == job.organization_id,
            Lead.deleted_at.is_(None),
            # Converted and lost leads are history; scoring them ranks records
            # nobody will ever work again.
            Lead.status.notin_((LeadStatus.CONVERTED, LeadStatus.LOST)),
        )
        .order_by(Lead.updated_at.asc())
        .limit(BATCH_SIZE)
    )
    leads = result.scalars().all()

    changed = 0
    for lead in leads:
        score = await score_lead(session, lead)
        if lead.ai_score != score.value:
            lead.ai_score = score.value
            changed += 1
    await session.flush()
    return {"scored": len(leads), "changed": changed}


async def score_contacts(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Recompute ``ai_score`` for a batch of contacts."""
    settings = await get_settings(session, job.organization_id)
    if not settings.contact_scoring_enabled:
        return {"skipped": "contact scoring disabled for this organization"}

    result = await session.execute(
        select(Contact)
        .where(
            Contact.organization_id == job.organization_id,
            Contact.deleted_at.is_(None),
        )
        .order_by(Contact.updated_at.asc())
        .limit(BATCH_SIZE)
    )
    contacts = result.scalars().all()

    changed = 0
    for contact in contacts:
        score = await score_contact(session, contact)
        if contact.ai_score != score.value:
            contact.ai_score = score.value
            changed += 1
    await session.flush()
    return {"scored": len(contacts), "changed": changed}


async def score_account_health_job(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Recompute account health, and optionally act on it.

    Computing the score and letting it relabel a customer are separately
    switched, because they are different levels of trust: seeing a number is
    reversible, and finding your customer list marked AT_RISK overnight is the
    kind of surprise that gets automation switched off entirely.
    """
    settings = await get_settings(session, job.organization_id)
    if not settings.account_health_enabled:
        return {"skipped": "account health disabled for this organization"}

    result = await session.execute(
        select(Account)
        .where(
            Account.organization_id == job.organization_id,
            Account.deleted_at.is_(None),
        )
        .order_by(Account.updated_at.asc())
        .limit(BATCH_SIZE)
    )
    accounts = result.scalars().all()

    changed = 0
    relabelled = 0
    for account in accounts:
        score = await score_account_health(session, account)
        if account.health_score != score.value:
            account.health_score = score.value
            changed += 1
        if settings.account_status_automation_enabled:
            suggested = health_to_status(score.value, account.status)
            if suggested is not account.status:
                account.status = suggested
                relabelled += 1
    await session.flush()
    return {"scored": len(accounts), "changed": changed, "relabelled": relabelled}


# --- Rollups -----------------------------------------------------------------


async def recompute_campaign_metrics(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Refresh every campaign's cached counts and ROI.

    ``CampaignService.recompute_metrics`` already existed and already derived
    the numbers correctly — its docstring says it belongs in a background job
    that did not exist yet. This is that job. Nothing about the calculation
    changed; it simply now runs without somebody opening a screen.
    """
    from app.products.crm.campaigns.models import Campaign

    result = await session.execute(
        select(Campaign).where(
            Campaign.organization_id == job.organization_id,
            Campaign.deleted_at.is_(None),
        )
    )
    campaigns = result.scalars().all()

    service = CampaignService(session)
    for campaign in campaigns:
        await service.recompute_metrics(campaign)
    await session.flush()
    return {"campaigns": len(campaigns)}


# --- Time-based nudges -------------------------------------------------------


async def _open_task_titles(
    session: AsyncSession,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType,
    entity_ids: list[uuid.UUID],
) -> set[tuple[uuid.UUID, str]]:
    """Existing open nudges, so a nightly job does not re-create them.

    One query for the whole batch rather than one per record: a nightly job
    over five hundred deals must not be five hundred round trips.
    """
    if not entity_ids:
        return set()
    result = await session.execute(
        select(Task.related_entity_id, Task.title).where(
            Task.organization_id == organization_id,
            Task.deleted_at.is_(None),
            Task.related_entity_type == entity_type,
            Task.related_entity_id.in_(entity_ids),
            Task.status.notin_((TaskStatus.COMPLETED, TaskStatus.CANCELLED)),
        )
    )
    return {(uuid.UUID(str(row[0])), str(row[1])) for row in result.all()}


async def stale_opportunity_nudge(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Create a follow-up task for open deals nobody has touched.

    The most-requested feature in every sales team, and the one that most
    needs the duplicate guard: run nightly without it and a deal that stays
    quiet for a fortnight accumulates fourteen identical tasks.
    """
    settings = await get_settings(session, job.organization_id)
    if not settings.stale_reminders_enabled:
        return {"skipped": "reminders disabled for this organization"}

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=settings.stale_opportunity_days)
    result = await session.execute(
        select(Opportunity)
        .where(
            Opportunity.organization_id == job.organization_id,
            Opportunity.deleted_at.is_(None),
            Opportunity.won_at.is_(None),
            Opportunity.lost_at.is_(None),
            Opportunity.updated_at < cutoff,
        )
        .order_by(Opportunity.updated_at.asc())
        .limit(BATCH_SIZE)
    )
    stale = result.scalars().all()

    title = "Follow up: no activity recently"
    existing = await _open_task_titles(
        session,
        job.organization_id,
        CrmEntityType.OPPORTUNITY,
        [deal.id for deal in stale],
    )

    created = 0
    for deal in stale:
        if (deal.id, title) in existing:
            continue
        session.add(
            Task(
                organization_id=job.organization_id,
                title=title,
                description=(
                    f"“{deal.name}” has had no update for "
                    f"{settings.stale_opportunity_days} days."
                ),
                priority=Priority.MEDIUM,
                owner_id=deal.owner_id,
                assigned_to_id=deal.owner_id,
                due_date=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
                related_entity_type=CrmEntityType.OPPORTUNITY,
                related_entity_id=deal.id,
            )
        )
        created += 1
    await session.flush()
    return {"stale": len(stale), "tasks_created": created}


async def stale_lead_nudge(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Nudge the owner of a lead that has gone quiet before qualification."""
    settings = await get_settings(session, job.organization_id)
    if not settings.stale_reminders_enabled:
        return {"skipped": "reminders disabled for this organization"}

    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=settings.stale_lead_days)
    result = await session.execute(
        select(Lead)
        .where(
            Lead.organization_id == job.organization_id,
            Lead.deleted_at.is_(None),
            Lead.status.in_((LeadStatus.NEW, LeadStatus.CONTACTED)),
            Lead.updated_at < cutoff,
        )
        .order_by(Lead.updated_at.asc())
        .limit(BATCH_SIZE)
    )
    stale = result.scalars().all()

    title = "Follow up: lead has gone quiet"
    existing = await _open_task_titles(
        session, job.organization_id, CrmEntityType.LEAD, [lead.id for lead in stale]
    )

    created = 0
    for lead in stale:
        if (lead.id, title) in existing:
            continue
        session.add(
            Task(
                organization_id=job.organization_id,
                title=title,
                description=(
                    f"{lead.full_name} has had no update for {settings.stale_lead_days} days."
                ),
                priority=Priority.MEDIUM,
                owner_id=lead.owner_id,
                assigned_to_id=lead.owner_id,
                due_date=dt.datetime.now(dt.UTC) + dt.timedelta(days=1),
                related_entity_type=CrmEntityType.LEAD,
                related_entity_id=lead.id,
            )
        )
        created += 1
    await session.flush()
    return {"stale": len(stale), "tasks_created": created}


async def closing_soon_reminder(session: AsyncSession, job: Job) -> dict[str, Any]:
    """Remind owners of deals whose close date is nearly here."""
    settings = await get_settings(session, job.organization_id)
    if not settings.stale_reminders_enabled:
        return {"skipped": "reminders disabled for this organization"}

    today = dt.datetime.now(dt.UTC).date()
    horizon = today + dt.timedelta(days=CLOSING_SOON_DAYS)
    result = await session.execute(
        select(Opportunity)
        .where(
            Opportunity.organization_id == job.organization_id,
            Opportunity.deleted_at.is_(None),
            Opportunity.won_at.is_(None),
            Opportunity.lost_at.is_(None),
            Opportunity.expected_close_date <= horizon,
            Opportunity.expected_close_date >= today,
        )
        .order_by(Opportunity.expected_close_date.asc())
        .limit(BATCH_SIZE)
    )
    closing = result.scalars().all()

    title = "Closing soon: confirm the outcome"
    existing = await _open_task_titles(
        session,
        job.organization_id,
        CrmEntityType.OPPORTUNITY,
        [deal.id for deal in closing],
    )

    created = 0
    for deal in closing:
        if (deal.id, title) in existing:
            continue
        session.add(
            Task(
                organization_id=job.organization_id,
                title=title,
                description=f"“{deal.name}” is expected to close on {deal.expected_close_date}.",
                priority=Priority.HIGH,
                owner_id=deal.owner_id,
                assigned_to_id=deal.owner_id,
                due_date=dt.datetime.now(dt.UTC),
                related_entity_type=CrmEntityType.OPPORTUNITY,
                related_entity_id=deal.id,
            )
        )
        created += 1
    await session.flush()
    return {"closing_soon": len(closing), "tasks_created": created}


# --- Registration ------------------------------------------------------------

#: Handlers, keyed by job type. Registered on the Platform queue at the
#: composition root so the queue never imports a product module.
HANDLERS = {
    SCORE_LEADS: score_leads,
    SCORE_CONTACTS: score_contacts,
    SCORE_ACCOUNT_HEALTH: score_account_health_job,
    RECOMPUTE_CAMPAIGN_METRICS: recompute_campaign_metrics,
    STALE_OPPORTUNITY_NUDGE: stale_opportunity_nudge,
    STALE_LEAD_NUDGE: stale_lead_nudge,
    CLOSING_SOON_REMINDER: closing_soon_reminder,
}

#: When each job runs. Scoring and rollups are nightly because their inputs
#: change slowly and the answer is only read the next morning; the nudges are
#: nightly for the same reason. Nothing here needs to be hourly, and making it
#: so would generate tasks people learn to ignore.
SCHEDULES: tuple[Schedule, ...] = (
    Schedule(RECOMPUTE_CAMPAIGN_METRICS, Cadence.DAILY, hour=1),
    Schedule(SCORE_LEADS, Cadence.DAILY, hour=2),
    Schedule(SCORE_CONTACTS, Cadence.DAILY, hour=2),
    Schedule(SCORE_ACCOUNT_HEALTH, Cadence.DAILY, hour=2),
    # After scoring, so a nudge reflects the score the morning will show.
    Schedule(STALE_LEAD_NUDGE, Cadence.DAILY, hour=3),
    Schedule(STALE_OPPORTUNITY_NUDGE, Cadence.DAILY, hour=3),
    Schedule(CLOSING_SOON_REMINDER, Cadence.DAILY, hour=3),
)


__all__ = [
    "BATCH_SIZE",
    "CLOSING_SOON_REMINDER",
    "HANDLERS",
    "RECOMPUTE_CAMPAIGN_METRICS",
    "SCHEDULES",
    "SCORE_ACCOUNT_HEALTH",
    "SCORE_CONTACTS",
    "SCORE_LEADS",
    "STALE_LEAD_NUDGE",
    "STALE_OPPORTUNITY_NUDGE",
    "get_settings",
]
