"""Liveness and readiness endpoints.

``GET /health``       — process liveness. Never touches a dependency.
``GET /health/ready`` — dependency readiness. 200 only when PostgreSQL **and**
                        Redis both answer; 503 with a safe structured body
                        otherwise.

Neither response exposes connection strings, hostnames, driver messages or any
other internal infrastructure detail. Settings are read from application state
rather than the global singleton so a test (or a second mounted app) sees its
own configuration.
"""

from __future__ import annotations

from typing import Literal

import structlog
from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from app.core import database
from app.core import redis as redis_module
from app.core.config import Settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])

DependencyStatus = Literal["up", "down"]


class HealthResponse(BaseModel):
    """Liveness payload."""

    service: str = Field(examples=["s3k-crm-backend"])
    status: Literal["healthy"] = "healthy"
    environment: str = Field(examples=["development"])


class ReadinessResponse(BaseModel):
    """Readiness payload including per-dependency status."""

    service: str
    status: Literal["ready", "not_ready"]
    environment: str
    dependencies: dict[str, DependencyStatus]


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness probe",
    status_code=status.HTTP_200_OK,
)
async def health(request: Request) -> HealthResponse:
    """Return 200 whenever the application process is running."""
    settings: Settings = request.app.state.settings
    return HealthResponse(service=settings.app_name, environment=settings.environment)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe (PostgreSQL + Redis)",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(request: Request, response: Response) -> ReadinessResponse:
    """Return 200 only when every downstream dependency is reachable."""
    settings: Settings = request.app.state.settings
    dependencies: dict[str, DependencyStatus] = {}

    try:
        await database.check_database_connection(request.app.state.engine)
        dependencies["database"] = "up"
    except Exception as exc:  # any failure at all means "not ready"
        # Detail goes to the log, never to the client.
        logger.warning("readiness_dependency_down", dependency="database", error=str(exc))
        dependencies["database"] = "down"

    try:
        await redis_module.check_redis_connection(request.app.state.redis)
        dependencies["redis"] = "up"
    except Exception as exc:  # any failure at all means "not ready"
        logger.warning("readiness_dependency_down", dependency="redis", error=str(exc))
        dependencies["redis"] = "down"

    ready = all(state == "up" for state in dependencies.values())
    response.status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        service=settings.app_name,
        status="ready" if ready else "not_ready",
        environment=settings.environment,
        dependencies=dependencies,
    )
