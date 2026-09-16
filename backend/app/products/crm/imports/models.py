"""SQLAlchemy model for a saved CSV column mapping (Checkpoint 4).

A template stores a *mapping*, never a file: ``{csv header -> field}`` plus
the duplicate policy, so reusing one against next month's export re-maps by
header name rather than replaying anything from the file that created it.
That is the same "a saved thing answers a question, it is not a snapshot"
design :class:`~app.products.crm.views.models.SavedView` already uses for its
``filters`` document, reused here for the identical reason: an importer who
gets the same CRM export every week from the same external system should map
its columns once.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin

#: Ceiling on templates one organization may save, per entity. A dropdown on
#: the mapping step renders the whole set; this is the same "the screen it
#: decorates must not slow down" bound ``MAX_VIEWS_PER_ENTITY`` states.
MAX_TEMPLATES_PER_ENTITY = 50


class ImportMappingTemplate(Base, CrmEntityMixin):
    """One saved ``{csv header -> field}`` mapping for one importable entity."""

    __tablename__ = "import_mapping_templates"
    __table_args__ = (
        Index(
            "uq_import_mapping_templates_org_entity_name_live",
            "organization_id",
            "entity_slug",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_import_mapping_templates_organization_id_entity_slug",
            "organization_id",
            "entity_slug",
        ),
        {"schema": CRM_SCHEMA},
    )

    #: :attr:`~app.products.crm.imports.catalog.ImportableEntity.slug`, e.g.
    #: ``"leads"``. Not a foreign key: the importable-entity catalogue is code,
    #: not a table, the same reason a saved view's ``entity_type`` is a bare
    #: enum column rather than one.
    entity_slug: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: ``{csv header: target field}``, the exact document the preview/commit
    #: endpoints already accept as their ``mapping`` form field.
    mapping: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    duplicate_policy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SKIP", server_default="SKIP"
    )


__all__ = ["MAX_TEMPLATES_PER_ENTITY", "ImportMappingTemplate"]
