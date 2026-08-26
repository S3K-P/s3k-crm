"""Account business rules.

Beyond generic CRUD this enforces two rules from the plan (P2-W11-BE-03/04):

* duplicate names inside an organization are **warned about, not blocked**
  (decision C03) — the caller re-submits with ``allow_duplicate=true``;
* an account with open opportunities cannot be archived, because doing so would
  orphan live pipeline.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.products.crm.accounts.models import Account, AccountStatus
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
    ) -> tuple[Sequence[Account], int]:
        return await self.list(
            organization_id, params=params, filters=filters, visibility=visibility
        )

    async def exists(self, account_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Whether the account exists **in this organization**.

        The public existence check other CRM modules use when validating a
        foreign key they were handed, so they never reach into this module's
        repository.
        """
        return await self._repository.exists(account_id, organization_id)

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
        return await self.create(
            organization_id=organization_id, actor_id=actor_id, values=values
        )

    async def archive_account(
        self, account: Account, *, actor_id: uuid.UUID | None
    ) -> Account:
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
