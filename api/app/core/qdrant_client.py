from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models


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

    async def ensure_hybrid_collection(self, collection_name: str, vector_size: int) -> None:
        """Create a collection configured for dense and sparse retrieval if missing."""

        exists = await self._client.collection_exists(collection_name)
        if exists:
            return

        await self._client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                    on_disk=True,
                )
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )

    async def upsert_chunks(
        self,
        collection_name: str,
        points: list[models.PointStruct],
    ) -> None:
        """Upsert chunk vectors and filter payloads into Qdrant."""

        if not points:
            return
        await self._client.upsert(collection_name=collection_name, points=points, wait=False)

    async def close(self) -> None:
        """Close Qdrant HTTP and gRPC resources."""

        await self._client.close()
