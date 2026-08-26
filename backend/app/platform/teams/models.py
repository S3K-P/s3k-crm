"""SQLAlchemy models for the teams module (doc 04 "Team & Department").

Three tables, all in ``platform`` because organizational structure is a
Platform concern that several products will read and none may own (doc 08).

    departments        an optional grouping above teams
    teams              the working group a record's owner belongs to
    team_memberships   the user <-> team join

**Why this exists.** Record-level visibility shipped as *owner vs
organization-wide* only (CR07) because there was no team to resolve against.
The middle rung — "records owned by anyone on my team" — is the one most sales
organizations actually want, and it is the reason B02 blocked GATE 2.

``TeamMembership`` deliberately carries no ``organization_id``: a membership is
reached only through its team, and duplicating the tenant discriminator on the
join would create a second place for it to disagree with the first. Its
isolation comes from the team it points at, which is tenant-scoped and
RLS-protected — see the migration, where the join's policy is written as an
``EXISTS`` over ``teams`` rather than a column comparison.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import (
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

PLATFORM_SCHEMA = "platform"


class Department(
    Base,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
):
    """A grouping above teams, e.g. "Sales" or "Customer Success".

    Optional by design: ``Team.department_id`` is nullable, so an organization
    that does not think in departments never has to create one. It exists
    because doc 04 specifies it and ``Team`` references it; leaving it out
    would mean inventing a ``Team`` without the parent its schema names.

    Departments carry **no** authorization meaning. Visibility resolves through
    team membership only — a department is a label for grouping teams on the
    admin screen, not a wider circle of trust. Giving it one would silently
    widen every rep's reach the moment an administrator tidied the org chart.
    """

    __tablename__ = "departments"
    __table_args__ = (
        # Partial: a deleted department must not reserve its name forever.
        Index(
            "uq_departments_organization_id_name_live",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)


class Team(
    Base,
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    AuthorshipMixin,
    SoftDeleteMixin,
    TenantMixin,
):
    """A working group whose members can see one another's records."""

    __tablename__ = "teams"
    __table_args__ = (
        Index(
            "uq_teams_organization_id_name_live",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_teams_department_id", "department_id"),
        {"schema": PLATFORM_SCHEMA},
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    #: ``RESTRICT`` rather than ``CASCADE``: deleting a department must not
    #: silently take its teams — and with them every member's visibility —
    #: with it. The service refuses the delete and says which teams are in the
    #: way.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{PLATFORM_SCHEMA}.departments.id",
            ondelete="RESTRICT",
            name="fk_teams_department_id_departments",
        ),
        nullable=True,
    )


class TeamMembership(Base, UUIDPrimaryKeyMixin):
    """One user's place on one team.

    No soft delete: removing somebody from a team must actually remove their
    access to their former team-mates' records. A soft-deleted row that the
    visibility predicate forgot to filter would be a silent, permanent leak,
    and there is nothing here worth keeping that the audit trail does not
    already record.
    """

    __tablename__ = "team_memberships"
    __table_args__ = (
        # A user belongs to a team once. Not partial: there is no soft delete
        # here, so a plain unique constraint is the whole rule.
        Index(
            "uq_team_memberships_team_id_user_id",
            "team_id",
            "user_id",
            unique=True,
        ),
        Index("ix_team_memberships_user_id", "user_id"),
        {"schema": PLATFORM_SCHEMA},
    )

    team_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            f"{PLATFORM_SCHEMA}.teams.id",
            ondelete="CASCADE",
            name="fk_team_memberships_team_id_teams",
        ),
        nullable=False,
    )
    #: Not a foreign key to ``users``, matching ``AuthorshipMixin``: Platform
    #: must not force a hard identity dependency into every join, and a
    #: membership row is cleaned up by the service when a user is removed.
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    joined_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


__all__ = ["Department", "Team", "TeamMembership"]
