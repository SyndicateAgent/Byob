from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app.api.health import router as health_router
from api.app.api.v1 import router as api_v1_router
from api.app.config import Settings, get_settings
from api.app.core.clip_embedding import ClipEmbeddingClient
from api.app.core.embedding import EmbeddingClient
from api.app.core.logging import configure_logging
from api.app.core.metrics import MetricsMiddleware
from api.app.core.minio_client import MinioClient
from api.app.core.qdrant_client import QdrantStoreClient
from api.app.core.redis_client import RedisClient
from api.app.core.rerank import RerankClient
from api.app.db.session import create_engine, create_session_factory
from api.app.middleware.request_context import RequestContextMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and close infrastructure clients for the API process."""

    settings: Settings = app.state.settings
    db_engine = create_engine(settings)
    app.state.db_engine = db_engine
    app.state.db_session_factory = create_session_factory(db_engine)
    app.state.redis_client = RedisClient(
        settings.redis_url, settings.dependency_health_timeout_seconds
    )
    app.state.qdrant_client = QdrantStoreClient(
        str(settings.qdrant_url), settings.dependency_health_timeout_seconds
    )
    app.state.embedding_client = EmbeddingClient(settings)
    app.state.clip_embedding_client = ClipEmbeddingClient(settings)
    if settings.clip_preload_on_startup:
        await app.state.clip_embedding_client.warmup()
    app.state.rerank_client = RerankClient(settings)
    app.state.minio_client = MinioClient(
        str(settings.minio_endpoint_url),
        settings.dependency_health_timeout_seconds,
        settings,
    )

    try:
        yield
    finally:
        await app.state.redis_client.close()
        await app.state.qdrant_client.close()
        await app.state.embedding_client.close()
        await app.state.clip_embedding_client.close()
        await app.state.rerank_client.close()
        await app.state.minio_client.close()
        await db_engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    app = FastAPI(
        title="BYOB API",
        description=(
            "BYOB self-hosted vector database API with a simple "
            "MCP-backed QA Agent tester."
        ),
        version=resolved_settings.app_version,
        openapi_version="3.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings

    app.add_middleware(MetricsMiddleware, enabled=resolved_settings.prometheus_metrics_enabled)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(api_v1_router)

    return app


app = create_app()
