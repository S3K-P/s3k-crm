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

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]


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

    # --- Observability (ADR-018) -------------------------------------------
    log_level: LogLevel = "INFO"
    log_json: bool = True

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
