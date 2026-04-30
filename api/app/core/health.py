from asyncio import gather
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Protocol

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from api.app.core.es_client import ElasticsearchClient
from api.app.core.minio_client import MinioClient
from api.app.core.qdrant_client import QdrantStoreClient
from api.app.core.redis_client import RedisClient
from api.app.schemas.health import ComponentStatus, HealthCheck

HealthOperation = Callable[[], Awaitable[None]]


class DependencyState(Protocol):
    """Application state attributes required for dependency health checks."""

    db_engine: AsyncEngine
    redis_client: RedisClient
    qdrant_client: QdrantStoreClient
    elasticsearch_client: ElasticsearchClient
    minio_client: MinioClient


async def probe_dependency(name: str, operation: HealthOperation) -> HealthCheck:
    """Run one dependency health operation and return a public health check."""

    logger = structlog.get_logger(__name__)
    start = perf_counter()
    try:
        await operation()
    except Exception as exc:  # noqa: BLE001
        latency_ms = round((perf_counter() - start) * 1000, 2)
        logger.warning(
            "dependency_health_check_failed",
            dependency=name,
            error_type=type(exc).__name__,
        )
        return HealthCheck(name=name, status="down", latency_ms=latency_ms)

    latency_ms = round((perf_counter() - start) * 1000, 2)
    return HealthCheck(name=name, status="ok", latency_ms=latency_ms)


def aggregate_health_status(checks: list[HealthCheck]) -> ComponentStatus:
    """Return an aggregate status for a collection of health checks."""

    if all(check.status == "ok" for check in checks):
        return "ok"
    if any(check.status == "ok" for check in checks):
        return "degraded"
    return "down"


async def check_postgres(engine: AsyncEngine) -> None:
    """Verify PostgreSQL accepts a trivial query."""

    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def collect_dependency_checks(app_state: DependencyState) -> list[HealthCheck]:
    """Collect health checks for all Phase 1 infrastructure dependencies."""

    db_engine: AsyncEngine = app_state.db_engine
    redis_client: RedisClient = app_state.redis_client
    qdrant_client: QdrantStoreClient = app_state.qdrant_client
    elasticsearch_client: ElasticsearchClient = app_state.elasticsearch_client
    minio_client: MinioClient = app_state.minio_client

    checks = await gather(
        probe_dependency("postgres", lambda: check_postgres(db_engine)),
        probe_dependency("redis", redis_client.ping),
        probe_dependency("qdrant", qdrant_client.ping),
        probe_dependency("elasticsearch", elasticsearch_client.ping),
        probe_dependency("minio", minio_client.ping),
    )
    return list(checks)
