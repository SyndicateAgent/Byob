from asyncio import wait_for
from collections.abc import Mapping

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

VISUAL_COLLECTION_SUFFIX = "_visual"


def visual_collection_name(collection_name: str) -> str:
    """Return the companion Qdrant collection used for CLIP image vectors."""

    return f"{collection_name}{VISUAL_COLLECTION_SUFFIX}"


class QdrantStoreClient:
    """Async Qdrant client wrapper for vector store operations."""

    def __init__(
        self,
        url: str,
        timeout_seconds: float,
        *,
        health_timeout_seconds: float | None = None,
        upsert_batch_size: int = 128,
    ) -> None:
        self._health_timeout_seconds = health_timeout_seconds or timeout_seconds
        self._upsert_batch_size = max(upsert_batch_size, 1)
        self._client = AsyncQdrantClient(
            url=url,
            timeout=max(1, int(timeout_seconds)),
            check_compatibility=False,
            trust_env=False,
        )

    async def ping(self) -> None:
        """Verify Qdrant is reachable."""

        await wait_for(
            self._client.get_collections(),
            timeout=max(1.0, self._health_timeout_seconds),
        )

    async def collection_exists(self, collection_name: str) -> bool:
        """Return whether a collection exists."""

        return bool(await self._client.collection_exists(collection_name))

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

    async def ensure_visual_collection(self, collection_name: str, vector_size: int) -> None:
        """Create a collection configured for CLIP image retrieval if missing."""

        exists = await self._client.collection_exists(collection_name)
        if exists:
            return

        await self._client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "visual": models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                    on_disk=True,
                )
            },
        )

    async def upsert_chunks(
        self,
        collection_name: str,
        points: list[models.PointStruct],
    ) -> None:
        """Upsert chunk vectors and filter payloads into Qdrant."""

        if not points:
            return
        try:
            for batch in point_batches(points, getattr(self, "_upsert_batch_size", 128)):
                await self._client.upsert(
                    collection_name=collection_name,
                    points=batch,
                    wait=False,
                )
        except UnexpectedResponse as exc:
            response = exc.content.decode("utf-8", errors="replace")
            summary = describe_points(points)
            raise RuntimeError(
                "Qdrant upsert failed "
                f"collection={collection_name!r} point_count={len(points)} "
                f"vectors={summary}: {exc.status_code} {exc.reason_phrase}: {response}"
            ) from exc

    async def delete_points(self, collection_name: str, point_ids: list[str]) -> None:
        """Delete chunk vector points from Qdrant by point id."""

        if not point_ids:
            return
        exists = await self._client.collection_exists(collection_name)
        if not exists:
            return
        await self._client.delete(
            collection_name=collection_name,
            points_selector=models.PointIdsList(points=point_ids),
            wait=True,
        )

    async def delete_collection(self, collection_name: str) -> None:
        """Delete a Qdrant collection if it exists."""

        exists = await self._client.collection_exists(collection_name)
        if not exists:
            return
        await self._client.delete_collection(collection_name=collection_name)

    async def set_payload(
        self,
        collection_name: str,
        point_ids: list[str],
        payload: dict[str, object],
    ) -> None:
        """Update payload fields for existing Qdrant points."""

        if not point_ids:
            return
        exists = await self._client.collection_exists(collection_name)
        if not exists:
            return
        await self._client.set_payload(
            collection_name=collection_name,
            payload=payload,
            points=models.PointIdsList(points=point_ids),
            wait=True,
        )

    async def query_dense(
        self,
        collection_name: str,
        vector: list[float],
        query_filter: models.Filter,
        limit: int,
    ) -> list[models.ScoredPoint]:
        """Query the dense vector field in a collection."""

        response = await self._client.query_points(
            collection_name=collection_name,
            query=vector,
            using="dense",
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return list(response.points)

    async def query_sparse(
        self,
        collection_name: str,
        vector: models.SparseVector,
        query_filter: models.Filter,
        limit: int,
    ) -> list[models.ScoredPoint]:
        """Query the sparse keyword vector field in a collection."""

        response = await self._client.query_points(
            collection_name=collection_name,
            query=vector,
            using="sparse",
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return list(response.points)

    async def query_visual(
        self,
        collection_name: str,
        vector: list[float],
        query_filter: models.Filter,
        limit: int,
    ) -> list[models.ScoredPoint]:
        """Query the CLIP visual vector field in a collection."""

        exists = await self._client.collection_exists(collection_name)
        if not exists:
            return []
        response = await self._client.query_points(
            collection_name=collection_name,
            query=vector,
            using="visual",
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return list(response.points)

    async def close(self) -> None:
        """Close Qdrant HTTP and gRPC resources."""

        await self._client.close()


def describe_points(points: list[models.PointStruct]) -> str:
    """Return a compact vector-shape summary for Qdrant error messages."""

    if not points:
        return "empty"

    point = points[0]
    vector = point.vector
    if isinstance(vector, Mapping):
        parts = [describe_vector(name, value) for name, value in vector.items()]
        return "{" + ", ".join(parts) + "}"
    if isinstance(vector, list):
        return f"dense:{len(vector)}"
    return type(vector).__name__


def point_batches(
    points: list[models.PointStruct],
    batch_size: int,
) -> list[list[models.PointStruct]]:
    """Split Qdrant points into non-empty batches."""

    size = max(batch_size, 1)
    return [points[index : index + size] for index in range(0, len(points), size)]


def describe_vector(name: str, value: object) -> str:
    """Return a compact description of one named vector."""

    if isinstance(value, list):
        return f"{name}:dense:{len(value)}"
    if isinstance(value, models.SparseVector):
        return f"{name}:sparse:{len(value.indices)}"
    return f"{name}:{type(value).__name__}"
