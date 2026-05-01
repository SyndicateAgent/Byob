from uuid import uuid4

from qdrant_client.http import models

from api.app.api.v1.retrieval import build_cache_key
from api.app.config import Settings
from api.app.main import create_app
from api.app.schemas.retrieval import RetrievalRequest
from api.app.services.retrieval_service import (
    Candidate,
    build_qdrant_filter,
    referenced_asset_keys,
    rrf_fuse,
)


def test_phase_four_search_route_is_mounted() -> None:
    """Standard retrieval route is registered under /api/v1."""

    app = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v1/retrieval/search" in paths


def test_rrf_fuse_combines_dense_and_sparse_rankings() -> None:
    """RRF rewards candidates appearing in multiple rankings."""

    first = uuid4()
    second = uuid4()
    third = uuid4()

    fused = rrf_fuse(
        [
            [Candidate(first, 0.9), Candidate(second, 0.8)],
            [Candidate(second, 2.0), Candidate(third, 1.0)],
        ]
    )

    assert fused[0].chunk_id == second
    assert {candidate.chunk_id for candidate in fused} == {first, second, third}


def test_qdrant_filter_includes_allowed_metadata_filters() -> None:
    """Qdrant filters include only caller-requested metadata filters."""

    query_filter = build_qdrant_filter({"chunk_type": "text", "tags": ["manual"]})

    assert isinstance(query_filter.must, list)
    assert len(query_filter.must) == 2
    assert all(isinstance(condition, models.FieldCondition) for condition in query_filter.must)


def test_retrieval_cache_key_is_payload_scoped() -> None:
    """Retrieval cache keys are stable for identical payloads and vary by payload."""

    payload = RetrievalRequest(kb_ids=[uuid4()], query="hello")
    changed = RetrievalRequest(kb_ids=payload.kb_ids, query="hello again")

    assert build_cache_key(payload) == build_cache_key(payload)
    assert build_cache_key(payload) != build_cache_key(changed)


def test_referenced_asset_keys_parse_byob_asset_urls_once() -> None:
    """Retrieval can expose assets referenced by Markdown or HTML chunk content."""

    document_id = uuid4()
    asset_id = uuid4()
    content = (
        f"![plot](/api/v1/documents/{document_id}/assets/{asset_id})\n"
        f'<img src="/api/v1/documents/{document_id}/assets/{asset_id}">'
    )

    assert referenced_asset_keys(content) == [(document_id, asset_id)]
