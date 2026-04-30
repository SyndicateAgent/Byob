import httpx

from api.app.config import Settings


class RerankClient:
    """Client for an external rerank endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.rerank_enabled
        self._endpoint_url = str(settings.rerank_endpoint_url).rstrip("/")
        self._model = settings.rerank_model
        self._client = httpx.AsyncClient(timeout=30.0, trust_env=False)

    async def rerank(self, query: str, documents: list[str]) -> list[float] | None:
        """Return rerank scores when configured, otherwise no-op."""

        if not self._enabled or not documents:
            return None

        response = await self._client.post(
            f"{self._endpoint_url}/rerank",
            json={"model": self._model, "query": query, "documents": documents},
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list):
            raise RuntimeError("Rerank response does not contain results")

        scores = [0.0] * len(documents)
        for item in results:
            index = int(item["index"])
            scores[index] = float(item["relevance_score"])
        return scores

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()
