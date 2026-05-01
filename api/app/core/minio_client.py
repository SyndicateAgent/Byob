from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urljoin

import aioboto3  # type: ignore[import-untyped]
import httpx
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from api.app.config import Settings

BUCKET_EXISTS_ERROR_CODES = {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}


@dataclass(frozen=True)
class StoredObject:
    """Object bytes and metadata loaded from MinIO."""

    content: bytes
    content_type: str


def is_bucket_exists_error(exc: ClientError) -> bool:
    """Return whether S3 reports that bucket creation is already satisfied."""

    error = exc.response.get("Error", {})
    return error.get("Code") in BUCKET_EXISTS_ERROR_CODES


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
            try:
                await client.create_bucket(Bucket=self._bucket)
            except ClientError as exc:
                if not is_bucket_exists_error(exc):
                    raise
            await client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )

    async def get_object(self, key: str) -> bytes:
        """Read an object from the configured MinIO bucket."""

        stored_object = await self.get_stored_object(key)
        return stored_object.content

    async def get_stored_object(self, key: str) -> StoredObject:
        """Read an object and its content type from the configured MinIO bucket."""

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
            return StoredObject(
                content=cast(bytes, content),
                content_type=str(response.get("ContentType") or "application/octet-stream"),
            )

    async def close(self) -> None:
        """Close MinIO HTTP resources."""

        await self._client.aclose()
