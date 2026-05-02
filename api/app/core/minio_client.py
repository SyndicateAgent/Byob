from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urljoin

import aioboto3  # type: ignore[import-untyped]
import httpx
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from api.app.config import Settings

BUCKET_EXISTS_ERROR_CODES = {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}
MISSING_BUCKET_ERROR_CODES = {"NoSuchBucket", "NoSuchBucketPolicy"}


@dataclass(frozen=True)
class StoredObject:
    """Object bytes and metadata loaded from MinIO."""

    content: bytes
    content_type: str


def is_bucket_exists_error(exc: ClientError) -> bool:
    """Return whether S3 reports that bucket creation is already satisfied."""

    error = exc.response.get("Error", {})
    return error.get("Code") in BUCKET_EXISTS_ERROR_CODES


def is_missing_bucket_error(exc: ClientError) -> bool:
    """Return whether S3 reports that the bucket is already absent."""

    error = exc.response.get("Error", {})
    return error.get("Code") in MISSING_BUCKET_ERROR_CODES


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

    async def delete_object(self, key: str | None) -> None:
        """Delete one object key if it exists."""

        if not key:
            return
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        ) as client:
            try:
                await client.delete_object(Bucket=self._bucket, Key=key)
            except ClientError as exc:
                if not is_missing_bucket_error(exc):
                    raise

    async def delete_prefix(self, prefix: str) -> int:
        """Delete all objects under a prefix and return the number requested."""

        if not prefix:
            return 0
        deleted = 0
        continuation_token: str | None = None
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
        ) as client:
            while True:
                list_kwargs: dict[str, object] = {"Bucket": self._bucket, "Prefix": prefix}
                if continuation_token:
                    list_kwargs["ContinuationToken"] = continuation_token
                try:
                    response = await client.list_objects_v2(**list_kwargs)
                except ClientError as exc:
                    if is_missing_bucket_error(exc):
                        return deleted
                    raise

                objects = [
                    {"Key": key}
                    for item in response.get("Contents", [])
                    if isinstance((key := item.get("Key")), str)
                ]
                for index in range(0, len(objects), 1000):
                    batch = objects[index : index + 1000]
                    if not batch:
                        continue
                    await client.delete_objects(
                        Bucket=self._bucket,
                        Delete={"Objects": batch, "Quiet": True},
                    )
                    deleted += len(batch)

                if not response.get("IsTruncated"):
                    return deleted
                token = response.get("NextContinuationToken")
                continuation_token = token if isinstance(token, str) else None
                if continuation_token is None:
                    return deleted

    async def close(self) -> None:
        """Close MinIO HTTP resources."""

        await self._client.aclose()
