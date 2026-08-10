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

    # --- Observability (ADR-018) -------------------------------------------
    log_level: LogLevel = "INFO"
    log_json: bool = True

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
