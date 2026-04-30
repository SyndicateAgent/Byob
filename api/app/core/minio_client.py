from typing import Any, cast
from urllib.parse import urljoin

import aioboto3  # type: ignore[import-untyped]
import httpx

from api.app.config import Settings


class MinioClient:
    """Async MinIO client wrapper for object storage health checks."""

    def __init__(self, endpoint_url: str, timeout_seconds: float, settings: Settings) -> None:
        self._health_url = urljoin(endpoint_url.rstrip("/") + "/", "minio/health/live")
        self._client = httpx.AsyncClient(timeout=timeout_seconds, trust_env=False)
        self._endpoint_url = endpoint_url
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key.get_secret_value()
        self._bucket = settings.minio_bucket
        self._session = aioboto3.Session()

    async def ping(self) -> None:
        """Verify MinIO's live health endpoint responds successfully."""

        response = await self._client.get(self._health_url)
        response.raise_for_status()

    async def put_object(self, key: str, content: bytes, content_type: str) -> None:
        """Store an object in the configured MinIO bucket."""

        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        ) as client:
            await client.create_bucket(Bucket=self._bucket)
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )

    async def get_object(self, key: str) -> bytes:
        """Read an object from the configured MinIO bucket."""

        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        ) as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            response_body = cast(Any, response["Body"])
            async with response_body as stream:
                content = await stream.read()
                return cast(bytes, content)

    async def close(self) -> None:
        """Close MinIO HTTP resources."""

        await self._client.aclose()
