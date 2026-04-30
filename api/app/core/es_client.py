from elasticsearch import AsyncElasticsearch


class ElasticsearchClient:
    """Async Elasticsearch client wrapper for BM25 retrieval operations."""

    def __init__(self, url: str, timeout_seconds: float) -> None:
        self._client = AsyncElasticsearch(hosts=[url], request_timeout=timeout_seconds)

    async def ping(self) -> None:
        """Verify Elasticsearch accepts cluster requests."""

        response = await self._client.ping()
        if response is not True:
            raise RuntimeError("Elasticsearch ping failed")

    async def close(self) -> None:
        """Close Elasticsearch transport resources."""

        await self._client.close()
