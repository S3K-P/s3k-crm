"""Turning a CRM account into context the model can use (§7).

Three rules govern everything in this file.

**Permission-filtered, per module.** A caller who cannot read contacts must not
learn about contacts by asking the AI instead of opening the contacts screen.
Each section is gated on the caller's own permission for the module it comes
from, and record-level visibility is applied to the query — not to the result
— so an out-of-scope row is never fetched.

**Read-only.** Nothing here writes. Market Insights is an intelligence layer;
external findings never overwrite the account record.

**Clearly labelled as CRM.** The block is fenced and introduced as internal CRM
data, and the system prompt instructs the model to attribute it as such. The
user has to be able to tell "we already have three open deals here" (our
record) from "they raised a Series B in March" (the web) — §7 requires the
distinction and the interface repeats it.

Personal contact details are deliberately narrow: names, job titles and
counts, never email addresses or phone numbers. The model does not need them
to reason about an account, and sending them to a third-party API because they
happened to be nearby is not a trade worth making.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.dependencies import Principal
from app.platform.authorization.service import Action as PermissionAction
from app.products.crm.accounts.models import Account
from app.products.crm.contacts.models import Contact
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.shared.visibility import RecordVisibility

#: Caps on how much of the record travels. A long tail of stale rows crowds
#: out the research itself and costs tokens on every follow-up question.
MAX_CONTACTS = 8
MAX_OPPORTUNITIES = 8


@dataclass(frozen=True, slots=True)
class CrmContext:
    """Rendered CRM context, plus what it was allowed to include."""

    #: Markdown, ready to embed. Empty when nothing was readable.
    text: str
    #: Module names actually included, for the "what the AI saw" disclosure.
    sections: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


async def build_crm_context(
    session: AsyncSession, *, account: Account, principal: Principal
) -> CrmContext:
    """Describe ``account`` for the model, within the caller's permissions.

    Args:
        session: the request's session.
        account: an account already resolved through ``AccountService``, so
            organization ownership and record visibility are established.
        principal: the caller, carrying the permission snapshot resolved by
            ``require_permission``.

    Returns:
        A :class:`CrmContext`. The account section is always present — the
        caller demonstrably holds ``accounts.VIEW``, since that is how they
        reached this account — and contacts and opportunities appear only if
        their own module permission allows.
    """
    lines: list[str] = ["## Account record", "", *_account_lines(account)]
    sections: list[str] = ["accounts"]

    if principal.has_permission("contacts", PermissionAction.VIEW):
        contacts = await _contacts(session, account=account, principal=principal)
        if contacts:
            sections.append("contacts")
            lines += ["", "## Known contacts", ""]
            lines += contacts

    if principal.has_permission("opportunities", PermissionAction.VIEW):
        opportunities = await _opportunities(session, account=account, principal=principal)
        if opportunities:
            sections.append("opportunities")
            lines += ["", "## Open and recent opportunities", ""]
            lines += opportunities

    return CrmContext(text="\n".join(lines).strip(), sections=tuple(sections))


def _account_lines(account: Account) -> list[str]:
    """The account's own fields, skipping the ones nobody filled in.

    Empty fields are omitted rather than rendered as "Industry: None". A model
    reads a page of nulls as a signal about the company rather than about the
    CRM record, and the resulting report hedges for no reason.
    """
    fields: list[tuple[str, object | None]] = [
        ("Name", account.name),
        ("Industry", account.industry),
        ("Website", account.website),
        ("Company size", account.company_size),
        ("Annual revenue", account.annual_revenue),
        ("Status", account.status.value),
        ("Health score", account.health_score),
        ("Source", account.source),
        (
            "Location",
            ", ".join(
                part
                for part in (account.city, account.state, account.country)
                if part
            )
            or None,
        ),
        ("Description", account.description),
    ]
    return [f"- {label}: {value}" for label, value in fields if value not in (None, "")]


async def _contacts(
    session: AsyncSession, *, account: Account, principal: Principal
) -> list[str]:
    """Names and roles of contacts at this account the caller may read."""
    visibility = RecordVisibility.for_module(principal, "contacts")
    statement = (
        select(Contact)
        .where(
            Contact.organization_id == account.organization_id,
            Contact.account_id == account.id,
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
        # Email and phone are intentionally not included — see module docstring.
        lines.append(f"- {name}" + (f" — {role}" if role else ""))
    return lines


async def _opportunities(
    session: AsyncSession, *, account: Account, principal: Principal
) -> list[str]:
    """Pipeline on this account, with stage names resolved."""
    visibility = RecordVisibility.for_module(principal, "opportunities")
    statement = (
        select(Opportunity, PipelineStage.name)
        .join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
        .where(
            Opportunity.organization_id == account.organization_id,
            Opportunity.account_id == account.id,
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
            parts.append(f"{opportunity.currency} {opportunity.deal_value:,.0f}")
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


def account_id_or_none(value: str | None) -> uuid.UUID | None:
    """Parse an optional account id, treating a malformed one as absent."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


__all__ = [
    "MAX_CONTACTS",
    "MAX_OPPORTUNITIES",
    "CrmContext",
    "account_id_or_none",
    "build_crm_context",
]
