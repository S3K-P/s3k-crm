"""SQLAlchemy models for the notes module (doc 05 "Note")."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, CrmEntityType


class NoteVisibility(enum.StrEnum):
    """Who may read a note.

    ``PRIVATE`` is visible only to its author; ``TEAM`` and ``ORGANIZATION``
    widen that. Enforcement lives in the notes policy, not in the database.
    """

    PRIVATE = "PRIVATE"
    TEAM = "TEAM"
    ORGANIZATION = "ORGANIZATION"


class Note(Base, CrmEntityMixin):
    """Free-text commentary attached to a CRM record."""

    __tablename__ = "notes"
    __table_args__ = (
        Index(
            "ix_notes_organization_id_related",
            "organization_id",
            "related_entity_type",
            "related_entity_id",
        ),
        Index("ix_notes_organization_id_deleted_at", "organization_id", "deleted_at"),
        {"schema": CRM_SCHEMA},
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[NoteVisibility] = mapped_column(
        Enum(NoteVisibility, name="note_visibility", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=NoteVisibility.TEAM,
        server_default=NoteVisibility.TEAM.value,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    related_entity_type: Mapped[CrmEntityType] = mapped_column(
        Enum(CrmEntityType, name="crm_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    related_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    # --- Provenance --------------------------------------------------------
    #: Where this note was originally written, when it has since been moved.
    #:
    #: Lead conversion re-points a lead's notes onto the records the lead
    #: became. Copying them to all three (Zoho's behaviour) would triple the
    #: text and leave three copies to drift; moving them keeps one authority.
    #: But a moved note otherwise loses the fact that it was written while the
    #: record was still a lead, so these two columns record it.
    #:
    #: NULL on a note that has never moved, which is almost all of them.
    origin_entity_type: Mapped[CrmEntityType | None] = mapped_column(
        Enum(CrmEntityType, name="crm_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=True,
    )
    origin_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


__all__ = ["Note", "NoteVisibility"]
