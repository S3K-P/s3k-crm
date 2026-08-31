"""SQLAlchemy models for market_insights.

Three tables, and the shape follows from what §9 and §12 require of history:

``market_insight_sessions``
    One research subject. Carries the company name as typed, an optional link
    to the CRM account it concerns, and — critically — the id of the prompt
    version the research ran under.

``market_insight_messages``
    The conversation, ordered by ``sequence``. The first assistant message is
    the report; everything after it is follow-up.

``market_insight_sources``
    Pages the search tool actually returned, per turn. A separate table rather
    than JSON on the message so the Sources panel can be queried, deduplicated
    by URL and counted without parsing a blob.

**Why the company name is a column and not only a foreign key.** A session may
concern a company that is not in the CRM at all — that is the point of §3B.
``account_id`` is therefore nullable, and ``company_name`` is always present.
When an external company is later added to the CRM (§8) the link is filled in
and the research is preserved rather than restarted.

**Why ``prompt_version_id`` is here.** It is what makes §12 true. Re-reading
an old session resolves the exact wording that produced it, so an
administrator rewording the prompt changes what the *next* report says and
nothing about what a previous one already said.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.products.crm.common import CRM_SCHEMA, CrmEntityMixin, searchable


class ResearchStatus(enum.StrEnum):
    """Outcome of a research session.

    There is deliberately no in-flight state. A row is written only once a
    turn has finished (see the service's module docstring), so a session is
    either usable or it failed — and a status nothing can ever hold would be a
    lie told to every reader of this enum.

    ``FAILED`` is a stored outcome rather than a discarded row: a user who
    runs research and hits a provider outage should find the attempt in their
    history with the reason, not an empty list suggesting nothing happened.
    """

    READY = "READY"
    FAILED = "FAILED"


class MessageRole(enum.StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MarketInsightSession(Base, CrmEntityMixin):
    """One company being researched, and the conversation about it."""

    __tablename__ = "market_insight_sessions"
    __table_args__ = (
        Index(
            "ix_market_insight_sessions_organization_id_owner_id",
            "organization_id",
            "owner_id",
        ),
        Index(
            "ix_market_insight_sessions_organization_id_account_id",
            "organization_id",
            "account_id",
        ),
        Index(
            "ix_market_insight_sessions_organization_id_deleted_at",
            "organization_id",
            "deleted_at",
        ),
        Index(
            "ix_market_insight_sessions_organization_id_last_activity_at",
            "organization_id",
            "last_activity_at",
        ),
        {"schema": CRM_SCHEMA},
    )

    #: The company as the user named it. Always set, CRM-linked or not.
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The CRM account this concerns, when there is one. Nullable by design:
    #: researching a company the organization has never dealt with is the
    #: primary use case, not an edge one.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    #: Session title, defaulted from the company name and renameable (§10).
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Whose research this is. Drives record-level visibility (§13).
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[ResearchStatus] = mapped_column(
        Enum(ResearchStatus, name="research_status", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
        default=ResearchStatus.READY,
        server_default=ResearchStatus.READY.value,
    )
    #: Error code from the last failed turn, for the retry surface. Never a
    #: provider message — those can carry request detail.
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # --- Provenance --------------------------------------------------------
    #: The prompt wording this research ran under (§12). Not a hard FK: the
    #: prompt library is a Platform table and CRM tables do not depend on
    #: Platform ones (ARCHITECTURE-BOUNDARIES.md rule 3).
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    prompt_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: The model that produced the report, recorded per session because it is
    #: part of how the result should be read a year later.
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Whether CRM context was in scope for the opening report, so the UI can
    #: label the report honestly rather than guessing from ``account_id``.
    used_crm_context: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    #: Bumped on every turn, so History sorts by real activity rather than by
    #: creation — a session revisited today belongs at the top.
    last_activity_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    #: Company name at ``A``: it is what somebody types to find a past
    #: session. Title at ``B`` because a renamed session is found by its name.
    search_vector: Mapped[str | None] = searchable(
        "setweight(to_tsvector('english'::regconfig, coalesce(company_name, '')), 'A') || "
        "setweight(to_tsvector('english'::regconfig, coalesce(title, '')), 'B')"
    )


class MarketInsightMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One turn of the conversation.

    No soft-delete column: a conversation is deleted with its session, and a
    message that could vanish mid-thread would leave a report answering a
    question nobody can see.
    """

    __tablename__ = "market_insight_messages"
    __table_args__ = (
        Index(
            "ix_market_insight_messages_session_id_sequence",
            "session_id",
            "sequence",
            unique=True,
        ),
        Index(
            "ix_market_insight_messages_organization_id_session_id",
            "organization_id",
            "session_id",
        ),
        {"schema": CRM_SCHEMA},
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{CRM_SCHEMA}.market_insight_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Position in the conversation, 1-based. Unique per session, which is
    #: what makes ordering total even inside a single transaction.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="market_insight_role", schema=CRM_SCHEMA, native_enum=True),
        nullable=False,
    )
    #: Markdown. The opening report's section structure comes from the
    #: configured prompt, so it is stored as written rather than parsed into
    #: columns — hard-coding the sections here is exactly what §5 forbids.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: True when the model stopped early, so the UI can say the answer is
    #: partial instead of presenting a truncated report as complete.
    truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: How many web searches produced this turn. Shown as provenance.
    search_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    #: The user who spoke, or who asked for the assistant turn.
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class MarketInsightSource(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """A page the search tool actually returned while answering.

    Every row here corresponds to a result the provider reported. Nothing in
    this codebase writes a source from prose, which is what lets the UI present
    the panel as evidence rather than as decoration (§17).
    """

    __tablename__ = "market_insight_sources"
    __table_args__ = (
        Index(
            "ix_market_insight_sources_organization_id_session_id",
            "organization_id",
            "session_id",
        ),
        {"schema": CRM_SCHEMA},
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{CRM_SCHEMA}.market_insight_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The turn that retrieved it. Nullable so a source outlives a message
    #: deletion rather than disappearing from the session's evidence.
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(f"{CRM_SCHEMA}.market_insight_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    #: The tool's freshness hint, verbatim. Often absent, never guessed.
    page_age: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Whether a sentence in the answer cited this page, as opposed to it
    #: merely having been read on the way to the answer.
    cited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    #: Display order within its turn.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: When the retrieval happened — the "research date" §4 asks to show.
    retrieved_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


__all__ = [
    "MarketInsightMessage",
    "MarketInsightSession",
    "MarketInsightSource",
    "MessageRole",
    "ResearchStatus",
]
