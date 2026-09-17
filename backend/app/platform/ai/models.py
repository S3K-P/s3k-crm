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

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
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


#: Providers this deployment can actually call.
#:
#: Every entry has a class implementing ``ResearchProvider`` and a client
#: library behind it. Listing a vendor that nothing can call would put a
#: configurable, testable, permanently broken row on the Providers screen —
#: the same dishonesty the AI pages were stripped of.
#:
#: Both entries support **server-side web search**, and that is a requirement
#: rather than a coincidence. Market Insights cites its sources, so a model
#: that could only answer from training data would produce confident, undated
#: prose with nothing real to attribute — see the note at the top of
#: ``gemini.py``. A future vendor without grounding needs a way to be excluded
#: from research features rather than simply being added here.
ANTHROPIC_PROVIDER = "anthropic"
GEMINI_PROVIDER = "gemini"
SUPPORTED_PROVIDERS: tuple[str, ...] = (ANTHROPIC_PROVIDER, GEMINI_PROVIDER)


class CredentialStatus(enum.StrEnum):
    """What the last connectivity check against this credential concluded."""

    #: Stored but never successfully tested.
    UNVERIFIED = "UNVERIFIED"
    #: The provider accepted it. Set only after a real call.
    CONNECTED = "CONNECTED"
    #: The provider rejected it, or the test failed against it.
    INVALID = "INVALID"


class AiProviderCredential(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    """One organization's API credential for one AI provider.

    **The only reversibly-encrypted secret in the schema.** A password or a
    refresh token is hashed because it is only ever compared; this value has to
    be handed to Anthropic verbatim on every call, so it is stored as Fernet
    ciphertext and decrypted at the point of use. :mod:`app.core.secrets` holds
    the reasoning and the key handling.

    Nothing here is ever returned to a client. The API answers with
    :attr:`masked_key` and :attr:`status`; the ciphertext leaves the process
    only in the direction of the provider.

    Tenant-scoped and RLS-protected like the prompt library beside it — one
    organization's key is emphatically not another's, and a shared deployment
    key remains the *environment* fallback rather than a row anybody can read.
    """

    __tablename__ = "ai_provider_credentials"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider", name="uq_ai_provider_credentials_org_provider"
        ),
        # At most one default per organization, enforced by the database. Two
        # concurrent "make this the default" writes would otherwise both set
        # the flag and resolution would pick between them arbitrarily — the
        # same failure the prompt library's active-version index prevents.
        Index(
            "uq_ai_provider_credentials_default",
            "organization_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
        {"schema": PLATFORM_SCHEMA},
    )

    #: One of :data:`SUPPORTED_PROVIDERS`. A plain string rather than a native
    #: enum so adding a vendor needs no migration — the allow-list is enforced
    #: in the service, where an unsupported value can be refused with a message.
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Fernet ciphertext. Never logged, never serialised into a response.
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    #: Display form, e.g. ``••••••••AB9f``. Computed at write time so reading
    #: the list never needs the decryption key.
    masked_key: Mapped[str] = mapped_column(String(64), nullable=False)
    #: SHA-256 of the plaintext. Lets "is this the key I already hold?" be
    #: answered without decrypting, and gives audit something stable to name.
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[CredentialStatus] = mapped_column(
        Enum(
            CredentialStatus,
            name="ai_credential_status",
            schema=PLATFORM_SCHEMA,
            native_enum=True,
        ),
        nullable=False,
        default=CredentialStatus.UNVERIFIED,
        server_default=CredentialStatus.UNVERIFIED.value,
    )
    #: When connectivity was last checked, successfully or not.
    last_tested_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Why the last test failed, in words safe to show an administrator. Never
    #: the provider's raw error, which can echo request material back.
    last_test_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: The credential the gateway reaches for. See the partial index above.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: Who last wrote it. Not a foreign key, for the reason ``AuthorshipMixin``
    #: gives: the record must outlive the user.
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    def usable(self) -> bool:
        """Whether the gateway should try this credential.

        ``UNVERIFIED`` counts. A key that has never been tested is far more
        likely to be correct than not, and refusing to try it would make the
        environment fallback silently win over a key an administrator just
        entered — which reads as "my key was ignored". Only a credential the
        provider has actually *rejected* is skipped.
        """
        return self.status is not CredentialStatus.INVALID


__all__ = [
    "ANTHROPIC_PROVIDER",
    "GEMINI_PROVIDER",
    "MARKET_INSIGHTS_PROMPT_KEY",
    "SUPPORTED_PROVIDERS",
    "AiPromptVersion",
    "AiProviderCredential",
    "CredentialStatus",
]
