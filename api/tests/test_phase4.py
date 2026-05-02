from uuid import uuid4

from qdrant_client.http import models

from api.app.api.v1.retrieval import build_cache_key
from api.app.config import Settings
from api.app.main import create_app
from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.schemas.retrieval import RetrievalRequest
from api.app.services.retrieval_service import (
    Candidate,
    build_qdrant_filter,
    document_matches_governance_filters,
    rank_scored_chunks_by_authority,
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


def test_retrieval_governance_defaults_to_published_documents() -> None:
    """Retrieval hides draft/reviewed documents unless explicitly included."""

    published = Document(id=uuid4(), kb_id=uuid4(), name="published", review_status="published")
    draft = Document(id=uuid4(), kb_id=published.kb_id, name="draft", review_status="draft")

    assert document_matches_governance_filters(published, {})
    assert not document_matches_governance_filters(draft, {})
    assert document_matches_governance_filters(draft, {"include_unpublished": True})


def test_authority_ranking_prefers_lower_authority_levels() -> None:
    """Official sources rank ahead of lower-authority experience when both match."""

    kb_id = uuid4()
    official_doc = Document(id=uuid4(), kb_id=kb_id, name="law", authority_level=1)
    raw_doc = Document(id=uuid4(), kb_id=kb_id, name="chat", authority_level=5)
    official_chunk = Chunk(
        id=uuid4(),
        document_id=official_doc.id,
        kb_id=kb_id,
        content="law",
        chunk_index=0,
    )
    raw_chunk = Chunk(
        id=uuid4(),
        document_id=raw_doc.id,
        kb_id=kb_id,
        content="chat",
        chunk_index=1,
    )

    ranked = rank_scored_chunks_by_authority(
        [(raw_chunk, 0.99), (official_chunk, 0.2)],
        {raw_chunk.id: 0.99, official_chunk.id: 0.2},
        {official_doc.id: official_doc, raw_doc.id: raw_doc},
    )

    assert ranked[0][0] is official_chunk


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
