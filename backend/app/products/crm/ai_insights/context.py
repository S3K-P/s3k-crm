"""Turning an account, opportunity or lead into context the model can use.

Extends the pattern :mod:`app.products.crm.market_insights.context`
established for Checkpoint 1, with the same three rules:

**Permission-filtered, per module.** Every section is gated on the caller's
own permission for the module it comes from — ``principal.has_permission(...)``
— checked here rather than assumed from record-level visibility alone.
:meth:`AccountService.timeline`/:meth:`OpportunityService.timeline` are
deliberately **not** reused for this: both merge activities, tasks, notes and
email into one stream behind a single ``accounts.VIEW``/``opportunities.VIEW``
check with no per-source gate, which is the right trade-off for a human
reading their own account's timeline panel but the wrong one for what leaves
the organization's boundary in a model prompt. This module goes back to the
same building blocks (:mod:`app.products.crm.shared.timeline`) and adds the
gate market_insights already uses, so a caller who cannot read contacts,
tasks, notes or email does not learn about them by asking the AI instead.

**Read-only.** Nothing here writes.

**Clearly labelled as CRM**, fenced and attributed — see ``prompts.py``.

Contact personal detail stays narrow, for the same reason market_insights
gives: names and roles, never email addresses or phone numbers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.models import Account
from app.products.crm.common import CrmEntityType
from app.products.crm.contacts.models import Contact
from app.products.crm.currency import format_money
from app.products.crm.leads.models import Lead, LeadSource
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.shared.timeline import (
    TimelineEntry,
    activity_entries,
    deal_created_entries,
    email_entries,
    merge_timeline_entries,
    note_entries,
    stage_changed_entries,
    task_entries,
)
from app.products.crm.shared.visibility import RecordVisibility

MAX_CONTACTS = 8
MAX_OPPORTUNITIES = 8
MAX_TIMELINE_ENTRIES = 15


@dataclass(frozen=True, slots=True)
class CrmContext:
    """Rendered CRM context, plus what it was allowed to include."""

    text: str
    sections: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


def _lines(fields: list[tuple[str, object | None]]) -> list[str]:
    """Render ``(label, value)`` pairs, skipping fields nobody filled in.

    Same reasoning as ``market_insights.context._account_lines``: a page of
    "Field: None" reads to a model as a signal about the record rather than
    about the CRM, and the report hedges for no reason.
    """
    return [f"- {label}: {value}" for label, value in fields if value not in (None, "")]


def _timeline_lines(entries: list[TimelineEntry]) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        when = entry.occurred_at.date().isoformat()
        line = f"- [{when}] {entry.title}"
        if entry.detail:
            line += f" — {entry.detail}"
        lines.append(line)
    return lines


async def _timeline_for(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
    principal: Principal,
    opportunity_filter: object | None = None,
) -> list[TimelineEntry]:
    """Activities, tasks, notes and sent email against one record — gated.

    ``opportunity_filter`` also pulls in deal-creation and stage-change
    entries scoped by that predicate, used for the account context (every
    opportunity on the account) — the opportunity's own context passes no
    filter, since it is not itself a source of deal-created/stage-changed
    entries about *other* deals.
    """
    groups: list[list[TimelineEntry]] = []

    if principal.has_permission("activities", PermissionAction.VIEW):
        groups.append(
            await activity_entries(
                session,
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                limit=MAX_TIMELINE_ENTRIES,
            )
        )
    if principal.has_permission("tasks", PermissionAction.VIEW):
        groups.append(
            await task_entries(
                session,
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                visibility=RecordVisibility.for_module(principal, "tasks"),
                limit=MAX_TIMELINE_ENTRIES,
            )
        )
    if principal.has_permission("notes", PermissionAction.VIEW):
        groups.append(
            await note_entries(
                session,
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                viewer_id=principal.user_id,
                limit=MAX_TIMELINE_ENTRIES,
            )
        )
    if principal.has_permission("emails", PermissionAction.VIEW):
        groups.append(
            await email_entries(
                session,
                organization_id=organization_id,
                entity_type=entity_type,
                entity_id=entity_id,
                viewer_id=principal.user_id,
                limit=MAX_TIMELINE_ENTRIES,
            )
        )
    if opportunity_filter is not None and principal.has_permission(
        "opportunities", PermissionAction.VIEW
    ):
        visibility = RecordVisibility.for_module(principal, "opportunities")
        groups.append(
            await deal_created_entries(
                session,
                organization_id=organization_id,
                opportunity_filter=opportunity_filter,  # type: ignore[arg-type]
                visibility=visibility,
                limit=MAX_TIMELINE_ENTRIES,
            )
        )
        groups.append(
            await stage_changed_entries(
                session,
                organization_id=organization_id,
                opportunity_filter=opportunity_filter,  # type: ignore[arg-type]
                visibility=visibility,
                limit=MAX_TIMELINE_ENTRIES,
            )
        )

    return merge_timeline_entries(*groups, limit=MAX_TIMELINE_ENTRIES)


async def build_account_context(
    session: AsyncSession, *, account: Account, principal: Principal
) -> CrmContext:
    """Describe ``account`` for the model, within the caller's permissions."""
    lines: list[str] = ["## Account record", "", *_account_lines(account)]
    sections: list[str] = ["accounts"]

    if principal.has_permission("contacts", PermissionAction.VIEW):
        contacts = await _contacts(session, account_id=account.id, principal=principal)
        if contacts:
            sections.append("contacts")
            lines += ["", "## Known contacts", ""]
            lines += contacts

    if principal.has_permission("opportunities", PermissionAction.VIEW):
        opportunities = await _opportunities(session, account_id=account.id, principal=principal)
        if opportunities:
            sections.append("opportunities")
            lines += ["", "## Open and recent opportunities", ""]
            lines += opportunities

    timeline = await _timeline_for(
        session,
        organization_id=account.organization_id,
        entity_type=CrmEntityType.ACCOUNT,
        entity_id=account.id,
        principal=principal,
        opportunity_filter=Opportunity.account_id == account.id,
    )
    if timeline:
        sections.append("timeline")
        lines += ["", "## Recent activity (newest first)", ""]
        lines += _timeline_lines(timeline)

    return CrmContext(text="\n".join(lines).strip(), sections=tuple(sections))


