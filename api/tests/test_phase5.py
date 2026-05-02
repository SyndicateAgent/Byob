from uuid import uuid4

from api.app.api.v1.retrieval import dedupe_queries, merge_responses
from api.app.config import Settings
from api.app.main import create_app
from api.app.schemas.retrieval import (
    EnhancementInfo,
    RetrievalDocument,
    RetrievalEnhancements,
    RetrievalResponse,
    RetrievalResult,
    RetrievalStats,
)
from api.app.services.query_enhancer import decompose_query, enhance_query, rewrite_query


def retrieval_document() -> RetrievalDocument:
    return RetrievalDocument(
        id=uuid4(),
        name="doc",
        metadata={},
        governance_source_type="client_policy_archive",
        authority_level=42,
        review_status="published",
    )


def test_phase_five_routes_are_mounted() -> None:
    """Advanced retrieval capability routes are registered."""

    app = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v1/retrieval/search/advanced" in paths
    assert "/api/v1/retrieval/multi-search" in paths
    assert "/api/v1/retrieval/rerank" in paths
    assert "/api/v1/retrieval/embed" in paths
    assert "/api/v1/retrieval/{request_id}/feedback" in paths


def test_query_enhancer_generates_requested_metadata() -> None:
    """Query enhancer returns rewrite, decomposition, and HyDE metadata."""

    info = enhance_query(
        " alpha and beta? ",
        RetrievalEnhancements(query_rewrite=True, decompose=True, hyde=True, max_sub_queries=2),
    )

    assert isinstance(info, EnhancementInfo)
    assert info.rewritten_query == "alpha and beta"
    assert info.sub_queries == ["alpha", "beta"]
    assert info.hyde_doc is not None
    assert "alpha and beta" in info.hyde_doc


def test_query_helpers_are_deterministic() -> None:
    """Low-level query helpers normalize and dedupe predictably."""

    assert rewrite_query(" hello? ") == "hello"
    assert decompose_query("a, b, c", 2) == ["a", "b"]
    assert dedupe_queries(["a", "a", " ", "b"]) == ["a", "b"]


def test_merge_responses_keeps_best_score_per_chunk() -> None:
    """Advanced search response merging deduplicates by chunk id."""

    chunk_id = uuid4()
    document = retrieval_document()
    low = RetrievalResult(
        chunk_id=chunk_id,
        content="low",
        score=0.1,
        rerank_score=None,
        document=document,
        kb_id=uuid4(),
        chunk_type="text",
        page_num=None,
        bbox=None,
        metadata={},
    )
    high = low.model_copy(update={"content": "high", "score": 0.9})
    response_a = RetrievalResponse(
        request_id="req_a",
        results=[low],
        stats=RetrievalStats(
            total_latency_ms=1,
            stages={"embedding_ms": 1},
            total_candidates=1,
            after_fusion=1,
            after_rerank=1,
        ),
    )
    response_b = response_a.model_copy(update={"request_id": "req_b", "results": [high]})

    merged = merge_responses("req_final", [response_a, response_b], top_k=5)

    assert merged.request_id == "req_final"
    assert len(merged.results) == 1
    assert merged.results[0].content == "high"
