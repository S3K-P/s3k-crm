"""Structured logging configuration (ADR-018: structlog JSON).

Console rendering is used outside production for readability; production emits
one JSON object per line so logs are queryable in Grafana Cloud.

``merge_contextvars`` is the first processor, so anything bound with
``structlog.contextvars.bind_contextvars`` — notably ``tenant_id`` and
``user_id`` from :class:`~app.core.tenant.TenantContextMiddleware` — appears on
every log line emitted during that request without being passed explicitly.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog and route stdlib logging through it."""
    level = logging.getLevelNamesMapping()[settings.log_level]

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if settings.log_json
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Uvicorn's own loggers would otherwise double-emit their default format.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module name."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
