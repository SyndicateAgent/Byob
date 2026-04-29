from fastapi import FastAPI

from api.app.api.health import router as health_router
from api.app.config import Settings, get_settings
from api.app.core.logging import configure_logging
from api.app.core.metrics import MetricsMiddleware
from api.app.middleware.request_context import RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    app = FastAPI(
        title="Knowledge Base Platform API",
        description="Enterprise knowledge base platform/BaaS API. No Agent logic is implemented.",
        version=resolved_settings.app_version,
        openapi_version="3.1.0",
    )
    app.state.settings = resolved_settings

    app.add_middleware(MetricsMiddleware, enabled=resolved_settings.prometheus_metrics_enabled)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health_router)

    return app


app = create_app()
