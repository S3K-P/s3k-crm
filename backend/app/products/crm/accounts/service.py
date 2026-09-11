"""Account business rules.

Beyond generic CRUD this enforces two rules from the plan (P2-W11-BE-03/04):

* duplicate names inside an organization are **warned about, not blocked**
  (decision C03) — the caller re-submits with ``allow_duplicate=true``;
* an account with open opportunities cannot be archived, because doing so would
  orphan live pipeline.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.platform.auth.dependencies import Principal
from app.products.crm.accounts.models import Account, AccountStatus
from app.products.crm.accounts.overview import (
    AccountOverview,
    AccountOverviewRepository,
    TimelineEntry,
    merge_timeline_entries,
)
from app.products.crm.common import CrmEntityType
from app.products.crm.opportunities.models import Opportunity
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.shared.visibility import RecordVisibility


class DuplicateAccountError(ConflictError):
    """An account with the same name already exists in this organization."""

    code = "duplicate_account"
    message = "An account with that name already exists. Re-submit with allow_duplicate to proceed."


class AccountInUseError(ConflictError):
    """The account still has open opportunities."""

    code = "account_has_open_opportunities"
    message = "This account cannot be archived while it has open opportunities."


class AccountService(TenantScopedService[Account]):
    entity_name = "Account"
    #: Opts this entity into tenant-defined fields (Phase E). Declaring it
    #: is the whole wiring: the base class validates and merges
    #: ``custom_fields`` on every create and update from here on.
    crm_entity_type = CrmEntityType.ACCOUNT

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Account), Account)
        self._session = session

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        status: AccountStatus | None = None,
        industry: str | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> list[ColumnElement[bool]]:
        """Translate query parameters into SQL predicates."""
        filters: list[ColumnElement[bool]] = []
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(func.lower(Account.name).like(term))
        if status is not None:
            filters.append(Account.status == status)
        if industry:
            filters.append(Account.industry == industry)
        if owner_id is not None:
            filters.append(Account.owner_id == owner_id)
        return filters

    async def list_accounts(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
        visibility: RecordVisibility | None = None,
        sort_column: ColumnElement[Any] | None = None,
    ) -> tuple[Sequence[Account], int]:
        return await self.list(
            organization_id,
            params=params,
            filters=filters,
            visibility=visibility,
            sort_column=sort_column,
        )

    async def exists(self, account_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Whether the account exists **in this organization**.

        The public existence check other CRM modules use when validating a
        foreign key they were handed, so they never reach into this module's
        repository.
        """
        return await self._repository.exists(account_id, organization_id)

    async def overview(self, account: Account, principal: Principal) -> AccountOverview:
        """The Account 360 summary: real aggregates, each scoped exactly as
        the underlying list endpoint would scope it for this caller (§13) —
        a custom role holding ``opportunities.VIEW_ALL`` but not
        ``contacts.VIEW_ALL`` must see every deal and only their own contacts.
        """
        repo = AccountOverviewRepository(self._session)
        contacts_visibility = RecordVisibility.for_module(principal, "contacts")
        opportunities_visibility = RecordVisibility.for_module(principal, "opportunities")
        tasks_visibility = RecordVisibility.for_module(principal, "tasks")

        contacts_count = await repo.contacts_count(
            account.id, account.organization_id, contacts_visibility
        )
        (
            open_count,
            open_value,
            open_currencies,
            won_count,
            won_value,
            won_currencies,
        ) = await repo.deal_summary(account.id, account.organization_id, opportunities_visibility)
        open_tasks = await repo.open_tasks_count(
            account.id, account.organization_id, tasks_visibility
        )
        last_activity = await repo.activity_entries(account.id, account.organization_id, limit=1)
        owner_name = await repo.owner_name(account.organization_id, account.owner_id)
        primary_contact = await repo.primary_contact(
            account.organization_id, account.primary_contact_id
        )
        meeting = await repo.next_meeting(
            account.id, account.organization_id, now=dt.datetime.now(dt.UTC)
        )

        return AccountOverview(
            contacts_count=contacts_count,
            open_deals_count=open_count,
            open_pipeline_value=open_value,
            # A single currency in play is named; several have no one symbol,
            # and picking one would misstate the sum (dashboard/service.py
            # makes the same call for the org-wide figure).
            open_pipeline_currency=open_currencies[0] if len(open_currencies) == 1 else None,
            won_deals_count=won_count,
            won_revenue=won_value,
            won_revenue_currency=won_currencies[0] if len(won_currencies) == 1 else None,
            open_tasks_count=open_tasks,
            last_activity_at=last_activity[0].occurred_at if last_activity else None,
            next_meeting_id=meeting[0] if meeting else None,
            next_meeting_title=meeting[1] if meeting else None,
            next_meeting_at=meeting[2] if meeting else None,
            owner_name=owner_name,
            primary_contact_name=primary_contact.full_name if primary_contact else None,
            primary_contact_title=primary_contact.job_title if primary_contact else None,
        )

    async def timeline(
        self, account: Account, principal: Principal, *, limit: int = 50
    ) -> list[TimelineEntry]:
        """Every event this caller may see against this account, newest first."""
        repo = AccountOverviewRepository(self._session)
        contacts_visibility = RecordVisibility.for_module(principal, "contacts")
        opportunities_visibility = RecordVisibility.for_module(principal, "opportunities")
        tasks_visibility = RecordVisibility.for_module(principal, "tasks")

        activities = await repo.activity_entries(account.id, account.organization_id)
        deals_created = await repo.deal_created_entries(
            account.id, account.organization_id, opportunities_visibility
        )
        stage_changes = await repo.stage_changed_entries(
            account.id, account.organization_id, opportunities_visibility
        )
        contacts_created = await repo.contact_created_entries(
            account.id, account.organization_id, contacts_visibility
        )
        tasks = await repo.task_entries(account.id, account.organization_id, tasks_visibility)
        emails = await repo.email_entries(account.id, account.organization_id, principal.user_id)
        notes = await repo.note_entries(account.id, account.organization_id, principal.user_id)
        return merge_timeline_entries(
            activities,
            deals_created,
            stage_changes,
            contacts_created,
            tasks,
            emails,
            notes,
            limit=limit,
        )

    # --- Commands ----------------------------------------------------------

    async def create_account(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, object],
        allow_duplicate: bool = False,
    ) -> Account:
        """Create an account, warning on a duplicate name unless overridden."""
        name = str(values.get("name", "")).strip()
        if not allow_duplicate and await self._name_exists(organization_id, name):
            raise DuplicateAccountError
        return await self.create(organization_id=organization_id, actor_id=actor_id, values=values)

    async def archive_account(self, account: Account, *, actor_id: uuid.UUID | None) -> Account:
        """Soft-delete an account once nothing live depends on it."""
        if await self._open_opportunity_count(account) > 0:
            raise AccountInUseError
        return await self.soft_delete(account, actor_id=actor_id)

    # --- Internals ---------------------------------------------------------

    async def _name_exists(self, organization_id: uuid.UUID, name: str) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(Account)
            .where(
                Account.organization_id == organization_id,
                Account.deleted_at.is_(None),
                func.lower(Account.name) == name.lower(),
            )
        )
        return int(result.scalar_one()) > 0

    async def _open_opportunity_count(self, account: Account) -> int:
        """Opportunities on this account that are neither won nor lost."""
        result = await self._session.execute(
            select(func.count())
            .select_from(Opportunity)
            .where(
                Opportunity.organization_id == account.organization_id,
                Opportunity.account_id == account.id,
                Opportunity.deleted_at.is_(None),
                Opportunity.won_at.is_(None),
                Opportunity.lost_at.is_(None),
            )
        )
        return int(result.scalar_one())


__all__ = ["AccountInUseError", "AccountService", "DuplicateAccountError"]
