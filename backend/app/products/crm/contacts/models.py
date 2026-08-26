"""SQLAlchemy models for the contacts module (doc 05 "Contact")."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin


class ContactStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Contact(Base, CrmEntityMixin):
    """A person, optionally attached to an account.

    ``account_id`` is a real foreign key: the string ``account`` field the
    frontend currently uses is the anti-pattern W12 exists to remove.
    """

    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_organization_id_account_id", "organization_id", "account_id"),
        Index("ix_contacts_organization_id_email", "organization_id", "email"),
        Index("ix_contacts_organization_id_owner_id", "organization_id", "owner_id"),
        Index("ix_contacts_organization_id_deleted_at", "organization_id", "deleted_at"),
        CheckConstraint(
            "ai_score IS NULL OR (ai_score >= 0 AND ai_score <= 100)",
            name="ai_score_range",
        ),
        {"schema": CRM_SCHEMA},
    )

    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reporting_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    status: Mapped[ContactStatus] = mapped_column(
        Enum(ContactStatus, name="contact_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ContactStatus.ACTIVE,
        server_default=ContactStatus.ACTIVE.value,
    )
    #: Persisted only; nothing computes it yet (resolves A01).
    ai_score: Mapped[int | None] = mapped_column(nullable=True)
    preferred_communication: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Address -----------------------------------------------------------
    address_line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(120), nullable=True)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


__all__ = ["Contact", "ContactStatus"]
