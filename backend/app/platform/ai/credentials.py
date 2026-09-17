"""Provider credential management, and the resolution the gateway runs on.

**Two jobs, and the second is the one that matters most.**

*Managing* credentials is ordinary tenant-scoped CRUD with encryption at the
boundary: store ciphertext, hand back masked metadata, never return a key.

*Resolving* one is what the gateway does on every call, and its ordering is a
deliberate decision:

1. the organization's own stored credential, when it exists and has not been
   rejected by the provider;
2. otherwise a deployment-wide key from the environment — ``ANTHROPIC_API_KEY``
   or ``GEMINI_API_KEY``, in that order.

Tenant first, because an administrator who just typed a key into Settings must
see that key take effect — an environment variable quietly overriding it would
present as "S3K ignored my configuration". Environment second, because it is
the bootstrapping path: it is how a deployment runs AI before anyone has
configured anything, and how it keeps running for organizations that never do.

**A rejected credential is skipped, an untested one is not.** ``UNVERIFIED``
means nobody has checked yet, which is not evidence of anything; ``INVALID``
means the provider itself said no. Falling through to the environment on the
first is how a just-entered key would get silently ignored; falling through on
the second is how a tenant with a stale key keeps working.

Nothing in this module logs a credential, and no return value carries one
except :class:`ResolvedCredential`, which exists solely to hand the plaintext
to the provider constructor and is never serialised.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

import structlog
from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError, NotFoundError
from app.core.secrets import SecretBox, fingerprint_secret, mask_secret
from app.platform.ai.models import (
    ANTHROPIC_PROVIDER,
    GEMINI_PROVIDER,
    SUPPORTED_PROVIDERS,
    AiProviderCredential,
    CredentialStatus,
)
from app.platform.audit.service import Action as AuditAction
from app.platform.audit.service import audit_for_session

logger = structlog.get_logger(__name__)

#: Shortest thing that could plausibly be a provider key. Not a format check —
#: vendors change their prefixes — just enough to reject an empty paste before
#: it costs a network round trip.
MIN_KEY_LENGTH = 16


class UnsupportedProviderError(AppError):
    """A provider this deployment has no implementation for.

    404 rather than 422: from the caller's point of view the resource does not
    exist, and the supported set is discoverable at ``GET /ai/providers``.
    """

    status_code = status.HTTP_404_NOT_FOUND
    code = "unsupported_ai_provider"
    message = "That AI provider is not available on this deployment."


class InvalidCredentialError(AppError):
    """The submitted value cannot be a credential, before any network call."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "invalid_ai_credential"
    message = "That does not look like a valid API key."


@dataclass(frozen=True, slots=True)
class ResolvedCredential:
    """A usable key plus where it came from.

    ``source`` is reported to administrators — "this organization is running on
    the deployment-wide key" is something they need to be able to see — while
    ``secret`` never leaves the process except towards the provider.
    """

    secret: str
    #: ``"organization"`` or ``"environment"``.
    source: str
    provider: str


