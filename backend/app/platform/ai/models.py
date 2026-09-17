"""SQLAlchemy models for the AI gateway (ADR-016).

One table: the prompt library. A prompt is **append-only version history**
rather than an editable row, which is the whole mechanism behind §12 —
"changing the prompt affects new research, not old".

Editing publishes a new row with ``version + 1`` and moves the active flag.
Nothing rewrites a published version, so a research session that recorded
``prompt_version_id`` still resolves to the exact wording it ran under, months
after an administrator reworded it.

The table is tenant-scoped: one organization's prompt is not another's, and
RLS isolates it like every other table naming a customer.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

PLATFORM_SCHEMA = "platform"

#: Prompt key used by S3K CRM's Market Insights research feature.
#:
#: Named here rather than in the CRM module because the gateway owns the
#: keyspace: Platform must not import a product (ARCHITECTURE-BOUNDARIES rule
#: 1), so the constant lives on the side that can be imported by both.
MARKET_INSIGHTS_PROMPT_KEY = "market_insights"


class AiPromptVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One published revision of a configurable prompt.

    Rows are never updated except to clear :attr:`is_active`. Treating the
    text as immutable is what lets a stored research session point at the
    wording that produced it.
    """

    __tablename__ = "ai_prompt_versions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "key", "version", name="uq_ai_prompt_versions_org_key_version"
        ),
        # One active version per key, enforced by the database rather than by
        # the service. Two concurrent publishes would otherwise both flip the
        # flag on and every later read would pick arbitrarily between them.
        Index(
            "uq_ai_prompt_versions_active",
            "organization_id",
            "key",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    #: Which prompt this is, e.g. ``market_insights``. Stable across versions.
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Monotonic per (organization, key), starting at 1.
    version: Mapped[int] = mapped_column(nullable=False)
    #: The instruction text an administrator wrote.
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    #: Free-text note explaining the change, shown in the version list.
    change_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: Exactly one row per (organization, key) carries ``True``.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Who published it. Not a foreign key, for the reason ``AuthorshipMixin``
    #: gives: the history must outlive the user record.
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


__all__ = ["MARKET_INSIGHTS_PROMPT_KEY", "AiPromptVersion"]
