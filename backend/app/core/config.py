"""Typed application configuration.

Configuration is loaded from environment variables (or a git-ignored ``.env``
file) and validated by ``pydantic-settings`` at process start. Required
settings have **no default** so a misconfigured deployment fails fast with a
clear error instead of silently falling back to an insecure value.

See ``.env.example`` for the full list of supported variables.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Literal

from pydantic import (
    AliasChoices,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
#: Which vendor the AI gateway calls. Both reach a model that can search the
#: web while it answers, which is the one capability Market Insights cannot do
#: without; they differ in cost, and in how faithfully sources come back.
AiProvider = Literal["anthropic", "gemini"]


class ConfigurationError(RuntimeError):
    """Raised when application configuration is missing or invalid."""


class Settings(BaseSettings):
    """Validated application settings.

    Fields without a default are **required**; startup aborts when they are
    absent. No production credential ever has a fallback value here.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "s3k-crm-backend"
    environment: Environment = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # --- Datastores (required — no defaults, no embedded credentials) ------
    database_url: str = Field(
        ...,
        description="Async SQLAlchemy DSN, e.g. postgresql+asyncpg://user:pass@host:5432/db",
    )
    redis_url: str = Field(..., description="Redis DSN, e.g. redis://host:6379/0")

    # --- Connection pooling (ADR-005 / ADR-006) ----------------------------
    # Plan P0-W02-BE-02 specifies min 5 / max 20 connections: pool_size is the
    # persistent floor, pool_size + max_overflow the ceiling.
    db_pool_size: int = Field(default=5, ge=1, le=100)
    db_max_overflow: int = Field(default=15, ge=0, le=100)
    db_pool_timeout: int = Field(default=30, ge=1, le=300)
    db_pool_recycle: int = Field(default=1800, ge=-1)
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    redis_max_connections: int = Field(default=10, ge=1, le=1000)
    redis_socket_timeout: float = Field(default=5.0, gt=0)

    # --- Authentication (ADR-009, doc 13 "Authentication Security") --------
    # EdDSA (Ed25519) signing keys, PEM encoded. Required in every environment
    # except development/test, where an ephemeral keypair is generated at
    # startup so a fresh clone runs without key material on disk. An ephemeral
    # key is never acceptable in production: it would invalidate every issued
    # token on restart and cannot be shared across replicas.
    jwt_private_key: str | None = Field(
        default=None,
        description="Ed25519 private key in PEM format. Required outside development/test.",
    )
    jwt_public_key: str | None = Field(
        default=None,
        description="Ed25519 public key in PEM format. Required outside development/test.",
    )
    jwt_issuer: str = "s3k-platform"
    jwt_audience: str = "s3k-api"
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=60 * 60 * 24 * 14, ge=3600)

    # --- Password policy ---------------------------------------------------
    password_min_length: int = Field(default=12, ge=8, le=128)

    # --- Brute-force protection (doc 13) -----------------------------------
    login_max_failed_attempts: int = Field(default=5, ge=1, le=50)
    login_lockout_seconds: int = Field(default=900, ge=30)

    # --- Cookies -----------------------------------------------------------
    #: Refresh tokens travel in an httpOnly cookie (SEC01); never readable by JS.
    refresh_cookie_name: str = "s3k_refresh"
    #: Secure flag is forced on outside development so it cannot be forgotten.
    cookie_domain: str | None = None

    # --- CORS (doc 13 "API Security") --------------------------------------
    #: Browser origins allowed to call the API, comma-separated.
    #:
    #: Credentialed requests are required (the refresh cookie must travel), and
    #: the CORS specification forbids pairing credentials with a wildcard
    #: origin — so this is an explicit allow-list with no wildcard option.
    #: Empty means same-origin only, which is correct when the frontend is
    #: served from the same host.
    cors_allowed_origins: str = ""

    # --- Object storage (ADR-014, doc 13 "File Upload Security") -----------
    #
    # Cloudflare R2 in deployed environments, MinIO locally. Both speak the S3
    # API, so one boto3 client serves both and only these values differ. Every
    # credential field defaults to ``None`` rather than to a local value: a
    # deployment that forgets them must fail the validator below, not quietly
    # sign URLs against somebody else's bucket.
    storage_bucket: str | None = Field(
        default=None, description="Bucket holding attachment objects."
    )
    #: S3 endpoint the **backend** signs against. ``None`` targets real AWS S3;
    #: R2 and MinIO both need it set.
    storage_endpoint_url: str | None = None
    #: Endpoint the **browser** should reach, when it differs from the one the
    #: backend uses. Inside Docker the API talks to ``http://minio:9000`` while
    #: the browser can only reach ``http://localhost:9000``; a pre-signed URL
    #: built for the first host is unreachable from the second. Unset in
    #: production, where R2 is the same host for everyone.
    storage_public_endpoint_url: str | None = None
    storage_access_key_id: str | None = None
    storage_secret_access_key: str | None = None
    #: R2 ignores the region but boto3 requires one; ``auto`` is R2's own value.
    storage_region: str = "auto"
    #: R2 and MinIO both address buckets by path rather than by subdomain.
    storage_force_path_style: bool = True
    #: Doc 13: pre-signed download URLs expire in 15 minutes.
    storage_download_url_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    #: Upload URLs are equally short-lived; a browser uses one immediately.
    storage_upload_url_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    storage_connect_timeout_seconds: float = Field(default=5.0, gt=0)
    storage_read_timeout_seconds: float = Field(default=15.0, gt=0)

    # --- AI gateway (ADR-016) ----------------------------------------------
    #
    # The credential defaults to ``None`` and has no fallback, exactly like the
    # storage keys above. An unset key is a supported, *visible* state: the AI
    # endpoints report 503 ``ai_not_configured`` and the interface says so on
    # screen. That is the honest failure mode, and it is the reason nothing in
    # this codebase can silently substitute invented output for a model call.
    #
    # ``SecretStr`` keeps the value out of ``repr()``, structured logs and
    # tracebacks. It is read exactly once, by the provider, and is never part
    # of any response body — see ``AiConfigResponse``, which reports only
    # whether a key is present.
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key. Unset disables AI features rather than faking them.",
    )
    #: Google AI Studio key, for ``ai_provider="gemini"``. Kept in its own
    #: field rather than a shared ``ai_api_key`` so switching providers cannot
    #: silently send one vendor's credential to the other.
    #:
    #: Both spellings are accepted because both are in circulation: Google's
    #: own SDK reads ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``, and AI Studio
    #: labels the value the former. Accepting one only would reject a key that
    #: is sitting right there in the environment, correctly named.
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        description="Google AI Studio API key. Used only when ai_provider is 'gemini'.",
    )
    #: Which vendor to call. Anthropic is the default because its search tool
    #: returns real publisher URLs; Gemini is the option with a free tier.
    ai_provider: AiProvider = "anthropic"
    #: Pinned rather than 'latest': a model change alters what every stored
    #: research session would say if re-run, so it is a deliberate act.
    ai_model: str = "claude-opus-5"
    #: The Gemini counterpart of ``ai_model``. A moving alias rather than a
    #: pinned dated version, unlike ``ai_model`` above — a deliberate
    #: exception to that pinning policy, not an oversight. Dated Gemini Flash
    #: IDs have already gone stale twice in the time this integration has
    #: existed: the 2.5 generation closed to new API keys within weeks of
    #: general availability, and several 3.x releases return transient 503s
    #: under load that others in the same generation do not.
    #:
    #: The *lite* alias specifically, not ``gemini-flash-latest``: measured
    #: against the free tier while building this, the full Flash tier's
    #: "latest" alias was the one returning 503 "high demand" when tried, and
    #: Flash-Lite answered cleanly at the same moment — a smaller model is
    #: plausibly under lighter load on a capacity-constrained free tier.
    #: ``model_version`` on every response still records which concrete model
    #: actually wrote a given report, so reproducibility is not lost — only
    #: the choice of which model that is moves without a code change.
    gemini_model: str = "gemini-flash-lite-latest"
    #: Whether the Gemini provider offers Google Search grounding at all.
    #:
    #: Off by default. On a project with no billing account attached,
    #: grounding does not degrade gracefully — it returns a flat 429
    #: ("exceeded your current quota") on every model, every time, and
    #: enabling billing is the only fix (ai.google.dev/gemini-api/docs/rate-
    #: limits). Requesting it anyway would not buy partial results; it would
    #: only turn every research turn into a guaranteed failure. With this off,
    #: Gemini still answers, from its own training data rather than the live
    #: web — :class:`ResearchResult` then carries no sources, which the
    #: existing "No external sources" panel already tells the reader plainly,
    #: so nothing here needs to invent a second way of saying the same thing.
    gemini_grounding_enabled: bool = False
    #: Streaming is used for every call, so this can be generous without
    #: risking an HTTP timeout mid-report.
    ai_max_output_tokens: int = Field(default=64_000, ge=1_024, le=128_000)
    #: Ceiling on searches per research turn. Guards both latency and spend.
    ai_web_search_max_uses: int = Field(default=8, ge=1, le=30)
    #: A deep research turn legitimately runs for minutes.
    ai_request_timeout_seconds: float = Field(default=300.0, gt=0, le=900.0)
    #: ``pause_turn`` resumes before the turn is abandoned (server-tool loops).
    ai_max_continuations: int = Field(default=4, ge=0, le=10)
    #: Research turns started per user per hour. Applied in Redis.
    ai_rate_limit_per_hour: int = Field(default=40, ge=1, le=1000)

    # --- Observability (ADR-018) -------------------------------------------
    log_level: LogLevel = "INFO"
    log_json: bool = True

    @property
    def ai_credential(self) -> SecretStr | None:
        """The key for the *selected* provider, and only that one.

        Resolved by ``ai_provider`` rather than by "whichever key is set", so a
        deployment holding both credentials calls the vendor it was configured
        to call. A key for the other vendor is not a fallback.
        """
        if self.ai_provider == "gemini":
            return self.gemini_api_key
        return self.anthropic_api_key

    @property
    def ai_active_model(self) -> str:
        """The model id the selected provider will actually call."""
        return self.gemini_model if self.ai_provider == "gemini" else self.ai_model

    @property
    def ai_configured(self) -> bool:
        """Whether the AI gateway has a credential to call a model with.

        False is a first-class state, not an error: AI routes answer 503 with
        ``ai_not_configured`` and the frontend renders its existing
        "AI is not connected" surface. Nothing degrades to canned output.
        """
        key = self.ai_credential
        return bool(key and key.get_secret_value().strip())

    @property
    def storage_configured(self) -> bool:
        """Whether object storage has everything it needs to sign a URL.

        Attachment endpoints report 503 when this is false rather than failing
        deep inside boto3 with a credentials error. Outside development the
        validator below makes the false case unreachable.
        """
        return bool(
            self.storage_bucket and self.storage_access_key_id and self.storage_secret_access_key
        )

    @property
    def storage_browser_endpoint_url(self) -> str | None:
        """Endpoint a pre-signed URL handed to a browser must be built against."""
        return self.storage_public_endpoint_url or self.storage_endpoint_url

    @property
    def cookie_secure(self) -> bool:
        """Refresh cookies are Secure everywhere except local development."""
        return self.environment != "development"

    @property
    def cors_origins(self) -> list[str]:
        """Parsed allow-list of browser origins."""
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @field_validator("jwt_private_key", "jwt_public_key", mode="before")
    @classmethod
    def _normalise_pem(cls, value: str | None) -> str | None:
        r"""Accept PEM supplied with literal ``\n`` escapes.

        Container orchestrators and CI secret stores frequently cannot hold a
        real newline in an environment variable, so the escaped form is the
        common way to ship a PEM key.
        """
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned.replace("\\n", "\n")

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        """Require the async driver so the sync driver is never used by accident."""
        if not value.startswith("postgresql+asyncpg://"):
            msg = (
                "DATABASE_URL must use the async driver and start with "
                "'postgresql+asyncpg://' (SQLAlchemy 2.0 async, ADR-006)."
            )
            raise ValueError(msg)
        return value

    @field_validator("redis_url")
    @classmethod
    def _validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://", "unix://")):
            msg = "REDIS_URL must start with 'redis://', 'rediss://' or 'unix://'."
            raise ValueError(msg)
        return value

    @field_validator("api_prefix")
    @classmethod
    def _validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            msg = "API_PREFIX must start with '/'."
            raise ValueError(msg)
        return value.rstrip("/")

    @model_validator(mode="after")
    def _reject_insecure_production(self) -> Settings:
        """Refuse to run production with development conveniences enabled."""
        if self.environment == "production":
            if self.debug:
                msg = "DEBUG must be false when ENVIRONMENT=production."
                raise ValueError(msg)
            if self.db_echo:
                msg = "DB_ECHO must be false when ENVIRONMENT=production (leaks SQL and data)."
                raise ValueError(msg)
        if self.environment in ("staging", "production") and not (
            self.jwt_private_key and self.jwt_public_key
        ):
            msg = (
                "JWT_PRIVATE_KEY and JWT_PUBLIC_KEY are required when "
                f"ENVIRONMENT={self.environment}. Generate an Ed25519 keypair and supply "
                "both in PEM format; an ephemeral key would invalidate every token on "
                "restart and cannot be shared between replicas."
            )
            raise ValueError(msg)
        if self.environment in ("staging", "production") and not self.storage_configured:
            msg = (
                "STORAGE_BUCKET, STORAGE_ACCESS_KEY_ID and STORAGE_SECRET_ACCESS_KEY "
                f"are required when ENVIRONMENT={self.environment}. Attachments have "
                "nowhere to go without them, and starting anyway would accept uploads "
                "that fail at the last step."
            )
            raise ValueError(msg)
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def docs_url(self) -> str | None:
        """OpenAPI docs are disabled in production."""
        return None if self.is_production else "/docs"

    @property
    def openapi_url(self) -> str | None:
        return None if self.is_production else "/openapi.json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached, validated settings singleton.

    Raises:
        ConfigurationError: if any required setting is missing or invalid. The
            message names the offending fields but never echoes their values,
            so secrets stay out of logs and crash reports.
    """
    try:
        # All values come from the environment or .env; none are passed here.
        return Settings()
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or '<root>'}: {error['msg']}"
            for error in exc.errors()
        )
        msg = (
            "Invalid application configuration. Copy backend/.env.example to "
            f"backend/.env and correct the following: {details}"
        )
        raise ConfigurationError(msg) from exc


def load_settings_or_exit() -> Settings:
    """Load settings, printing a readable error and exiting on failure.

    Used by the ASGI entrypoint so a misconfigured container dies immediately
    with an actionable message rather than a Pydantic traceback.
    """
    try:
        return get_settings()
    except ConfigurationError as exc:
        # Logging is not configured yet at this point, so write straight to stderr.
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
