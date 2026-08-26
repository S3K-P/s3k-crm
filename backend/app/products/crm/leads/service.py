"""Lead business rules: the status state machine and conversion.

Two workflows from the plan live here:

* **Lifecycle** (P2-W13-BE-03) — status changes are restricted to the legal
  transitions in :data:`LEAD_TRANSITIONS`. Encoding it as data rather than as
  branching keeps it inspectable and testable.
* **Conversion** (P2-W14) — a qualified lead becomes an Account, a Contact and
  optionally an Opportunity, in one transaction.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import structlog
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.platform.audit.service import Action as AuditAction
from app.products.crm.accounts.models import Account
from app.products.crm.contacts.models import Contact
from app.products.crm.leads.models import Lead, LeadStatus
from app.products.crm.opportunities.models import Opportunity, PipelineStage
from app.products.crm.shared.pagination import PageParams
from app.products.crm.shared.repository import TenantScopedRepository
from app.products.crm.shared.service import TenantScopedService
from app.products.crm.shared.visibility import RecordVisibility

logger = structlog.get_logger(__name__)

#: Legal status moves. A lead may always be marked LOST or UNQUALIFIED from
#: an open stage; CONVERTED is reachable only through :meth:`LeadService.convert`,
#: never by a direct status edit, so it is absent from every source list here.
LEAD_TRANSITIONS: dict[LeadStatus, frozenset[LeadStatus]] = {
    LeadStatus.NEW: frozenset(
        {LeadStatus.CONTACTED, LeadStatus.UNQUALIFIED, LeadStatus.LOST}
    ),
    LeadStatus.CONTACTED: frozenset(
        {LeadStatus.QUALIFIED, LeadStatus.UNQUALIFIED, LeadStatus.LOST}
    ),
    LeadStatus.QUALIFIED: frozenset(
        {LeadStatus.PROPOSAL_SENT, LeadStatus.UNQUALIFIED, LeadStatus.LOST}
    ),
    LeadStatus.PROPOSAL_SENT: frozenset(
        {LeadStatus.NEGOTIATION, LeadStatus.UNQUALIFIED, LeadStatus.LOST}
    ),
    LeadStatus.NEGOTIATION: frozenset({LeadStatus.UNQUALIFIED, LeadStatus.LOST}),
    # Terminal / near-terminal states.
    LeadStatus.UNQUALIFIED: frozenset({LeadStatus.CONTACTED}),  # re-open
    LeadStatus.CONVERTED: frozenset(),
    LeadStatus.LOST: frozenset({LeadStatus.CONTACTED}),  # re-open a lost lead
}

#: A lead must have reached at least this far before it can be converted.
CONVERTIBLE_FROM: frozenset[LeadStatus] = frozenset(
    {LeadStatus.QUALIFIED, LeadStatus.PROPOSAL_SENT, LeadStatus.NEGOTIATION}
)


class InvalidLeadTransitionError(ValidationFailedError):
    """The requested status change is not permitted from the current status."""

    code = "invalid_lead_transition"


class LeadAlreadyConvertedError(ConflictError):
    """The lead has already been converted."""

    code = "lead_already_converted"
    message = "This lead has already been converted."


class LeadNotConvertibleError(ValidationFailedError):
    """The lead is not far enough through the pipeline to convert."""

    code = "lead_not_convertible"
    message = "Only a qualified lead can be converted."


class DuplicateLeadEmailError(ConflictError):
    """Another open lead in this organization already uses that address."""

    code = "duplicate_lead_email"
    message = (
        "An open lead with that email already exists. Re-submit with allow_duplicate to proceed."
    )


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """What a conversion produced."""

    lead: Lead
    account: Account
    contact: Contact
    opportunity: Opportunity | None


@dataclass(frozen=True, slots=True)
class ConversionSuggestions:
    """Existing records the convert UI can link instead of recreating."""

    matching_accounts: tuple[Account, ...]
    matching_contacts: tuple[Contact, ...]
    suggested_account_name: str
    suggested_contact_name: str
    suggested_opportunity_name: str
    suggested_deal_value: Decimal | None


class LeadService(TenantScopedService[Lead]):
    entity_name = "Lead"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TenantScopedRepository(session, Lead), Lead)
        self._session = session

    # --- Queries -----------------------------------------------------------

    def build_filters(
        self,
        *,
        search: str | None = None,
        status: LeadStatus | None = None,
        owner_id: uuid.UUID | None = None,
        lead_source_id: uuid.UUID | None = None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if search:
            term = f"%{search.strip().lower()}%"
            filters.append(
                or_(
                    func.lower(Lead.first_name).like(term),
                    func.lower(Lead.last_name).like(term),
                    func.lower(func.coalesce(Lead.company, "")).like(term),
                    func.lower(func.coalesce(Lead.email, "")).like(term),
                )
            )
        if status is not None:
            filters.append(Lead.status == status)
        if owner_id is not None:
            filters.append(Lead.owner_id == owner_id)
        if lead_source_id is not None:
            filters.append(Lead.lead_source_id == lead_source_id)
        return filters

    async def list_leads(
        self,
        organization_id: uuid.UUID,
        *,
        params: PageParams,
        filters: Sequence[ColumnElement[bool]] = (),
        visibility: RecordVisibility | None = None,
    ) -> tuple[Sequence[Lead], int]:
        return await self.list(
            organization_id, params=params, filters=filters, visibility=visibility
        )

    async def create_lead(
        self,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        values: dict[str, object],
        allow_duplicate: bool = False,
    ) -> Lead:
        """Create a lead, warning on a duplicate email unless overridden."""
        email = values.get("email")
        if (
            email
            and not allow_duplicate
            and await self._open_email_exists(organization_id, str(email))
        ):
            raise DuplicateLeadEmailError
        return await self.create(
            organization_id=organization_id, actor_id=actor_id, values=values
        )

    async def conversion_suggestions(
        self, lead: Lead
    ) -> ConversionSuggestions:
        """Find existing accounts/contacts the convert UI should offer to link."""
        account_name = (lead.company or lead.full_name).strip()
        accounts = await self._find_accounts_by_name(lead.organization_id, account_name)
        contacts: list[Contact] = []
        seen: set[uuid.UUID] = set()
        if lead.email:
            for contact in await self._find_contacts_by_email(
                lead.organization_id, str(lead.email)
            ):
                if contact.id not in seen:
                    contacts.append(contact)
                    seen.add(contact.id)
        if lead.phone:
            for contact in await self._find_contacts_by_phone(
                lead.organization_id, lead.phone
            ):
                if contact.id not in seen:
                    contacts.append(contact)
                    seen.add(contact.id)
        return ConversionSuggestions(
            matching_accounts=accounts,
            matching_contacts=tuple(contacts),
            suggested_account_name=account_name,
            suggested_contact_name=lead.full_name,
            suggested_opportunity_name=f"{account_name} — new opportunity",
            suggested_deal_value=lead.expected_deal_size,
        )

    # --- Conversion --------------------------------------------------------

    async def convert(
        self,
        lead: Lead,
        *,
        actor_id: uuid.UUID | None,
        account_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        create_opportunity: bool = True,
        opportunity_name: str | None = None,
        opportunity_value: Decimal | None = None,
        stage_id: uuid.UUID | None = None,
        expected_close_date: dt.date | None = None,
    ) -> ConversionResult:
        """Turn a qualified lead into an account, a contact and maybe a deal.

        ``account_id`` / ``contact_id`` attach to existing records. When omitted,
        an exact name/email match in the organization is reused automatically so
        conversion never silently duplicates. Everything happens in the caller's
        transaction.

        Raises:
            LeadAlreadyConvertedError: the lead was converted previously.
            LeadNotConvertibleError: the lead has not been qualified.
            NotFoundError: an explicit id is not in this organization.
        """
        if lead.status is LeadStatus.CONVERTED or lead.converted_at is not None:
            raise LeadAlreadyConvertedError
        if lead.status not in CONVERTIBLE_FROM:
            raise LeadNotConvertibleError(
                details={
                    "status": lead.status.value,
                    "convertible_from": sorted(s.value for s in CONVERTIBLE_FROM),
                }
            )

        organization_id = lead.organization_id
        now = dt.datetime.now(dt.UTC)

        account = await self._resolve_account(
            lead, account_id=account_id, actor_id=actor_id, organization_id=organization_id
        )
        contact = await self._resolve_contact(
            lead,
            account=account,
            contact_id=contact_id,
            actor_id=actor_id,
            organization_id=organization_id,
        )

        if account.primary_contact_id is None:
            account.primary_contact_id = contact.id

        opportunity: Opportunity | None = None
        if create_opportunity:
            opportunity = await self._create_opportunity(
                lead,
                account=account,
                contact=contact,
                actor_id=actor_id,
                name=opportunity_name,
                value=opportunity_value,
                stage_id=stage_id,
                expected_close_date=expected_close_date,
            )

        lead.status = LeadStatus.CONVERTED
        lead.converted_at = now
        lead.converted_account_id = account.id
        lead.converted_contact_id = contact.id
        lead.converted_opportunity_id = opportunity.id if opportunity else None
        lead.updated_by_id = actor_id
        await self._session.flush()

        logger.info(
            "lead_converted",
            lead_id=str(lead.id),
            organization_id=str(organization_id),
            account_id=str(account.id),
            contact_id=str(contact.id),
            opportunity_id=str(opportunity.id) if opportunity else None,
        )

        # Conversion creates up to three records in one transaction, and the
        # generic CREATED entries for those do not say what caused them. This
        # is the record that ties the four together.
        await self.audit.record(
            organization_id=organization_id,
            action=AuditAction.LEAD_CONVERTED,
            module=self.audit_module,
            actor_id=actor_id,
            entity_type=self.audit_entity_type,
            entity_id=lead.id,
            entity_label=self.audit_label(lead),
            details={
                "account_id": account.id,
                "contact_id": contact.id,
                "opportunity_id": opportunity.id if opportunity else None,
            },
        )
        return ConversionResult(
            lead=lead, account=account, contact=contact, opportunity=opportunity
        )

    async def _resolve_account(
        self,
        lead: Lead,
        *,
        account_id: uuid.UUID | None,
        actor_id: uuid.UUID | None,
        organization_id: uuid.UUID,
    ) -> Account:
        """Attach to an existing account or create one from the lead."""
        if account_id is not None:
            result = await self._session.execute(
                select(Account).where(
                    Account.id == account_id,
                    Account.organization_id == organization_id,
                    Account.deleted_at.is_(None),
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise NotFoundError("Account not found.")
            return existing

        account_name = (lead.company or lead.full_name).strip()
        matches = await self._find_accounts_by_name(organization_id, account_name)
        if matches:
            return matches[0]

        account = Account(
            organization_id=organization_id,
            name=account_name,
            industry=lead.industry,
            website=lead.website,
            company_size=lead.company_size,
            owner_id=lead.owner_id,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def _resolve_contact(
        self,
        lead: Lead,
        *,
        account: Account,
        contact_id: uuid.UUID | None,
        actor_id: uuid.UUID | None,
        organization_id: uuid.UUID,
    ) -> Contact:
        """Attach to an existing contact or create one from the lead."""
        if contact_id is not None:
            result = await self._session.execute(
                select(Contact).where(
                    Contact.id == contact_id,
                    Contact.organization_id == organization_id,
                    Contact.deleted_at.is_(None),
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                raise NotFoundError("Contact not found.")
            # Keep the contact under the conversion account when it was orphaned
            # or still pointing at a different account — conversion is the
            # authoritative link for this journey.
            if existing.account_id != account.id:
                existing.account_id = account.id
                existing.updated_by_id = actor_id
                await self._session.flush()
            return existing

        if lead.email:
            matches = await self._find_contacts_by_email(organization_id, str(lead.email))
            if matches:
                contact = matches[0]
                if contact.account_id != account.id:
                    contact.account_id = account.id
                    contact.updated_by_id = actor_id
                    await self._session.flush()
                return contact

        if lead.phone:
            matches = await self._find_contacts_by_phone(organization_id, lead.phone)
            if matches:
                contact = matches[0]
                if contact.account_id != account.id:
                    contact.account_id = account.id
                    contact.updated_by_id = actor_id
                    await self._session.flush()
                return contact

        contact = Contact(
            organization_id=organization_id,
            account_id=account.id,
            first_name=lead.first_name,
            last_name=lead.last_name,
            email=lead.email,
            phone=lead.phone,
            owner_id=lead.owner_id,
            notes=lead.notes,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(contact)
        await self._session.flush()
        return contact

    async def _create_opportunity(
        self,
        lead: Lead,
        *,
        account: Account,
        contact: Contact,
        actor_id: uuid.UUID | None,
        name: str | None,
        value: Decimal | None,
        stage_id: uuid.UUID | None,
        expected_close_date: dt.date | None,
    ) -> Opportunity:
        resolved_stage_id = stage_id or await self._first_stage_id(lead.organization_id)
        if resolved_stage_id is None:
            raise ValidationFailedError(
                "No pipeline stage is configured for this organization.",
                details={"hint": "Create a pipeline and at least one stage first."},
            )

        opportunity = Opportunity(
            organization_id=lead.organization_id,
            name=name or f"{account.name} — new opportunity",
            account_id=account.id,
            primary_contact_id=contact.id,
            owner_id=lead.owner_id,
            stage_id=resolved_stage_id,
            deal_value=value if value is not None else lead.expected_deal_size,
            expected_close_date=expected_close_date,
            lead_source_id=lead.lead_source_id,
            products=lead.product_interest,
            notes=lead.notes,
            created_by_id=actor_id,
            updated_by_id=actor_id,
        )
        self._session.add(opportunity)
        await self._session.flush()
        return opportunity

    async def _first_stage_id(self, organization_id: uuid.UUID) -> uuid.UUID | None:
        """The earliest open stage of the organization's default pipeline."""
        result = await self._session.execute(
            select(PipelineStage.id)
            .where(
                PipelineStage.organization_id == organization_id,
                PipelineStage.deleted_at.is_(None),
                PipelineStage.is_won.is_(False),
                PipelineStage.is_lost.is_(False),
            )
            .order_by(PipelineStage.sort_order)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _find_accounts_by_name(
        self, organization_id: uuid.UUID, name: str
    ) -> tuple[Account, ...]:
        if not name.strip():
            return ()
        result = await self._session.execute(
            select(Account)
            .where(
                Account.organization_id == organization_id,
                Account.deleted_at.is_(None),
                func.lower(Account.name) == name.strip().lower(),
            )
            .order_by(Account.created_at.asc())
            .limit(10)
        )
        return tuple(result.scalars().all())

    async def _find_contacts_by_email(
        self, organization_id: uuid.UUID, email: str
    ) -> tuple[Contact, ...]:
        result = await self._session.execute(
            select(Contact)
            .where(
                Contact.organization_id == organization_id,
                Contact.deleted_at.is_(None),
                func.lower(Contact.email) == email.strip().lower(),
            )
            .order_by(Contact.created_at.asc())
            .limit(10)
        )
        return tuple(result.scalars().all())

    async def _find_contacts_by_phone(
        self, organization_id: uuid.UUID, phone: str
    ) -> tuple[Contact, ...]:
        """Match on digit-normalized phone so formatting differences still hit."""
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 7:
            return ()
        result = await self._session.execute(
            select(Contact)
            .where(
                Contact.organization_id == organization_id,
                Contact.deleted_at.is_(None),
                Contact.phone.is_not(None),
            )
            .order_by(Contact.created_at.asc())
            .limit(50)
        )
        matches = [
            contact
            for contact in result.scalars().all()
            if contact.phone
            and "".join(ch for ch in contact.phone if ch.isdigit()).endswith(digits[-10:])
        ]
        return tuple(matches[:10])

    async def _open_email_exists(self, organization_id: uuid.UUID, email: str) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(Lead)
            .where(
                Lead.organization_id == organization_id,
                Lead.deleted_at.is_(None),
                Lead.status.notin_(
                    (LeadStatus.CONVERTED, LeadStatus.LOST, LeadStatus.UNQUALIFIED)
                ),
                func.lower(Lead.email) == email.strip().lower(),
            )
        )
        return int(result.scalar_one()) > 0

    async def counts_by_status(self, organization_id: uuid.UUID) -> dict[str, int]:
        """Per-status totals backing the kanban column headers."""
        result = await self._session.execute(
            select(Lead.status, func.count())
            .where(Lead.organization_id == organization_id, Lead.deleted_at.is_(None))
            .group_by(Lead.status)
        )
        counts = {status.value: 0 for status in LeadStatus}
        for status, total in result.all():
            counts[status.value] = int(total)
        return counts

    # --- Lifecycle ---------------------------------------------------------

    async def change_status(
        self,
        lead: Lead,
        *,
        new_status: LeadStatus,
        actor_id: uuid.UUID | None,
        lost_reason: str | None = None,
    ) -> Lead:
        """Move a lead through the pipeline.

        Raises:
            InvalidLeadTransitionError: the move is not legal from the current
                status, including any attempt to set CONVERTED directly —
                conversion must go through :meth:`convert` so the account and
                contact are actually created.
        """
        if new_status is lead.status:
            return lead

        previous_status = lead.status
        allowed = LEAD_TRANSITIONS.get(lead.status, frozenset())
        if new_status not in allowed:
            raise InvalidLeadTransitionError(
                f"A lead cannot move from {lead.status.value} to {new_status.value}.",
                details={
                    "from": lead.status.value,
                    "to": new_status.value,
                    "allowed": sorted(status.value for status in allowed),
                },
            )

        lead.status = new_status
        if new_status in (LeadStatus.LOST, LeadStatus.UNQUALIFIED):
            lead.lost_reason = lost_reason
        else:
            lead.lost_reason = None
        lead.updated_by_id = actor_id
        await self._session.flush()
        logger.info(
            "lead_status_changed",
            lead_id=str(lead.id),
            organization_id=str(lead.organization_id),
            to=new_status.value,
        )

        # Recorded as its own action rather than as a generic UPDATE: a lead
        # moving through the pipeline is the event a sales manager reviews, and
        # burying it among field diffs would make it unfindable.
        await self.audit.record(
            organization_id=lead.organization_id,
            action=AuditAction.LEAD_STATUS_CHANGED,
            module=self.audit_module,
            actor_id=actor_id,
            entity_type=self.audit_entity_type,
            entity_id=lead.id,
            entity_label=self.audit_label(lead),
            details={
                "from": previous_status,
                "to": new_status,
                "lost_reason": lead.lost_reason,
            },
        )
        return lead

    async def assign_owner(
        self, lead: Lead, *, owner_id: uuid.UUID | None, actor_id: uuid.UUID | None
    ) -> Lead:
        previous_owner_id = lead.owner_id
        lead.owner_id = owner_id
        lead.updated_by_id = actor_id
        await self._session.flush()
        logger.info(
            "lead_owner_changed",
            lead_id=str(lead.id),
            owner_id=str(owner_id) if owner_id else None,
        )

        # Ownership decides record-level visibility (ADR-010), so reassigning
        # it changes who can see the lead. That makes it an access-control
        # event, not merely a field edit (`P2-W13-BE-05`).
        if previous_owner_id != owner_id:
            await self.audit.record(
                organization_id=lead.organization_id,
                action=AuditAction.OWNER_REASSIGNED,
                module=self.audit_module,
                actor_id=actor_id,
                entity_type=self.audit_entity_type,
                entity_id=lead.id,
                entity_label=self.audit_label(lead),
                details={"from": previous_owner_id, "to": owner_id},
            )
        return lead


__all__ = [
    "CONVERTIBLE_FROM",
    "LEAD_TRANSITIONS",
    "ConversionResult",
    "ConversionSuggestions",
    "DuplicateLeadEmailError",
    "InvalidLeadTransitionError",
    "LeadAlreadyConvertedError",
    "LeadNotConvertibleError",
    "LeadService",
]