class AiCredentialService:
    """Stores, tests and resolves AI provider credentials."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        key = settings.ai_credential_encryption_key
        self._box = SecretBox.from_key(key.get_secret_value() if key else None)

    # --- Reading ----------------------------------------------------------

    @property
    def storage_available(self) -> bool:
        """Whether credentials can be written at all on this deployment."""
        return self._box.available

    async def get(
        self, *, organization_id: uuid.UUID, provider: str
    ) -> AiProviderCredential | None:
        """One organization's credential for one provider.

        Filtered on ``organization_id`` explicitly. RLS is the backstop, not
        the primary control — the same rule the prompt repository states.
        """
        result = await self._session.execute(
            select(AiProviderCredential).where(
                AiProviderCredential.organization_id == organization_id,
                AiProviderCredential.provider == provider,
            )
        )
        return result.scalar_one_or_none()

    async def list_for(
        self, organization_id: uuid.UUID
    ) -> list[AiProviderCredential]:
        result = await self._session.execute(
            select(AiProviderCredential)
            .where(AiProviderCredential.organization_id == organization_id)
            .order_by(AiProviderCredential.provider)
        )
        return list(result.scalars().all())

    # --- Writing ----------------------------------------------------------

    async def store(
        self,
        *,
        organization_id: uuid.UUID,
        provider: str,
        secret: str,
        actor_id: uuid.UUID | None,
    ) -> AiProviderCredential:
        """Encrypt and save a credential, replacing any previous one.

        Upserts rather than versioning, unlike the prompt library: an old
        prompt has to stay resolvable because research pinned to it must remain
        reproducible, whereas keeping superseded ciphertext around would only
        enlarge the set of secrets an attacker could work on. History lives in
        the audit trail, which records *that* a key changed and never its value.

        The credential is stored ``UNVERIFIED``; :meth:`test` is what promotes
        it to ``CONNECTED``, and only a real provider response can.

        Raises:
            UnsupportedProviderError: no implementation for ``provider``.
            InvalidCredentialError: the value is obviously not a key.
            SecretsNotConfiguredError: no encryption key on this deployment.
        """
        require_supported(provider)
        cleaned = secret.strip()
        if len(cleaned) < MIN_KEY_LENGTH:
            raise InvalidCredentialError

        # Raises SecretsNotConfiguredError before anything is written, so a
        # deployment without an encryption key never half-saves a credential.
        ciphertext = self._box.encrypt(cleaned)

        existing = await self.get(organization_id=organization_id, provider=provider)
        fingerprint = fingerprint_secret(cleaned)
        unchanged = existing is not None and existing.key_fingerprint == fingerprint

        if existing is None:
            # Default only when nothing else already is. Claiming it
            # unconditionally violates the one-default-per-organization index
            # the moment a second provider is configured — and silently
            # switching which vendor the gateway calls, just because a key was
            # added, is not something an administrator asked for. Choosing is
            # ``set_default``'s job.
            has_default = await self._default_for(organization_id) is not None
            credential = AiProviderCredential(
                organization_id=organization_id,
                provider=provider,
                secret_ciphertext=ciphertext,
                masked_key=mask_secret(cleaned),
                key_fingerprint=fingerprint,
                status=CredentialStatus.UNVERIFIED,
                is_default=not has_default,
                updated_by_id=actor_id,
            )
            self._session.add(credential)
        else:
            credential = existing
            credential.secret_ciphertext = ciphertext
            credential.masked_key = mask_secret(cleaned)
            credential.key_fingerprint = fingerprint
            credential.updated_by_id = actor_id
            if not unchanged:
                # A different key invalidates what the last test proved.
                credential.status = CredentialStatus.UNVERIFIED
                credential.last_tested_at = None
                credential.last_test_error = None

        await self._session.flush()

        await audit_for_session(self._session).record(
            organization_id=organization_id,
            action=AuditAction.UPDATED if existing is not None else AuditAction.CREATED,
            module="ai",
            entity_type="AI_PROVIDER_CREDENTIAL",
            entity_id=credential.id,
            entity_label=provider,
            actor_id=actor_id,
            # Fingerprint, never the key or the ciphertext. It is enough to
            # tell a reviewer that the value changed, and useless to anyone who
            # obtains the trail.
            details={
                "provider": provider,
                "rotated": not unchanged,
                "fingerprint": fingerprint[:12],
            },
        )
        logger.info("ai_credential_stored", provider=provider, rotated=not unchanged)
        return credential

    async def delete(
        self, *, organization_id: uuid.UUID, provider: str, actor_id: uuid.UUID | None
    ) -> None:
        """Remove a credential, falling the organization back to the environment.

        Raises:
            NotFoundError: this organization holds no credential for ``provider``.
        """
        require_supported(provider)
        credential = await self.get(organization_id=organization_id, provider=provider)
        if credential is None:
            raise NotFoundError("No credential is configured for that provider.")

        await self._session.delete(credential)
        await self._session.flush()

        await audit_for_session(self._session).record(
            organization_id=organization_id,
            action=AuditAction.DELETED,
            module="ai",
            entity_type="AI_PROVIDER_CREDENTIAL",
            entity_id=credential.id,
            entity_label=provider,
            actor_id=actor_id,
            details={"provider": provider},
        )
        logger.info("ai_credential_deleted", provider=provider)

    async def set_default(
        self, *, organization_id: uuid.UUID, provider: str, actor_id: uuid.UUID | None
    ) -> AiProviderCredential:
        """Make ``provider`` the one the gateway reaches for.

        Clears the flag across the organization first, in the same transaction,
        so the partial unique index never sees two defaults.
        """
        require_supported(provider)
        credential = await self.get(organization_id=organization_id, provider=provider)
        if credential is None:
            raise NotFoundError("No credential is configured for that provider.")

        await self._session.execute(
            update(AiProviderCredential)
            .where(
                AiProviderCredential.organization_id == organization_id,
                AiProviderCredential.is_default.is_(True),
            )
            .values(is_default=False)
        )
        credential.is_default = True
        await self._session.flush()

        await audit_for_session(self._session).record(
            organization_id=organization_id,
            action=AuditAction.UPDATED,
            module="ai",
            entity_type="AI_PROVIDER_CREDENTIAL",
            entity_id=credential.id,
            entity_label=provider,
            actor_id=actor_id,
            details={"provider": provider, "made_default": True},
        )
        return credential

    def reveal(self, credential: AiProviderCredential) -> str:
        """Decrypt a stored credential, for an immediate provider call.

        The one deliberate hole in "the key never comes back out", and it is
        narrow by construction: it takes a row the caller already loaded under
        its tenant filter, returns a plain string, and every caller in this
        codebase passes that string straight into a provider client and lets it
        go out of scope. It is never awaited into a response model, and there
        is no route that returns its value.

        Raises:
            SecretsNotConfiguredError: no encryption key on this deployment.
            SecretDecryptionError: the key was rotated, or the row altered.
        """
        return self._box.decrypt(credential.secret_ciphertext)

    async def record_test_result(
        self,
        *,
        credential: AiProviderCredential,
        ok: bool,
        error: str | None,
        now: dt.datetime | None = None,
    ) -> AiProviderCredential:
        """Write back what a connectivity check concluded."""
        credential.status = CredentialStatus.CONNECTED if ok else CredentialStatus.INVALID
        credential.last_tested_at = now or dt.datetime.now(dt.UTC)
        credential.last_test_error = None if ok else (error or "")[:255]
        await self._session.flush()
        return credential

    # --- Resolution -------------------------------------------------------

    async def resolve(self, organization_id: uuid.UUID) -> ResolvedCredential | None:
        """The credential the gateway should call with, or ``None``.

        See the module docstring for why the organization's own key is
        preferred over the environment, and why ``UNVERIFIED`` still counts
        while ``INVALID`` does not.

        Returns ``None`` when neither source has one — the honest
        "AI is not connected" state, not an error.
        """
        credential = await self._default_for(organization_id)
        if credential is not None and credential.usable():
            try:
                secret = self._box.decrypt(credential.secret_ciphertext)
            except AppError:
                # An undecryptable row must not silently fall through to the
                # environment: that would look like the stored key working when
                # it is in fact unreadable. Surfaced instead.
                raise
            return ResolvedCredential(
                secret=secret, source="organization", provider=credential.provider
            )

        return self._from_environment()

    def _from_environment(self) -> ResolvedCredential | None:
        """The deployment-wide fallback, whichever vendor supplied one.

        Ordered, not arbitrary: Anthropic first because it was the original
        deployment key and an existing environment must not change vendor
        underneath itself simply because a Gemini key was later added beside
        it. A deployment that wants Gemini to win sets only ``GEMINI_API_KEY``,
        or configures it per organization, which beats both.
        """
        for provider, key in (
            (ANTHROPIC_PROVIDER, self._settings.anthropic_api_key),
            (GEMINI_PROVIDER, self._settings.gemini_api_key),
        ):
            if key and key.get_secret_value().strip():
                return ResolvedCredential(
                    secret=key.get_secret_value().strip(),
                    source="environment",
                    provider=provider,
                )
        return None

    async def _default_for(
        self, organization_id: uuid.UUID
    ) -> AiProviderCredential | None:
        """The organization's default credential, or its only one."""
        result = await self._session.execute(
            select(AiProviderCredential)
            .where(
                AiProviderCredential.organization_id == organization_id,
                AiProviderCredential.is_default.is_(True),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


def require_supported(provider: str) -> str:
    """Refuse anything this deployment has no implementation for.

    Raises:
        UnsupportedProviderError: ``provider`` is not in the allow-list.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise UnsupportedProviderError
    return provider


__all__ = [
    "MIN_KEY_LENGTH",
    "AiCredentialService",
    "InvalidCredentialError",
    "ResolvedCredential",
    "UnsupportedProviderError",
    "require_supported",
]
