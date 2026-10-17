"""Tables behind configurable dashboards.

This module now holds three things that sound alike and are not:

* ``GET /crm/dashboard/summary`` (``service.py``, ``repository.py``) — the
  fixed home screen every organization gets. No rows, no configuration.
* ``HomeDashboardLayout``, below — one user's card order/visibility
  preference *for that fixed home screen*'s "Customize dashboard" feature.
  Still no report data, just nine booleans-and-a-position.
* ``Dashboard`` and ``DashboardComponent``, below — dashboards a user builds,
  each a arrangement of saved reports.

They share the ``dashboard`` permission module because they answer the same
question about a caller ("may this person look at aggregate CRM data") and
splitting them would mean an administrator granting two permissions to deliver
one capability.

A component points at a :class:`~app.products.crm.reports.models.SavedReport`
rather than at a catalogue key directly. That composition is deliberate: it
means a dashboard tile inherits the period, the sharing decision and the name
its report already carries, and it leaves exactly one place to change when a
report needs adjusting — rather than a definition per tile that drifts from
the report of the same name in the library.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin
from app.products.crm.reports.models import ShareScope

PLATFORM_SCHEMA = "platform"

#: Grid width of a dashboard row. Twelve because it divides by 2, 3, 4 and 6,
#: so halves, thirds and quarters are all expressible without fractions.
DASHBOARD_GRID_COLUMNS = 12


class ComponentDisplay(enum.StrEnum):
    """How one tile draws the report behind it."""

    #: The report's own chart hint. A report with no hint renders as a table
    #: instead — the service resolves that rather than drawing nothing.
    CHART = "CHART"
    TABLE = "TABLE"
    #: A single headline number: the first summable total the report declares.
    #: Falls back to the row count for a report that totals nothing, which is
    #: still a true statement about the report.
    METRIC = "METRIC"


class Dashboard(Base, CrmEntityMixin):
    """A named arrangement of report tiles."""

    __tablename__ = "dashboards"
    __table_args__ = (
        Index(
            "uq_dashboards_organization_id_name",
            "organization_id",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    visibility: Mapped[ShareScope] = mapped_column(
        Enum(ShareScope, name="share_scope", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ShareScope.PRIVATE,
        server_default=ShareScope.PRIVATE.value,
    )
    #: The dashboard this member lands on. Per owner rather than per
    #: organization: one person's default is not an administrative decision,
    #: and an organization-wide default would need a permission of its own to
    #: decide who may move it.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class DashboardComponent(Base, CrmEntityMixin):
    """One tile: a saved report, drawn a particular way, in a particular slot."""

    __tablename__ = "dashboard_components"
    __table_args__ = (
        CheckConstraint(
            f"width BETWEEN 1 AND {DASHBOARD_GRID_COLUMNS}",
            name="ck_dashboard_components_width",
        ),
        CheckConstraint("sort_order >= 0", name="ck_dashboard_components_sort_order"),
        Index(
            "ix_dashboard_components_organization_id_dashboard_id",
            "organization_id",
            "dashboard_id",
        ),
        Index(
            "ix_dashboard_components_organization_id_saved_report_id",
            "organization_id",
            "saved_report_id",
        ),
        {"schema": CRM_SCHEMA},
    )

    #: Cascade, because a tile has no meaning without its dashboard. This is
    #: the one relationship here where the child genuinely is part of the
    #: parent rather than a reference to something with its own life.
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.dashboards.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: ``RESTRICT``: a saved report still on a dashboard cannot be deleted out
    #: from under it. The service turns that into a 409 naming the dashboards
    #: involved, so the person deleting finds out *where* rather than being
    #: told no.
    saved_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.saved_reports.id", ondelete="RESTRICT"),
        nullable=False,
    )

    #: Overrides the saved report's name on this tile only. Null means "use the
    #: report's own name", which is what keeps a renamed report renaming its
    #: tiles.
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    display: Mapped[ComponentDisplay] = mapped_column(
        Enum(ComponentDisplay, name="component_display", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ComponentDisplay.CHART,
        server_default=ComponentDisplay.CHART.value,
    )
    #: Position in the flow, and how many of the twelve columns to occupy.
    #: A flow with widths beats explicit (x, y) coordinates here: it reflows on
    #: a narrow screen without the server having to store a second layout.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=6, server_default="6")


class HomeDashboardLayout(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One user's saved card order and visibility for the fixed home dashboard.

    Not related to :class:`Dashboard` above — this is the "Customize
    dashboard" preference for ``GET /crm/dashboard/summary``'s fixed home
    screen, not a user-built report dashboard. Lives in ``platform`` (per the
    ``TenantMixin`` + RLS convention every tenant-scoped table follows)
    alongside other per-user-per-org rows such as ``team_memberships``, since
    it is a preference rather than CRM domain data.

    ``user_id`` is a real foreign key, ``ON DELETE CASCADE``, unlike the
    owner/author columns CRM records carry: a layout *is* that user's
    preference and has no reason to outlive them.
    """

    __tablename__ = "dashboard_layouts"
    __table_args__ = (
        Index(
            "uq_dashboard_layouts_user_id_organization_id",
            "user_id",
            "organization_id",
            unique=True,
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{PLATFORM_SCHEMA}.users.id",
            ondelete="CASCADE",
            name="fk_dashboard_layouts_user_id_users",
        ),
        nullable=False,
    )
    #: Ordered list of ``{"card_type": str, "visible": bool}`` objects — the
    #: whole of what "Customize dashboard" lets a user change. Validated by
    #: the service against :class:`~app.products.crm.dashboard.schemas.HomeCardType`
    #: before it is ever written, so a row in this column is always a list of
    #: known card types in some order, never arbitrary JSON.
    cards: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)


__all__ = [
    "DASHBOARD_GRID_COLUMNS",
    "ComponentDisplay",
    "Dashboard",
    "DashboardComponent",
    "HomeDashboardLayout",
]
