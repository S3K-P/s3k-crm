"""Tables behind the saved-report library.

Two tables, and neither stores a result. A saved report stores the *question* —
which entry in the built-in catalogue, over which period — and the answer is
recomputed on every run against the runner's own record visibility. That is
the property that makes sharing safe: a manager and a rep can open the same
saved report and legitimately see different numbers, because the rows are
resolved for whoever asked, not for whoever saved it. Caching a result here
would turn a shared report into a way of handing a rep the manager's totals.

``base_report_key`` is a foreign key in spirit only: the catalogue it points
into is Python (``catalog.REPORTS``), not a table, so the database cannot
enforce it. The service validates the key on write, and the run path resolves
it again and 404s if the catalogue has since dropped it — a report definition
retired in a release must not become a 500 for everyone who saved it.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import Date, Enum, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin


class ShareScope(enum.StrEnum):
    """Who may open a saved object besides the person who made it.

    Deliberately two values rather than the three ``NoteVisibility`` carries.
    A note distinguishes TEAM from ORGANIZATION because a note is about a
    customer conversation that a team has a particular stake in; a saved report
    is a piece of tooling, and "my draft" versus "the team's" is the only
    distinction anyone has asked a reporting tool for. A third value would have
    to mean something, and nothing here means it.
    """

    #: Only the owner sees it. The default, so a half-built report is not
    #: broadcast to the organization the moment it is named.
    PRIVATE = "PRIVATE"
    #: Any member holding ``reports.VIEW`` sees it — and still runs it as
    #: themselves.
    SHARED = "SHARED"


class ReportPeriod(enum.StrEnum):
    """The window a saved report runs over, resolved fresh on every run.

    Storing a relative period rather than two dates is the difference between
    a saved report that keeps working and one that quietly reports last
    quarter forever. ``CUSTOM`` is the escape hatch and is the only value that
    reads ``date_from``/``date_to``.
    """

    ALL_TIME = "ALL_TIME"
    TODAY = "TODAY"
    LAST_7_DAYS = "LAST_7_DAYS"
    LAST_30_DAYS = "LAST_30_DAYS"
    LAST_90_DAYS = "LAST_90_DAYS"
    THIS_MONTH = "THIS_MONTH"
    LAST_MONTH = "LAST_MONTH"
    THIS_QUARTER = "THIS_QUARTER"
    LAST_QUARTER = "LAST_QUARTER"
    THIS_YEAR = "THIS_YEAR"
    CUSTOM = "CUSTOM"


class ReportFolder(Base, CrmEntityMixin):
    """A named group of saved reports.

    Flat, not a tree. A hierarchy would need move semantics, cycle prevention
    and a recursive read, and the thing people actually do with report folders
    — "Sales", "Marketing", "Board pack" — is satisfied by one level. Nesting
    can be added later without invalidating any row here.

    Folders are organization-wide by design and carry no ``ShareScope``: a
    folder is a filing cabinet, and a private cabinet whose contents are shared
    (or the reverse) is a puzzle rather than a feature. Sharing is decided per
    report.
    """

    __tablename__ = "report_folders"
    __table_args__ = (
        Index(
            "uq_report_folders_organization_id_name",
            "organization_id",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Who created it. Folders are readable organization-wide, so this is
    #: attribution rather than an access control input.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class SavedReport(Base, CrmEntityMixin):
    """A named, parameterised run of one built-in report."""

    __tablename__ = "saved_reports"
    __table_args__ = (
        Index(
            "uq_saved_reports_organization_id_name",
            "organization_id",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index("ix_saved_reports_organization_id_folder_id", "organization_id", "folder_id"),
        {"schema": CRM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Key into ``reports.catalog.REPORTS``. See the module docstring for why
    #: this is not a foreign key.
    base_report_key: Mapped[str] = mapped_column(String(64), nullable=False)

    #: ``SET NULL`` rather than cascade: deleting a folder must never delete
    #: the work filed in it. The service refuses to delete a non-empty folder
    #: anyway, so this is the backstop for a direct database action.
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(f"{CRM_SCHEMA}.report_folders.id", ondelete="SET NULL"),
        nullable=True,
    )

    period: Mapped[ReportPeriod] = mapped_column(
        Enum(ReportPeriod, name="report_period", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ReportPeriod.ALL_TIME,
        server_default=ReportPeriod.ALL_TIME.value,
    )
    #: Read only when ``period`` is ``CUSTOM``. Kept when the period changes
    #: away and back, so switching to a relative window and reconsidering does
    #: not silently discard the dates the user typed.
    date_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    visibility: Mapped[ShareScope] = mapped_column(
        Enum(ShareScope, name="share_scope", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ShareScope.PRIVATE,
        server_default=ShareScope.PRIVATE.value,
    )


__all__ = ["ReportFolder", "ReportPeriod", "SavedReport", "ShareScope"]
