from qdrant_client import AsyncQdrantClient


class QdrantStoreClient:
    """Async Qdrant client wrapper for vector store operations."""

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self._client = AsyncQdrantClient(
            url=url,
            timeout=max(1, int(timeout_seconds)),
            check_compatibility=False,
            trust_env=False,
        )

    async def ping(self) -> None:
        """Verify Qdrant is reachable."""

        await self._client.get_collections()

    async def close(self) -> None:
        """Close Qdrant HTTP and gRPC resources."""

        await self._client.close()