async def build_opportunity_context(
    session: AsyncSession, *, opportunity: Opportunity, principal: Principal
) -> CrmContext:
    """Describe ``opportunity`` for the model, within the caller's permissions."""
    stage_name = await _stage_name(session, opportunity.stage_id)
    lines: list[str] = [
        "## Deal record",
        "",
        *_opportunity_lines(opportunity, stage_name=stage_name),
    ]
    sections: list[str] = ["opportunities"]

    if principal.has_permission("accounts", PermissionAction.VIEW):
        account_name = await _account_name(session, opportunity.account_id)
        if account_name:
            lines += ["", "## Account", "", f"- {account_name}"]
            sections.append("accounts")

    if (
        principal.has_permission("contacts", PermissionAction.VIEW)
        and opportunity.primary_contact_id
    ):
        contact_line = await _contact_line(session, opportunity.primary_contact_id)
        if contact_line:
            lines += ["", "## Primary contact", "", contact_line]
            sections.append("contacts")

    timeline = await _timeline_for(
        session,
        organization_id=opportunity.organization_id,
        entity_type=CrmEntityType.OPPORTUNITY,
        entity_id=opportunity.id,
        principal=principal,
    )
    if timeline:
        sections.append("timeline")
        lines += ["", "## Recent activity (newest first)", ""]
        lines += _timeline_lines(timeline)

    return CrmContext(text="\n".join(lines).strip(), sections=tuple(sections))


async def build_lead_context(
    session: AsyncSession, *, lead: Lead, principal: Principal
) -> CrmContext:
    """Describe ``lead`` for the model, within the caller's permissions."""
    source_name = await _lead_source_name(session, lead.lead_source_id)
    lines: list[str] = ["## Lead record", "", *_lead_lines(lead, source_name=source_name)]
    sections: list[str] = ["leads"]

    timeline = await _timeline_for(
        session,
        organization_id=lead.organization_id,
        entity_type=CrmEntityType.LEAD,
        entity_id=lead.id,
        principal=principal,
    )
    if timeline:
        sections.append("timeline")
        lines += ["", "## Recent activity (newest first)", ""]
        lines += _timeline_lines(timeline)

    return CrmContext(text="\n".join(lines).strip(), sections=tuple(sections))


# ---------------------------------------------------------------------------
# Field rendering
# ---------------------------------------------------------------------------


def _account_lines(account: Account) -> list[str]:
    return _lines(
        [
            ("Name", account.name),
            ("Industry", account.industry),
            ("Website", account.website),
            ("Company size", account.company_size),
            (
                "Annual revenue",
                format_money(account.annual_revenue)
                if account.annual_revenue is not None
                else None,
            ),
            ("Status", account.status.value),
            ("Health score", account.health_score),
            ("Source", account.source),
            (
                "Location",
                ", ".join(p for p in (account.city, account.state, account.country) if p) or None,
            ),
            ("Description", account.description),
        ]
    )


def _opportunity_lines(opportunity: Opportunity, *, stage_name: str | None) -> list[str]:
    return _lines(
        [
            ("Name", opportunity.name),
            ("Stage", stage_name),
            (
                "Deal value",
                format_money(opportunity.deal_value) if opportunity.deal_value else None,
            ),
            (
                "Win probability",
                f"{opportunity.win_probability}%"
                if opportunity.win_probability is not None
                else None,
            ),
            (
                "Expected close date",
                opportunity.expected_close_date.isoformat()
                if opportunity.expected_close_date
                else None,
            ),
            ("Forecast category", opportunity.forecast_category),
            ("Competitor", opportunity.competitor),
            ("Health score", opportunity.health_score),
            ("Won at", opportunity.won_at.date().isoformat() if opportunity.won_at else None),
            ("Lost at", opportunity.lost_at.date().isoformat() if opportunity.lost_at else None),
            ("Loss reason", opportunity.loss_reason),
        ]
    )


