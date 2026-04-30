from urllib.parse import urljoin

import httpx


class MinioClient:
    """Async MinIO client wrapper for object storage health checks."""

    def __init__(self, endpoint_url: str, timeout_seconds: float) -> None:
        self._health_url = urljoin(endpoint_url.rstrip("/") + "/", "minio/health/live")
        self._client = httpx.AsyncClient(timeout=timeout_seconds, trust_env=False)

    async def ping(self) -> None:
        """Verify MinIO's live health endpoint responds successfully."""

        response = await self._client.get(self._health_url)
        response.raise_for_status()

    async def close(self) -> None:
        """Close MinIO HTTP resources."""

        await self._client.aclose()
