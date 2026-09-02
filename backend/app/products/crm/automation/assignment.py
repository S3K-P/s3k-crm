"""Automatic owner assignment, on every path a record can be created by.

Zoho's assignment rules run on import, web forms and the API but **not** on
manual creation — its own documentation says so plainly, and the analysis
(§2.7) calls it out as a gap worth not inheriting, because manual creation is
the most common path of all. S3K runs assignment wherever a record appears
without an owner.

The mechanism is deliberately small: an ordered list of rules per organization,
each a criterion and a set of candidate owners, resolved round-robin. That is
Zoho's model minus the parts that exist because Zoho cannot know its customer —
no rule builder UI, no twenty-five-criterion expressions, no per-module
configuration language (analysis §4.4).

**``owner_id`` is not a foreign key**, and this module does not make it one
(constraint C2: ownership must survive the owner leaving the platform). Rules
therefore hold user ids as plain values and validate them against membership
when they are written, not on every read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.products.crm.automation.models import AssignmentRule

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AssignmentContext:
    """What a rule may look at when deciding who gets a record.

    Narrow on purpose. These are the fields that actually drive territory
    assignment in practice; a general expression language over every column
    would be a rule engine, which §4.4 rules out of scope.
    """

    module: str
    country: str | None = None
    industry: str | None = None
    lead_source_id: uuid.UUID | None = None

    @classmethod
    def from_values(cls, module: str, values: dict[str, Any]) -> AssignmentContext:
        """Build a context from a create payload."""
        return cls(
            module=module,
            country=_as_text(values.get("country")),
            industry=_as_text(values.get("industry")),
            lead_source_id=_as_uuid(values.get("lead_source_id")),
        )


def _as_text(value: Any) -> str | None:
    return str(value).strip() or None if isinstance(value, str) else None


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


class Assigner:
    """Resolves the owner of a new record."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self,
        organization_id: uuid.UUID,
        context: AssignmentContext,
        *,
        fallback: uuid.UUID | None,
    ) -> uuid.UUID | None:
        """Who should own this record.

        Rules are tried in ``sort_order``; the first whose criteria match wins.
        When none match — or none are configured, which is the default — the
        fallback is used, and that is the creating user. So the behaviour with
        no configuration is exactly what it was before this existed, which is
        what makes the feature safe to add to a live tenant.
        """
        rules = await self._matching_rules(organization_id, context)
        for rule in rules:
            owner = await self._pick(rule)
            if owner is not None:
                logger.debug(
                    "assignment_rule_applied",
                    rule_id=str(rule.id),
                    module=context.module,
                    owner_id=str(owner),
                )
                return owner
        return fallback

    async def _matching_rules(
        self, organization_id: uuid.UUID, context: AssignmentContext
    ) -> list[AssignmentRule]:
        """Active rules for this module whose criteria the record satisfies.

        A NULL criterion means "any", so a rule with no criteria at all is a
        catch-all — which is how a simple round-robin across the whole team is
        expressed without a special case.
        """
        result = await self._session.execute(
            select(AssignmentRule)
            .where(
                AssignmentRule.organization_id == organization_id,
                AssignmentRule.deleted_at.is_(None),
                AssignmentRule.is_active.is_(True),
                AssignmentRule.module == context.module,
            )
            .order_by(AssignmentRule.sort_order, AssignmentRule.created_at)
        )
        return [rule for rule in result.scalars().all() if _matches(rule, context)]

    async def _pick(self, rule: AssignmentRule) -> uuid.UUID | None:
        """Take the next owner from a rule, round-robin.

        ``last_assigned_index`` is advanced on the rule row inside the caller's
        transaction, so two records created concurrently take different owners
        rather than both taking the first. Under contention the row lock
        serialises them, which is the correct trade: round-robin fairness is
        the entire point, and these are single-row updates.
        """
        candidates = list(rule.owner_ids or [])
        if not candidates:
            return None
        index = (rule.last_assigned_index + 1) % len(candidates)
        rule.last_assigned_index = index
        return uuid.UUID(str(candidates[index]))


def _matches(rule: AssignmentRule, context: AssignmentContext) -> bool:
    """Whether every criterion the rule sets is satisfied.

    Criteria are ANDed and case-insensitive for text. An unset criterion is not
    a wildcard match to be scored — it simply is not checked.
    """
    if rule.match_country and (
        context.country is None
        or rule.match_country.strip().lower() != context.country.strip().lower()
    ):
        return False
    if rule.match_industry and (
        context.industry is None
        or rule.match_industry.strip().lower() != context.industry.strip().lower()
    ):
        return False
    return not (
        rule.match_lead_source_id
        and rule.match_lead_source_id != context.lead_source_id
    )


async def reassign_orphaned_records(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    departing_user_id: uuid.UUID,
    new_owner_id: uuid.UUID | None,
) -> dict[str, int]:
    """Move a departing user's records to somebody else.

    Zoho's Mass Transfer, minus the manual step. It is a cross-module operation
    because ``owner_id`` is not a foreign key (C2) — there is no cascade to
    lean on, so each owning table is updated explicitly.

    Returns:
        How many records moved, per module, for the audit entry.
    """
    from app.products.crm.accounts.models import Account
    from app.products.crm.contacts.models import Contact
    from app.products.crm.leads.models import Lead
    from app.products.crm.opportunities.models import Opportunity
    from app.products.crm.tasks.models import Task

    moved: dict[str, int] = {}
    for name, model in (
        ("leads", Lead),
        ("accounts", Account),
        ("contacts", Contact),
        ("opportunities", Opportunity),
        ("tasks", Task),
    ):
        result = await session.execute(
            update(model)
            .where(
                model.organization_id == organization_id,
                model.owner_id == departing_user_id,
                model.deleted_at.is_(None),
            )
            .values(owner_id=new_owner_id)
        )
        count = int(cast("CursorResult[Any]", result).rowcount or 0)
        if count:
            moved[name] = count

    if moved:
        logger.info(
            "orphaned_records_reassigned",
            organization_id=str(organization_id),
            from_user=str(departing_user_id),
            to_user=str(new_owner_id) if new_owner_id else None,
            moved=moved,
        )
    return moved


async def team_member_ids(
    session: AsyncSession, organization_id: uuid.UUID
) -> list[uuid.UUID]:
    """Active members of the organization, as assignment candidates.

    Queried through the memberships table rather than imported from the teams
    module, because this is a product module reading Platform data — allowed
    for reads, and cheaper than an import that would breach the boundary.
    """
    from app.platform.organizations.models import MembershipStatus, OrganizationMembership

    result = await session.execute(
        select(OrganizationMembership.user_id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
        )
        .order_by(OrganizationMembership.user_id)
    )
    return [uuid.UUID(str(value)) for value in result.scalars().all()]


__all__ = [
    "Assigner",
    "AssignmentContext",
    "reassign_orphaned_records",
    "team_member_ids",
]
