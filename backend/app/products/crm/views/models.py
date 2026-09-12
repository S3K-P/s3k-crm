"""SQLAlchemy model for saved list views (Phase F).

**A view stores a question, never an answer.** ``filters``, ``sort_by`` and
``columns`` describe what to ask the record endpoint; no row, id or count is
kept. That is what makes a view opened a year later show that day's records
rather than a snapshot nobody can tell is stale, and it is why running a view
costs exactly what running the underlying list costs.

**It is also not a permission.** Sharing a view organization-wide shares the
*question*. Answering it still goes through the module's own endpoint, behind
that module's permission and record-level visibility, so two colleagues opening
one shared view legitimately see different rows.

The filter document is deliberately opaque to the database: it is the same
query-string vocabulary the list endpoints already accept, including the
``cf_*`` custom-field filters from Phase E. Storing it as JSONB rather than as
columns means a view keeps working when a module gains a filter, and means the
one place that has to understand a filter is the endpoint that already did.
What *is* enforced is that the document is small and shallow — see
:mod:`.schemas` — because it is loaded on every list render.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, Index, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, CrmEntityType

#: Ceiling on views one organization may save, per record type.
#:
#: Not tidiness: every view is offered in a dropdown on the list screen, and
#: the whole set for an entity is read on each render. A four-figure count
#: would make the screen it decorates slower for everybody in the tenant.
MAX_VIEWS_PER_ENTITY = 200


class ViewVisibility(enum.StrEnum):
    """Who may read a saved view.

    Three rungs, matching the record-visibility ladder the product already
    has, so "who can see this view" is answered with the same vocabulary as
    "who can see these records" rather than a second, subtly different one.
    """

    #: Its owner only. The default: a half-built view is nobody else's problem.
    PRIVATE = "PRIVATE"
    #: Its owner and anyone on a team they share.
    TEAM = "TEAM"
    #: Everyone in the organization.
    ORGANIZATION = "ORGANIZATION"


class SavedView(Base, CrmEntityMixin):
    """One named list configuration for one record type."""

    __tablename__ = "saved_views"
    __table_args__ = (
        # Name uniqueness is scoped to the *owner*, not the organization: two
        # reps each having their own "My hot leads" is normal and refusing the
        # second would be surprising. A shared view with a colliding name is
        # equally legitimate — the list screen shows the owner beside it.
        Index(
            "uq_saved_views_owner_entity_name_live",
            "organization_id",
            "owner_id",
            "entity_type",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # The read behind every list render: "which views may I see on this
        # entity". Ordered so the tenant and entity columns lead, since both
        # are equality predicates.
        Index(
            "ix_saved_views_organization_id_entity_type",
            "organization_id",
            "entity_type",
        ),
        # At most one default per person per record type. Partial on both
        # conditions so it constrains only the rows making the claim, and
        # keyed by owner because a default is a personal preference — one
        # administrator's choice must not become everybody's.
        Index(
            "uq_saved_views_owner_entity_default",
            "organization_id",
            "owner_id",
            "entity_type",
            unique=True,
            postgresql_where=text("is_default AND deleted_at IS NULL"),
        ),
        {"schema": CRM_SCHEMA},
    )

    entity_type: Mapped[CrmEntityType] = mapped_column(
        Enum(CrmEntityType, name="crm_entity_type", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    #: The person the view belongs to. Not nullable, unlike ``owner_id``
    #: elsewhere: an unowned record is a historical artefact, but an unowned
    #: *view* could never have been created — and under the visibility rules
    #: below it would be one nobody could edit and everybody could see.
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    visibility: Mapped[ViewVisibility] = mapped_column(
        Enum(ViewVisibility, name="view_visibility", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ViewVisibility.PRIVATE,
        server_default=ViewVisibility.PRIVATE.value,
    )

    #: The list endpoint's own query vocabulary, as ``{name: value}``.
    filters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    #: An optional multi-condition AND/OR filter (Checkpoint 5), stored as a
    #: ``reports.conditions.ReportFilterGroup``. Additive and separate from
    #: ``filters`` above rather than a replacement for it: every existing view
    #: keeps working under the same flat-document validator it always had, and
    #: a view that *does* carry an advanced filter has both applied together
    #: (ANDed) by the list endpoint — the flat document for the simple,
    #: single-value filters the list screen's own controls still write, the
    #: advanced one for whatever the condition-builder produced.
    advanced_filter: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    #: Column keys to show, in order. Empty means "the screen's own default
    #: columns", which is different from "no columns" and is why this is a
    #: list rather than a nullable one.
    columns: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    sort_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sort_dir: Mapped[str | None] = mapped_column(String(4), nullable=True)

    #: Opened automatically when its owner visits the list screen.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    @property
    def is_shared(self) -> bool:
        return self.visibility is not ViewVisibility.PRIVATE


__all__ = ["MAX_VIEWS_PER_ENTITY", "SavedView", "ViewVisibility"]