def _lead_lines(lead: Lead, *, source_name: str | None) -> list[str]:
    name = f"{lead.first_name} {lead.last_name}".strip()
    return _lines(
        [
            ("Name", name),
            ("Company", lead.company),
            ("Status", lead.status.value),
            ("Priority", lead.priority.value if lead.priority else None),
            ("Source", source_name),
            ("Industry", lead.industry),
            ("Company size", lead.company_size),
            ("Product interest", lead.product_interest),
            (
                "Expected deal size",
                format_money(lead.expected_deal_size) if lead.expected_deal_size else None,
            ),
            ("Lost reason", lead.lost_reason),
        ]
    )


# ---------------------------------------------------------------------------
# Related-record queries
# ---------------------------------------------------------------------------


async def _contacts(
    session: AsyncSession, *, account_id: uuid.UUID, principal: Principal
) -> list[str]:
    visibility = RecordVisibility.for_module(principal, "contacts")
    statement = (
        select(Contact)
        .where(
            Contact.organization_id == principal.organization_id,
            Contact.account_id == account_id,
            Contact.deleted_at.is_(None),
        )
        .order_by(Contact.created_at.desc())
        .limit(MAX_CONTACTS)
    )
    predicate = visibility.filter_for(Contact)
    if predicate is not None:
        statement = statement.where(predicate)
    rows = (await session.execute(statement)).scalars().all()
    lines: list[str] = []
    for contact in rows:
        name = f"{contact.first_name} {contact.last_name}".strip()
        role = contact.job_title or contact.department
        lines.append(f"- {name}" + (f" — {role}" if role else ""))
    return lines


async def _opportunities(
    session: AsyncSession, *, account_id: uuid.UUID, principal: Principal
) -> list[str]:
    visibility = RecordVisibility.for_module(principal, "opportunities")
    statement = (
        select(Opportunity, PipelineStage.name)
        .join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
        .where(
            Opportunity.organization_id == principal.organization_id,
            Opportunity.account_id == account_id,
            Opportunity.deleted_at.is_(None),
        )
        .order_by(Opportunity.created_at.desc())
        .limit(MAX_OPPORTUNITIES)
    )
    predicate = visibility.filter_for(Opportunity)
    if predicate is not None:
        statement = statement.where(predicate)
    lines: list[str] = []
    for opportunity, stage_name in (await session.execute(statement)).all():
        parts = [f"- {opportunity.name}", f"stage {stage_name}"]
        if opportunity.deal_value is not None:
            parts.append(format_money(opportunity.deal_value))
        if opportunity.win_probability is not None:
            parts.append(f"{opportunity.win_probability}% to win")
        if opportunity.expected_close_date is not None:
            parts.append(f"expected {opportunity.expected_close_date.isoformat()}")
        if opportunity.won_at is not None:
            parts.append("WON")
        elif opportunity.lost_at is not None:
            parts.append("LOST")
        lines.append(" — ".join(parts))
    return lines


async def _stage_name(session: AsyncSession, stage_id: uuid.UUID) -> str | None:
    result = await session.execute(select(PipelineStage.name).where(PipelineStage.id == stage_id))
    return result.scalar_one_or_none()


async def _account_name(session: AsyncSession, account_id: uuid.UUID) -> str | None:
    result = await session.execute(select(Account.name).where(Account.id == account_id))
    return result.scalar_one_or_none()


async def _contact_line(session: AsyncSession, contact_id: uuid.UUID) -> str | None:
    result = await session.execute(
        select(Contact.first_name, Contact.last_name, Contact.job_title).where(
            Contact.id == contact_id
        )
    )
    row = result.one_or_none()
    if row is None:
        return None
    first_name, last_name, job_title = row
    name = f"{first_name} {last_name}".strip()
    return f"- {name}" + (f" — {job_title}" if job_title else "")


async def _lead_source_name(session: AsyncSession, source_id: uuid.UUID | None) -> str | None:
    if source_id is None:
        return None
    result = await session.execute(select(LeadSource.name).where(LeadSource.id == source_id))
    return result.scalar_one_or_none()


def entity_id_or_none(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


__all__ = [
    "MAX_CONTACTS",
    "MAX_OPPORTUNITIES",
    "MAX_TIMELINE_ENTRIES",
    "CrmContext",
    "build_account_context",
    "build_lead_context",
    "build_opportunity_context",
    "entity_id_or_none",
]
