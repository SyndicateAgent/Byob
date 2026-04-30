from time import perf_counter

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_COUNT = Counter(
    "byob_http_requests_total",
    "Total HTTP requests handled by the API service.",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "byob_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record basic Prometheus metrics for HTTP requests."""

    def __init__(self, app: ASGIApp, enabled: bool) -> None:
        super().__init__(app)
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Record request count and latency labels for each response."""

        if not self._enabled:
            return await call_next(request)

        start = perf_counter()
        response = await call_next(request)
        duration = perf_counter() - start
        path = request.scope.get("path", request.url.path)
        status_code = str(response.status_code)

        REQUEST_COUNT.labels(request.method, path, status_code).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(duration)
        return response


def render_metrics() -> Response:
    """Render Prometheus metrics in the standard text exposition format."""

    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
