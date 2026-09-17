"""Read the CRM into Next Best Action signal snapshots — batched, permission-aware.

The read model behind ``nba_signals.py``, in the same spirit as
``insights.py``: plain SQL questions over the records a caller can already see,
a fixed number of queries per page of records rather than per record.

Rules that hold throughout:

* **Archived rows never count.** Every activity, meeting, email, contact and
  deal read here filters ``deleted_at IS NULL`` — an archived call is not
  "last contact", an archived contact is not a stakeholder.
* **Cancelled work is not an interaction.** Only calls/emails/meetings that
  happened count toward "last interaction" or "last follow-up"; a planned
  activity whose date has passed without being completed does not.
* **Other modules' permissions still apply.** Stakeholder counts need
  ``contacts.VIEW``; account industry, custom fields and deal history need
  ``accounts.VIEW`` and the account's own record visibility; closed-deal
  history for predictions is limited to the deals the caller may see. Without
  the permission the signal is ``None``, and rules on it simply do not fire.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.models import Account
from app.products.crm.activities.models import Activity, ActivityStatus, ActivityType, Meeting
from app.products.crm.ai_insights.models import NbaActionLog
from app.products.crm.ai_insights.nba_predictive import ClosedDeal, value_band
from app.products.crm.ai_insights.nba_signals import (
    contact_roles,
    custom_field_signals,
    days_since,
    meeting_purposes,
    mentions_pricing,
)
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.emails.models import EmailDirection, EmailMessage, EmailStatus
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.opportunities.models import (
    Opportunity,
    OpportunityStageHistory,
    PipelineStage,
)
from app.products.crm.shared.visibility import RecordVisibility

#: Hard ceilings on rows read per batch — a runaway record cannot turn one
#: queue load into an unbounded scan.
MAX_ACTIVITY_ROWS = 5_000
MAX_EMAIL_ROWS = 5_000
MAX_HISTORY_DEALS = 1_000
RECENT_TEXT_DAYS = 30
PRICING_WINDOW_DAYS = 14
RECENT_TEXT_LIMIT = 4_000
SUPPRESSION_WINDOW_DAYS = 30

_CUSTOMER_TOUCH_TYPES = (ActivityType.CALL, ActivityType.EMAIL, ActivityType.MEETING)


@dataclass(slots=True)
class _Interactions:
    last_interaction_at: dt.datetime | None = None
    last_outbound_at: dt.datetime | None = None
    last_inbound_at: dt.datetime | None = None
    last_outbound_email_at: dt.datetime | None = None
    outbound_emails_30d: int = 0
    inbound_emails_30d: int = 0
    last_meeting_at: dt.datetime | None = None
    completed_meetings: int = 0
    upcoming_meetings: int = 0
    purposes: set[str] = field(default_factory=set)
    texts: list[str] = field(default_factory=list)
    pricing_recent: bool = False


def _later(current: dt.datetime | None, candidate: dt.datetime | None) -> dt.datetime | None:
    if candidate is None:
        return current
    return candidate if current is None or candidate > current else current


async def _interactions(
    session: AsyncSession,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType,
    ids: Sequence[uuid.UUID],
    now: dt.datetime,
) -> dict[uuid.UUID, _Interactions]:
    result: dict[uuid.UUID, _Interactions] = defaultdict(_Interactions)
    if not ids:
        return result
    occurred = func.coalesce(
        Meeting.start_time, Activity.completed_at, Activity.due_date, Activity.created_at
    )
    rows = (
        await session.execute(
            select(
                Activity.related_entity_id,
                Activity.type,
                Activity.status,
                Activity.subject,
                Activity.description,
                Activity.outcome,
                Activity.completed_at,
                occurred,
                Meeting.start_time,
            )
            .outerjoin(Meeting, Meeting.activity_id == Activity.id)
            .where(
                Activity.organization_id == organization_id,
                Activity.deleted_at.is_(None),
                Activity.related_entity_type == entity_type,
                Activity.related_entity_id.in_(ids),
            )
            .order_by(occurred.desc())
            .limit(MAX_ACTIVITY_ROWS)
        )
    ).all()
    text_cutoff = now - dt.timedelta(days=RECENT_TEXT_DAYS)
    pricing_cutoff = now - dt.timedelta(days=PRICING_WINDOW_DAYS)
    for entity_id, kind, status, subject, description, outcome, completed_at, at, start in rows:
        if entity_id is None:
            continue
        info = result[entity_id]
        if status is ActivityStatus.CANCELLED:
            continue
        text = " ".join(part for part in (subject, description, outcome) if part)
        if at is not None and text_cutoff <= at <= now:
            info.texts.append(text)
            if at >= pricing_cutoff and mentions_pricing(text):
                info.pricing_recent = True
        if kind is ActivityType.MEETING and start is not None:
            if start > now:
                if status is ActivityStatus.PLANNED:
                    info.upcoming_meetings += 1
                continue
            info.completed_meetings += 1
            info.last_meeting_at = _later(info.last_meeting_at, start)
            info.purposes |= meeting_purposes(subject)
            info.last_interaction_at = _later(info.last_interaction_at, start)
            info.last_outbound_at = _later(info.last_outbound_at, start)
            continue
        if kind in _CUSTOMER_TOUCH_TYPES and status is ActivityStatus.COMPLETED:
            touched = completed_at or at
            if touched is not None and touched <= now:
                info.last_interaction_at = _later(info.last_interaction_at, touched)
                info.last_outbound_at = _later(info.last_outbound_at, touched)

    email_rows = (
        await session.execute(
            select(
                EmailMessage.related_entity_id,
                EmailMessage.direction,
                func.coalesce(EmailMessage.sent_at, EmailMessage.created_at),
            )
            .where(
                EmailMessage.organization_id == organization_id,
                EmailMessage.deleted_at.is_(None),
                EmailMessage.related_entity_type == entity_type,
                EmailMessage.related_entity_id.in_(ids),
                or_(
                    EmailMessage.direction == EmailDirection.INBOUND,
                    EmailMessage.status.in_((EmailStatus.SENT, EmailStatus.QUEUED)),
                ),
            )
            .order_by(func.coalesce(EmailMessage.sent_at, EmailMessage.created_at).desc())
            .limit(MAX_EMAIL_ROWS)
        )
    ).all()
    for entity_id, direction, at in email_rows:
        if entity_id is None or at is None:
            continue
        info = result[entity_id]
        recent = at >= text_cutoff
        info.last_interaction_at = _later(info.last_interaction_at, at)
        if direction is EmailDirection.INBOUND:
            info.last_inbound_at = _later(info.last_inbound_at, at)
            info.inbound_emails_30d += int(recent)
        else:
            info.last_outbound_at = _later(info.last_outbound_at, at)
            info.last_outbound_email_at = _later(info.last_outbound_email_at, at)
            info.outbound_emails_30d += int(recent)
    return result


def _interaction_signals(info: _Interactions, now: dt.datetime) -> dict[str, Any]:
    text = " \n".join(info.texts)[:RECENT_TEXT_LIMIT]
    awaiting = info.last_outbound_email_at is not None and (
        info.last_inbound_at is None or info.last_inbound_at < info.last_outbound_email_at
    )
    return {
        "days_since_last_interaction": days_since(info.last_interaction_at, now),
        "days_since_last_outbound": days_since(info.last_outbound_at, now),
        "days_since_last_customer_response": days_since(info.last_inbound_at, now),
        "awaiting_customer_response": awaiting,
        "outbound_emails_30d": info.outbound_emails_30d,
        "inbound_emails_30d": info.inbound_emails_30d,
        "days_since_last_meeting": days_since(info.last_meeting_at, now),
        "completed_meeting_count": info.completed_meetings,
        "upcoming_meeting_count": info.upcoming_meetings,
        "demo_completed": "demo" in info.purposes,
        "technical_workshop_completed": "workshop" in info.purposes,
        "pricing_discussed_recently": info.pricing_recent,
        "recent_interaction_text": text or None,
    }


def _follow_up_signals(
    entity_id: uuid.UUID,
    info: _Interactions,
    open_tasks: Mapping[uuid.UUID, int],
    overdue: Mapping[uuid.UUID, int],
) -> dict[str, Any]:
    open_count = open_tasks.get(entity_id, 0)
    return {
        "open_task_count": open_count,
        "overdue_task_count": overdue.get(entity_id, 0),
        "has_follow_up_scheduled": open_count > 0 or info.upcoming_meetings > 0,
    }


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenDeal:
    """What the predictive layer needs about one open deal."""

    band: int | None
    done: frozenset[str]
    past_proposal: bool


async def opportunity_signals(
    session: AsyncSession,
    principal: Principal,
    opportunities: Sequence[Opportunity],
    *,
    open_tasks: Mapping[uuid.UUID, int],
    overdue: Mapping[uuid.UUID, int],
    now: dt.datetime,
) -> tuple[dict[uuid.UUID, dict[str, Any]], dict[uuid.UUID, OpenDeal]]:
    org = principal.organization_id
    ids = [opportunity.id for opportunity in opportunities]
    if not ids:
        return {}, {}
    today = now.date()

    # --- Stages: name, pipeline order, when the deal entered its stage -----
    stage_rows = (
        await session.execute(
            select(
                PipelineStage.id,
                PipelineStage.pipeline_id,
                PipelineStage.name,
                PipelineStage.sort_order,
            ).where(
                PipelineStage.organization_id == org,
                PipelineStage.pipeline_id.in_(
                    select(PipelineStage.pipeline_id).where(
                        PipelineStage.id.in_(
                            {opportunity.stage_id for opportunity in opportunities}
                        )
                    )
                ),
            )
        )
    ).all()
    stages = {row[0]: row for row in stage_rows}
    proposal_order: dict[uuid.UUID, int] = {}
    for _, pipeline_id, name, sort_order in stage_rows:
        if "proposal" in name.lower():
            proposal_order[pipeline_id] = min(
                proposal_order.get(pipeline_id, sort_order), sort_order
            )

    entered_rows = (
        await session.execute(
            select(
                OpportunityStageHistory.opportunity_id,
                OpportunityStageHistory.to_stage_id,
                func.max(OpportunityStageHistory.changed_at),
            )
            .where(
                OpportunityStageHistory.organization_id == org,
                OpportunityStageHistory.opportunity_id.in_(ids),
            )
            .group_by(OpportunityStageHistory.opportunity_id, OpportunityStageHistory.to_stage_id)
        )
    ).all()
    entered = {(row[0], row[1]): row[2] for row in entered_rows}

    interactions = await _interactions(session, org, CrmEntityType.OPPORTUNITY, ids, now)

    # --- Accounts (their own permission and visibility) --------------------
    account_ids = {opportunity.account_id for opportunity in opportunities}
    accounts: dict[uuid.UUID, Account] = {}
    if principal.has_permission("accounts", PermissionAction.VIEW):
        statement = select(Account).where(
            Account.organization_id == org,
            Account.deleted_at.is_(None),
            Account.id.in_(account_ids),
        )
        predicate = RecordVisibility.for_module(principal, "accounts").filter_for(Account)
        if predicate is not None:
            statement = statement.where(predicate)
        accounts = {account.id: account for account in (await session.execute(statement)).scalars()}

    # --- Stakeholders ------------------------------------------------------
    may_see_contacts = principal.has_permission("contacts", PermissionAction.VIEW)
    roles_by_account: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    contacts_by_account: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    phone_by_contact: dict[uuid.UUID, bool] = {}
    engaged: set[uuid.UUID] = set()
    if may_see_contacts:
        primary_ids = {o.primary_contact_id for o in opportunities if o.primary_contact_id}
        contact_rows = (
            await session.execute(
                select(
                    Contact.id,
                    Contact.account_id,
                    Contact.job_title,
                    Contact.department,
                    Contact.phone,
                    Contact.mobile,
                ).where(
                    Contact.organization_id == org,
                    Contact.deleted_at.is_(None),
                    or_(Contact.account_id.in_(account_ids), Contact.id.in_(primary_ids)),
                )
            )
        ).all()
        for contact_id, account_id, title, department, phone, mobile in contact_rows:
            phone_by_contact[contact_id] = bool(phone or mobile)
            if account_id is None:
                continue
            contacts_by_account[account_id].append(contact_id)
            for role in contact_roles(title, department):
                roles_by_account[account_id][role] += 1
        contact_ids = [row[0] for row in contact_rows]
        if contact_ids:
            cutoff = now - dt.timedelta(days=RECENT_TEXT_DAYS)
            engaged |= {
                row[0]
                for row in (
                    await session.execute(
                        select(Activity.related_entity_id).where(
                            Activity.organization_id == org,
                            Activity.deleted_at.is_(None),
                            Activity.related_entity_type == CrmEntityType.CONTACT,
                            Activity.related_entity_id.in_(contact_ids),
                            func.coalesce(Activity.completed_at, Activity.created_at) >= cutoff,
                        )
                    )
                ).all()
                if row[0] is not None
            }
            engaged |= {
                row[0]
                for row in (
                    await session.execute(
                        select(EmailMessage.related_entity_id).where(
                            EmailMessage.organization_id == org,
                            EmailMessage.deleted_at.is_(None),
                            EmailMessage.related_entity_type == CrmEntityType.CONTACT,
                            EmailMessage.related_entity_id.in_(contact_ids),
                            EmailMessage.created_at >= cutoff,
                        )
                    )
                ).all()
                if row[0] is not None
            }

    # --- Account history (closed deals the caller may see) -----------------
    won_by_account: dict[uuid.UUID, int] = defaultdict(int)
    lost_by_account: dict[uuid.UUID, int] = defaultdict(int)
    products_by_account: dict[uuid.UUID, list[str]] = defaultdict(list)
    if accounts:
        history_statement = select(
            Opportunity.account_id, Opportunity.won_at, Opportunity.products
        ).where(
            Opportunity.organization_id == org,
            Opportunity.deleted_at.is_(None),
            Opportunity.account_id.in_(list(accounts)),
            or_(Opportunity.won_at.is_not(None), Opportunity.lost_at.is_not(None)),
        )
        predicate = RecordVisibility.for_module(principal, "opportunities").filter_for(Opportunity)
        if predicate is not None:
            history_statement = history_statement.where(predicate)
        for account_id, won_at, products in (await session.execute(history_statement)).all():
            if won_at is not None:
                won_by_account[account_id] += 1
                for product in (products or "").replace("\n", ",").split(","):
                    name = product.strip()
                    if name and name not in products_by_account[account_id]:
                        products_by_account[account_id].append(name)
            else:
                lost_by_account[account_id] += 1

    signals: dict[uuid.UUID, dict[str, Any]] = {}
    open_deals: dict[uuid.UUID, OpenDeal] = {}
    for opportunity in opportunities:
        info = interactions[opportunity.id]
        stage = stages.get(opportunity.stage_id)
        stage_name = stage[2] if stage else ""
        lowered = stage_name.lower()
        is_proposal = "proposal" in lowered
        is_negotiation = "negotiation" in lowered or "contract" in lowered
        order = proposal_order.get(stage[1]) if stage else None
        is_early = (
            (stage[3] < order)
            if (stage and order is not None)
            else not (is_proposal or is_negotiation)
        )
        entered_at = entered.get((opportunity.id, opportunity.stage_id)) or opportunity.created_at
        account = accounts.get(opportunity.account_id)
        roles = roles_by_account.get(opportunity.account_id, {}) if may_see_contacts else None
        contact_list = contacts_by_account.get(opportunity.account_id, [])

        snapshot: dict[str, Any] = {
            "stage_name": stage_name,
            "stage_is_proposal": is_proposal,
            "stage_is_negotiation": is_negotiation,
            "stage_is_early": is_early,
            "days_in_stage": days_since(entered_at, now),
            "deal_value": float(opportunity.deal_value)
            if opportunity.deal_value is not None
            else None,
            "win_probability": opportunity.win_probability,
            "days_to_close": (
                (opportunity.expected_close_date - today).days
                if opportunity.expected_close_date is not None
                else None
            ),
            "has_competitor": bool((opportunity.competitor or "").strip()),
            "competitor": (opportunity.competitor or "").strip() or None,
            "account_industry": account.industry if account else None,
            "has_phone": (
                phone_by_contact.get(opportunity.primary_contact_id)
                if may_see_contacts and opportunity.primary_contact_id
                else None
            ),
            "contact_count": len(contact_list) if may_see_contacts else None,
            "decision_maker_count": roles.get("decision_maker", 0) if roles is not None else None,
            "technical_contact_count": roles.get("technical", 0) if roles is not None else None,
            "procurement_contact_count": roles.get("procurement", 0) if roles is not None else None,
            "finance_contact_count": roles.get("finance", 0) if roles is not None else None,
            "engaged_contact_count_30d": (
                sum(1 for contact_id in contact_list if contact_id in engaged)
                if may_see_contacts
                else None
            ),
            "account_won_deals": won_by_account.get(opportunity.account_id, 0) if account else None,
            "account_lost_deals": lost_by_account.get(opportunity.account_id, 0)
            if account
            else None,
            "account_is_customer": (won_by_account.get(opportunity.account_id, 0) > 0)
            if account
            else None,
            "account_products": ", ".join(products_by_account.get(opportunity.account_id, []))
            or None,
        }
        snapshot |= _interaction_signals(info, now)
        snapshot |= _follow_up_signals(opportunity.id, info, open_tasks, overdue)
        snapshot |= custom_field_signals(
            opportunity.custom_fields or {},
            (account.custom_fields or {}) if account else {},
            today=today,
        )
        signals[opportunity.id] = snapshot

        done: set[str] = set()
        if "workshop" in info.purposes:
            done.add("workshop_before_proposal")
        if "demo" in info.purposes:
            done.add("demo_before_proposal")
        if "executive" in info.purposes:
            done.add("executive_meeting")
        open_deals[opportunity.id] = OpenDeal(
            band=value_band(opportunity.deal_value),
            done=frozenset(done),
            past_proposal=not is_early,
        )
    return signals, open_deals


async def closed_deal_history(
    session: AsyncSession, principal: Principal, *, now: dt.datetime
) -> list[ClosedDeal]:
    """The caller-visible closed deals the predictive layer learns from."""
    if not principal.has_permission("opportunities", PermissionAction.VIEW):
        return []
    org = principal.organization_id
    closed_at = func.coalesce(Opportunity.won_at, Opportunity.lost_at)
    statement = (
        select(Opportunity.id, Opportunity.deal_value, Opportunity.won_at, closed_at)
        .where(
            Opportunity.organization_id == org,
            Opportunity.deleted_at.is_(None),
            or_(Opportunity.won_at.is_not(None), Opportunity.lost_at.is_not(None)),
        )
        .order_by(closed_at.desc())
        .limit(MAX_HISTORY_DEALS)
    )
    predicate = RecordVisibility.for_module(principal, "opportunities").filter_for(Opportunity)
    if predicate is not None:
        statement = statement.where(predicate)
    deals = (await session.execute(statement)).all()
    if not deals:
        return []
    ids = [row[0] for row in deals]

    proposal_rows = (
        await session.execute(
            select(
                OpportunityStageHistory.opportunity_id, func.min(OpportunityStageHistory.changed_at)
            )
            .join(PipelineStage, PipelineStage.id == OpportunityStageHistory.to_stage_id)
            .where(
                OpportunityStageHistory.organization_id == org,
                OpportunityStageHistory.opportunity_id.in_(ids),
                PipelineStage.name.ilike("%proposal%"),
            )
            .group_by(OpportunityStageHistory.opportunity_id)
        )
    ).all()
    proposal_at = {row[0]: row[1] for row in proposal_rows}

    meetings: dict[uuid.UUID, list[tuple[dt.datetime, set[str]]]] = defaultdict(list)
    meeting_rows = (
        await session.execute(
            select(Activity.related_entity_id, Activity.subject, Meeting.start_time)
            .join(Meeting, Meeting.activity_id == Activity.id)
            .where(
                Activity.organization_id == org,
                Activity.deleted_at.is_(None),
                Activity.type == ActivityType.MEETING,
                Activity.status != ActivityStatus.CANCELLED,
                Activity.related_entity_type == CrmEntityType.OPPORTUNITY,
                Activity.related_entity_id.in_(ids),
            )
            .limit(MAX_ACTIVITY_ROWS)
        )
    ).all()
    for entity_id, subject, start in meeting_rows:
        if entity_id is not None and start is not None:
            meetings[entity_id].append((start, meeting_purposes(subject)))

    history: list[ClosedDeal] = []
    for deal_id, deal_value, won_at, closed in deals:
        practices: set[str] = set()
        cutoff = proposal_at.get(deal_id) or closed
        for start, purposes in meetings.get(deal_id, []):
            if start > closed:
                continue
            if "workshop" in purposes and start < cutoff:
                practices.add("workshop_before_proposal")
            if "demo" in purposes and start < cutoff:
                practices.add("demo_before_proposal")
            if "executive" in purposes:
                practices.add("executive_meeting")
        history.append(
            ClosedDeal(
                won=won_at is not None, band=value_band(deal_value), practices=frozenset(practices)
            )
        )
    return history


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


async def lead_signals(
    session: AsyncSession,
    principal: Principal,
    leads: Sequence[Lead],
    *,
    open_tasks: Mapping[uuid.UUID, int],
    overdue: Mapping[uuid.UUID, int],
    now: dt.datetime,
) -> dict[uuid.UUID, dict[str, Any]]:
    ids = [lead.id for lead in leads]
    interactions = await _interactions(
        session, principal.organization_id, CrmEntityType.LEAD, ids, now
    )
    signals: dict[uuid.UUID, dict[str, Any]] = {}
    for lead in leads:
        info = interactions[lead.id]
        snapshot: dict[str, Any] = {
            "lead_status": lead.status.value,
            "lead_priority": lead.priority.value if lead.priority else None,
            "expected_deal_size": (
                float(lead.expected_deal_size) if lead.expected_deal_size is not None else None
            ),
            "days_since_created": days_since(lead.created_at, now),
            "has_email": bool(lead.email),
            "has_phone": bool(lead.phone),
            "stage_is_proposal": lead.status is LeadStatus.PROPOSAL_SENT,
            "stage_is_negotiation": lead.status is LeadStatus.NEGOTIATION,
            "stage_is_early": lead.status not in (LeadStatus.PROPOSAL_SENT, LeadStatus.NEGOTIATION),
        }
        snapshot |= _interaction_signals(info, now)
        snapshot |= _follow_up_signals(lead.id, info, open_tasks, overdue)
        snapshot |= custom_field_signals(lead.custom_fields or {}, {}, today=now.date())
        signals[lead.id] = snapshot
    return signals


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------


async def recent_action_logs(
    session: AsyncSession,
    organization_id: uuid.UUID,
    entity_type: str,
    ids: Sequence[uuid.UUID],
    *,
    now: dt.datetime,
) -> dict[uuid.UUID, dict[str, tuple[str, dt.datetime]]]:
    """``entity_id -> action_code -> (outcome, most recent log time)`` over the window."""
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(
                NbaActionLog.entity_id,
                NbaActionLog.action_code,
                NbaActionLog.outcome,
                func.max(NbaActionLog.created_at),
            )
            .where(
                NbaActionLog.organization_id == organization_id,
                NbaActionLog.entity_type == entity_type,
                NbaActionLog.entity_id.in_(ids),
                NbaActionLog.created_at >= now - dt.timedelta(days=SUPPRESSION_WINDOW_DAYS),
            )
            .group_by(NbaActionLog.entity_id, NbaActionLog.action_code, NbaActionLog.outcome)
        )
    ).all()
    logs: dict[uuid.UUID, dict[str, tuple[str, dt.datetime]]] = defaultdict(dict)
    for entity_id, action_code, outcome, at in rows:
        current = logs[entity_id].get(action_code)
        if current is None or at > current[1]:
            logs[entity_id][action_code] = (outcome.value, at)
    return logs


__all__ = [
    "OpenDeal",
    "closed_deal_history",
    "lead_signals",
    "opportunity_signals",
    "recent_action_logs",
]
