"""Tests for typed configuration loading and fail-fast validation."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import ConfigurationError, Settings, get_settings
from tests.conftest import TEST_JWT_PRIVATE_KEY, TEST_JWT_PUBLIC_KEY

VALID_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://user:pw@db:5432/s3k",
    "REDIS_URL": "redis://cache:6379/0",
    # Required from staging upwards; harmless in development/test.
    "JWT_PRIVATE_KEY": TEST_JWT_PRIVATE_KEY,
    "JWT_PUBLIC_KEY": TEST_JWT_PUBLIC_KEY,
    # Likewise required from staging upwards: attachments have nowhere to go
    # without them, so a deployed environment refuses to start. Placeholders —
    # nothing here reaches an object store. That the requirement is *enforced*
    # is pinned separately by
    # ``test_attachment_storage_failures.test_staging_refuses_to_start_without_storage``.
    "STORAGE_BUCKET": "test-attachments",
    "STORAGE_ACCESS_KEY_ID": "test-key-id",
    "STORAGE_SECRET_ACCESS_KEY": "test-secret",
}


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Prevent the developer's real .env and shell environment leaking in."""
    for name in (
        "APP_NAME",
        "ENVIRONMENT",
        "DEBUG",
        "API_PREFIX",
        "DATABASE_URL",
        "REDIS_URL",
        "LOG_LEVEL",
        "DB_ECHO",
    ):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_loads_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_NAME", "s3k-crm-backend")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_name == "s3k-crm-backend"
    assert settings.environment == "staging"
    assert settings.log_level == "DEBUG"
    assert settings.database_url == VALID_ENV["DATABASE_URL"]
    assert settings.redis_url == VALID_ENV["REDIS_URL"]


def test_defaults_are_applied_for_optional_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.app_name == "s3k-crm-backend"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.api_prefix == "/api/v1"
    assert settings.log_level == "INFO"
    assert settings.db_pool_size == 5


def test_missing_database_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", VALID_ENV["REDIS_URL"])

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert "database_url" in str(exc_info.value)


def test_missing_redis_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_ENV["DATABASE_URL"])

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert "redis_url" in str(exc_info.value)


def test_get_settings_raises_configuration_error_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The public loader surfaces a readable error, not a raw pydantic traceback."""
    monkeypatch.chdir(tmp_path)  # an empty directory: no .env to fall back on

    with pytest.raises(ConfigurationError) as exc_info:
        get_settings()

    message = str(exc_info.value)
    assert "database_url" in message
    assert ".env.example" in message


def test_sync_database_driver_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@db:5432/s3k")
    monkeypatch.setenv("REDIS_URL", VALID_ENV["REDIS_URL"])

    with pytest.raises(ValidationError, match="asyncpg"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_invalid_redis_scheme_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_ENV["DATABASE_URL"])
    monkeypatch.setenv("REDIS_URL", "http://cache:6379")

    with pytest.raises(ValidationError, match="redis://"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_invalid_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ENVIRONMENT", "prod")  # not a member of the literal

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_production_rejects_debug_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """No insecure production defaults: DEBUG must not be on in production."""
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DEBUG", "true")

    with pytest.raises(ValidationError, match="DEBUG"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_production_rejects_sql_echo(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DB_ECHO", "true")

    with pytest.raises(ValidationError, match="DB_ECHO"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_production_hides_openapi_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ENVIRONMENT", "production")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.is_production is True
    assert settings.docs_url is None
    assert settings.openapi_url is None


def test_api_prefix_must_be_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("API_PREFIX", "api/v1")

    with pytest.raises(ValidationError, match="API_PREFIX"):
        Settings(_env_file=None)  # type: ignore[call-arg]


# --- Email: Microsoft Graph is the only transport -----------------------------

GRAPH_ENV = {
    "MICROSOFT_TENANT_ID": "tenant",
    "MICROSOFT_CLIENT_ID": "client",
    "MICROSOFT_CLIENT_SECRET": "secret-value",
    "MICROSOFT_GRAPH_SENDER_EMAIL": "notifications@s3k.example.com",
}


@pytest.fixture
def _no_graph_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*GRAPH_ENV, "EMAIL_PROVIDER"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.usefixtures("_no_graph_env")
def test_email_is_unconfigured_by_default_and_boot_still_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.email_provider == "null"
    assert settings.graph_email_configured is False


@pytest.mark.usefixtures("_no_graph_env")
@pytest.mark.parametrize("missing", list(GRAPH_ENV))
def test_graph_provider_refuses_to_start_without_every_setting(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    for key, value in {**VALID_ENV, **GRAPH_ENV}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(missing)
    monkeypatch.setenv("EMAIL_PROVIDER", "graph")

    with pytest.raises(ValidationError, match="EMAIL_PROVIDER=graph"):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.usefixtures("_no_graph_env")
def test_graph_provider_starts_with_every_setting_and_hides_the_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {**VALID_ENV, **GRAPH_ENV}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("EMAIL_PROVIDER", "graph")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.graph_email_configured is True
    assert "secret-value" not in repr(settings)
    assert "secret-value" not in str(settings.model_dump())


@pytest.mark.usefixtures("_no_graph_env")
@pytest.mark.parametrize("value", ["smtp", "sendgrid", "resend", "ses"])
def test_no_other_email_transport_can_be_selected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    for key, env_value in VALID_ENV.items():
        monkeypatch.setenv(key, env_value)
    monkeypatch.setenv("EMAIL_PROVIDER", value)

    with pytest.raises(ValidationError, match="email_provider"):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.usefixtures("_no_graph_env")
@pytest.mark.parametrize("environment", ["staging", "production"])
def test_the_console_provider_is_refused_outside_development(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    for key, value in VALID_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("EMAIL_PROVIDER", "console")

    with pytest.raises(ValidationError, match="EMAIL_PROVIDER=console"):
        Settings(_env_file=None)  # type: ignore[call-arg]
