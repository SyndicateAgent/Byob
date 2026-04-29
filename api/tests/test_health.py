import pytest
from httpx import ASGITransport, AsyncClient

from api.app.config import Settings
from api.app.main import create_app


@pytest.mark.asyncio
async def test_healthz_returns_request_id_and_service_state() -> None:
    """Health endpoint returns a stable public response contract."""

    app = create_app(Settings(app_env="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/healthz", headers={"X-Request-ID": "req_test"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req_test"
    assert response.json() == {
        "request_id": "req_test",
        "status": "ok",
        "service": "kb-platform",
        "environment": "test",
        "version": "0.1.0",
        "checks": [{"name": "app", "status": "ok", "latency_ms": None}],
    }


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_text() -> None:
    """Metrics endpoint returns Prometheus text exposition format."""

    app = create_app(Settings(app_env="test"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "kb_platform_http_requests_total" in response.text
