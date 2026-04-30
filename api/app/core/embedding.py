import httpx

from api.app.config import Settings


class EmbeddingClient:
    """Async client for an Infinity/OpenAI-compatible embedding endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._endpoint_url = str(settings.embedding_endpoint_url).rstrip("/")
        self._model = settings.embedding_model
        self._client = httpx.AsyncClient(timeout=30.0, trust_env=False)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed texts with the configured embedding service."""

        response = await self._client.post(
            f"{self._endpoint_url}/embeddings",
            json={"model": self._model, "input": texts},
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise RuntimeError("Embedding response does not contain a data list")
        return [list(item["embedding"]) for item in data]

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()
