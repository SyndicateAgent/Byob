import httpx
import pytest

from api.app.config import Settings
from api.app.core import embedding as embedding_module
from api.app.core.embedding import EmbeddingClient
from api.app.core.http_urls import normalize_loopback_endpoint_url


def test_normalize_loopback_endpoint_url_prefers_ipv4() -> None:
    """Windows Docker Desktop can hang on localhost for published model ports."""

    assert normalize_loopback_endpoint_url("http://localhost:7997") == "http://127.0.0.1:7997"
    assert normalize_loopback_endpoint_url("http://embedding.test") == "http://embedding.test"


class FakeEmbeddingResponse:
    """Small response double for OpenAI-compatible embeddings."""

    def __init__(self, inputs: list[str]) -> None:
        self._inputs = inputs

    def raise_for_status(self) -> None:
        """Simulate a successful HTTP response."""

    def json(self) -> dict[str, object]:
        """Return one embedding per requested input."""

        return {
            "data": [
                {"embedding": [float(index), float(len(text))]}
                for index, text in enumerate(self._inputs)
            ]
        }


class FakeAsyncClient:
    """Capture embedding HTTP requests without making network calls."""

    def __init__(self, *, timeout: float, trust_env: bool) -> None:
        self.timeout = timeout
        self.trust_env = trust_env
        self.requests: list[list[str]] = []
        fake_clients.append(self)

    async def post(self, url: str, *, json: dict[str, object]) -> FakeEmbeddingResponse:
        """Capture the embedding request payload."""

        assert url == "http://embedding.test/embeddings"
        assert json["model"] == "test-embedding-model"
        inputs = json["input"]
        assert isinstance(inputs, list)
        assert all(isinstance(item, str) for item in inputs)
        batch = [str(item) for item in inputs]
        self.requests.append(batch)
        return FakeEmbeddingResponse(batch)

    async def aclose(self) -> None:
        """Simulate closing the HTTP client."""


fake_clients: list[FakeAsyncClient] = []


@pytest.mark.asyncio
async def test_embedding_client_batches_and_bounds_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Large documents should be embedded in bounded requests."""

    fake_clients.clear()
    monkeypatch.setattr(embedding_module.httpx, "AsyncClient", FakeAsyncClient)
    client = EmbeddingClient(
        Settings(
            app_env="test",
            embedding_endpoint_url="http://embedding.test",
            embedding_model="test-embedding-model",
            embedding_timeout_seconds=9.5,
            embedding_batch_size=2,
            embedding_max_input_chars=1000,
        )
    )

    long_text = "x" * 1005
    embeddings = await client.embed_texts(["alpha", long_text, "omega"])

    assert fake_clients[0].timeout == 9.5
    assert fake_clients[0].trust_env is False
    assert fake_clients[0].requests == [["alpha", "x" * 1000], ["omega"]]
    assert embeddings == [[0.0, 5.0], [1.0, 1000.0], [0.0, 5.0]]


class TimeoutFallbackAsyncClient(FakeAsyncClient):
    """Force the embedding client to split batches and shorten single inputs."""

    async def post(self, url: str, *, json: dict[str, object]) -> FakeEmbeddingResponse:
        """Timeout on oversized requests, then delegate successful requests."""

        inputs = json["input"]
        assert isinstance(inputs, list)
        if len(inputs) > 1 or any(isinstance(item, str) and len(item) > 2_000 for item in inputs):
            raise httpx.ReadTimeout("slow embedding batch")
        return await super().post(url, json=json)


@pytest.mark.asyncio
async def test_embedding_client_splits_and_shortens_timeout_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slow CPU embedding backends should get smaller retry requests."""

    fake_clients.clear()
    progress: list[tuple[int, int]] = []
    monkeypatch.setattr(embedding_module.httpx, "AsyncClient", TimeoutFallbackAsyncClient)
    client = EmbeddingClient(
        Settings(
            app_env="test",
            embedding_endpoint_url="http://embedding.test",
            embedding_model="test-embedding-model",
            embedding_timeout_seconds=9.5,
            embedding_batch_size=2,
            embedding_max_input_chars=4_000,
        )
    )

    async def report(completed: int, total: int) -> None:
        progress.append((completed, total))

    embeddings = await client.embed_texts(
        ["alpha", "x" * 5_000, "omega"],
        progress_callback=report,
    )

    assert fake_clients[0].requests == [["alpha"], ["x" * 2_000], ["omega"]]
    assert progress == [(2, 3), (3, 3)]
    assert embeddings == [[0.0, 5.0], [0.0, 2000.0], [0.0, 5.0]]