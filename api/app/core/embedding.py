from collections.abc import Awaitable, Callable

import httpx

from api.app.config import Settings
from api.app.core.http_urls import normalize_loopback_endpoint_url

EmbeddingProgressCallback = Callable[[int, int], Awaitable[None]]
MIN_TIMEOUT_RETRY_CHARS = 1_000


class EmbeddingClient:
    """Async client for an Infinity/OpenAI-compatible embedding endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._endpoint_url = normalize_loopback_endpoint_url(
            str(settings.embedding_endpoint_url)
        ).rstrip("/")
        self.model = settings.embedding_model
        self.batch_size = settings.embedding_batch_size
        self.max_input_chars = settings.embedding_max_input_chars
        self._client = httpx.AsyncClient(
            timeout=settings.embedding_timeout_seconds,
            trust_env=False,
        )

    async def embed_texts(
        self,
        texts: list[str],
        *,
        progress_callback: EmbeddingProgressCallback | None = None,
    ) -> list[list[float]]:
        """Embed texts with the configured embedding service."""

        if not texts:
            return []

        embeddings: list[list[float]] = []
        prepared_texts = [self.prepare_text(text) for text in texts]
        for batch in batched(prepared_texts, self.batch_size):
            embeddings.extend(await self._embed_batch_with_timeout_fallback(batch))
            if progress_callback is not None:
                await progress_callback(len(embeddings), len(texts))
        return embeddings

    async def _embed_batch_with_timeout_fallback(self, texts: list[str]) -> list[list[float]]:
        """Retry slow embedding requests as smaller work units before failing."""

        try:
            return await self._embed_batch(texts)
        except httpx.TimeoutException as exc:
            if len(texts) > 1:
                midpoint = max(1, len(texts) // 2)
                left = await self._embed_batch_with_timeout_fallback(texts[:midpoint])
                right = await self._embed_batch_with_timeout_fallback(texts[midpoint:])
                return [*left, *right]
            shortened = shortened_timeout_retry_text(texts[0])
            if shortened != texts[0]:
                return await self._embed_batch_with_timeout_fallback([shortened])
            raise RuntimeError(
                "Embedding request timed out for a single bounded chunk. "
                "Reduce EMBEDDING_MAX_INPUT_CHARS or increase EMBEDDING_TIMEOUT_SECONDS."
            ) from exc

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed one bounded batch of texts."""

        response = await self._client.post(
            f"{self._endpoint_url}/embeddings",
            json={"model": self.model, "input": texts},
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise RuntimeError("Embedding response does not contain a data list")
        if len(data) != len(texts):
            raise RuntimeError(
                "Embedding response size does not match request size: "
                f"expected {len(texts)}, got {len(data)}"
            )
        return [list(item["embedding"]) for item in data]

    def prepare_text(self, text: str) -> str:
        """Bound one input text before sending it to the embedding service."""

        if len(text) <= self.max_input_chars:
            return text
        return text[: self.max_input_chars].rstrip()

    async def close(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()


def batched(values: list[str], batch_size: int) -> list[list[str]]:
    """Split values into non-empty batches."""

    size = max(batch_size, 1)
    return [values[index : index + size] for index in range(0, len(values), size)]


def shortened_timeout_retry_text(text: str) -> str:
    """Return a shorter single input after an embedding timeout."""

    if len(text) <= MIN_TIMEOUT_RETRY_CHARS:
        return text
    return text[: max(MIN_TIMEOUT_RETRY_CHARS, len(text) // 2)].rstrip()
