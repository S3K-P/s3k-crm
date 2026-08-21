"""Contact business rules (plan P2-W12).

Two rules beyond generic CRUD:

* **Primary contact is exactly one per account** (P2-W12-BE-03). Promoting a
  contact demotes the incumbent, in the same transaction, so the invariant
  cannot be observed broken.
* **Duplicate email warns rather than blocks** (P2-W12-BE-04), matching the
  account duplicate-name rule and decision C03 — the caller re-submits with
  ``allow_duplicate``.

``account_id`` is validated against the caller's organization before it is
written: a contact must never be attachable to another tenant's account.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.products.crm.accounts.models import Account
from app.products.crm.contacts.models import Contact, ContactStatus
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.shared.visibility import RecordVisibility


class DuplicateContactEmailError(ConflictError):
    """Another contact in this organization already uses that address."""

    code = "duplicate_contact_email"
    message = (
        "A contact with that email already exists. Re-submit with allow_duplicate to proceed."
    )


class ContactService(TenantScopedService[Contact]):
    entity_name = "Contact"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Contact), Contact)
        self._session = session

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        status: ContactStatus | None = None,
        account_id: uuid.UUID | None = None,
        owner_id: uuid.UUID | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Contact.first_name).like(term),
                    func.lower(Contact.last_name).like(term),
                    func.lower(func.coalesce(Contact.email, "")).like(term),
                    func.lower(func.coalesce(Contact.job_title, "")).like(term),
                )
            )
        if status is not None:
            filters.append(Contact.status == status)
        if account_id is not None:
            filters.append(Contact.account_id == account_id)
        if owner_id is not None:
            filters.append(Contact.owner_id == owner_id)
        return filters

    async def list_contacts(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
        visibility: RecordVisibility | None = None,
    ) -> tuple[Sequence[Contact], int]:
        return await self.list(
            organization_id, params=params, filters=filters, visibility=visibility
        )

    async def exists(self, contact_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
        """Existence check other CRM modules use when handed a contact id."""
        return await self._repository.exists(contact_id, organization_id)

    # --- Commands ----------------------------------------------------------

    async def create_contact(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
        allow_duplicate: bool = False,
    ) -> Contact:
        """Create a contact, optionally promoting it to primary on its account."""
        payload = dict(values)
        make_primary = bool(payload.pop("is_primary", False))

        account_id = payload.get("account_id")
        if account_id is not None:
            await self._require_account(account_id, organization_id)

        email = payload.get("email")
        if email and not allow_duplicate and await self._email_exists(organization_id, str(email)):
            raise DuplicateContactEmailError

        contact = await self.create(
            organization_id=organization_id, actor_id=actor_id, values=payload
        )

        if make_primary and contact.account_id is not None:
            await self.set_primary(contact, actor_id=actor_id)
        return contact

    async def update_contact(
        self,
        contact: Contact,
        *,
        actor_id: uuid.UUID | None,
        values: dict[str, Any],
        allow_duplicate: bool = False,
    ) -> Contact:
        """Patch a contact, re-validating any account move and email change."""
        payload = dict(values)
        make_primary = payload.pop("is_primary", None)

        if "account_id" in payload and payload["account_id"] is not None:
            await self._require_account(payload["account_id"], contact.organization_id)

        email = payload.get("email")
        if (
            email
            and str(email).lower() != (contact.email or "").lower()
            and not allow_duplicate
            and await self._email_exists(contact.organization_id, str(email))
        ):
            raise DuplicateContactEmailError

        updated = await self.update(contact, actor_id=actor_id, values=payload)

        if make_primary is True and updated.account_id is not None:
            await self.set_primary(updated, actor_id=actor_id)
        return updated

    async def set_primary(self, contact: Contact, *, actor_id: uuid.UUID | None) -> Contact:
        """Make ``contact`` the primary contact of its account.

        The demotion is a single UPDATE against the account row rather than a
        flag on the contact, because ``accounts.primary_contact_id`` is where
        the relationship actually lives — so "exactly one" is structural, not
        something two rows have to agree about.

        Raises:
            NotFoundError: the contact has no account to be primary of.
        """
        if contact.account_id is None:
            raise NotFoundError("This contact is not attached to an account.")

        await self._session.execute(
            update(Account)
            .where(
                Account.id == contact.account_id,
                Account.organization_id == contact.organization_id,
            )
            .values(primary_contact_id=contact.id, updated_by_id=actor_id)
        )
        await self._session.flush()
        return contact

    async def is_primary(self, contact: Contact) -> bool:
        """Whether this contact is its account's primary contact."""
        if contact.account_id is None:
            return False
        result = await self._session.execute(
            select(Account.primary_contact_id).where(
                Account.id == contact.account_id,
                Account.organization_id == contact.organization_id,
            )
        )
        return result.scalar_one_or_none() == contact.id

    async def archive_contact(
        self, contact: Contact, *, actor_id: uuid.UUID | None
    ) -> Contact:
        """Soft-delete a contact, clearing it from its account first.

        Leaving ``accounts.primary_contact_id`` pointing at an archived row
        would make the account's detail page resolve a record the API no
        longer returns.
        """
        if contact.account_id is not None and await self.is_primary(contact):
            await self._session.execute(
                update(Account)
                .where(
                    Account.id == contact.account_id,
                    Account.organization_id == contact.organization_id,
                )
                .values(primary_contact_id=None, updated_by_id=actor_id)
            )
        return await self.soft_delete(contact, actor_id=actor_id)

    # --- Internals ---------------------------------------------------------

    async def _require_account(
        self, account_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        """Reject an account id that is not in the caller's organization."""
        result = await self._session.execute(
            select(Account.id).where(
                Account.id == account_id,
                Account.organization_id == organization_id,
                Account.deleted_at.is_(None),
            )
        )
        if result.scalar_one_or_none() is None:
            raise NotFoundError("Account not found.")

    async def _email_exists(self, organization_id: uuid.UUID, email: str) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(Contact)
            .where(
                Contact.organization_id == organization_id,
                Contact.deleted_at.is_(None),
                func.lower(Contact.email) == email.lower(),
            )
        )
        return int(result.scalar_one()) > 0


__all__ = ["ContactService", "DuplicateContactEmailError"]
