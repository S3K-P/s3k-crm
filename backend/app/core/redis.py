"""Async Redis client with lifecycle management.

Scope is deliberately narrow: connection management and a health probe only.
Caching, rate limiting, idempotency keys and the ARQ queue (ADR-013) are
implemented in later phases.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.config import Settings

logger = structlog.get_logger(__name__)


def create_redis_client(settings: Settings) -> Redis:
    """Build the async Redis client.

    ``Redis.from_url`` is lazy: no socket is opened until the first command,
    so this is safe to call during application construction.
    """
    return Redis.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        socket_timeout=settings.redis_socket_timeout,
        socket_connect_timeout=settings.redis_socket_timeout,
        decode_responses=True,
        health_check_interval=30,
    )


async def close_redis_client(client: Redis) -> None:
    """Release the connection pool during shutdown."""
    await client.aclose()
    logger.info("redis_client_closed")


async def check_redis_connection(client: Redis) -> None:
    """Probe Redis connectivity.

    Raises:
        Exception: any connection or protocol error, surfaced to the readiness
            endpoint which converts it into a safe 503 response.
    """
    await client.ping()


async def get_redis(request: Request) -> Redis:
    """FastAPI dependency returning the shared Redis client."""
    client: Redis = request.app.state.redis
    return client


RedisClient = Annotated[Redis, Depends(get_redis)]
