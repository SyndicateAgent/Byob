from fastapi import APIRouter, Request
from starlette.responses import Response

from api.app.config import Settings
from api.app.core.health import aggregate_health_status, collect_dependency_checks
from api.app.core.metrics import render_metrics
from api.app.schemas.health import HealthCheck, HealthResponse

router = APIRouter(tags=["monitoring"])


@router.get("/healthz", response_model=HealthResponse, summary="Service health check")
async def healthz(request: Request) -> HealthResponse:
    """Return the current service health state."""

    settings: Settings = request.app.state.settings
    checks = [HealthCheck(name="app", status="ok")]
    if settings.dependency_health_checks_enabled:
        checks.extend(await collect_dependency_checks(request.app.state))

    return HealthResponse(
        request_id=request.state.request_id,
        status=aggregate_health_status(checks),
        service=settings.app_name,
        environment=settings.app_env,
        version=settings.app_version,
        checks=checks,
    )


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Return Prometheus metrics for scraping."""

    return render_metrics()
