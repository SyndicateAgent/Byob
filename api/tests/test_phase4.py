from uuid import uuid4

from qdrant_client.http import models

from api.app.api.v1.retrieval import build_cache_key
from api.app.config import Settings
from api.app.core.clip_embedding import ClipEmbeddingClient
from api.app.core.qdrant_client import visual_collection_name
from api.app.main import create_app
from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.document_asset import DocumentAsset
from api.app.schemas.retrieval import RetrievalRequest
from api.app.services.ingestion_service import (
    StoredParsedAsset,
    chunks_by_asset_id,
    document_asset_api_url,
)
from api.app.services.retrieval_service import (
    Candidate,
    build_qdrant_filter,
    dedupe_asset_keys,
    document_matches_governance_filters,
    rank_scored_chunks_by_authority,
    referenced_asset_keys,
    rrf_fuse,
    visual_asset_keys_from_points,
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


def test_authority_ranking_prefers_lower_numeric_authority_values() -> None:
    """User-defined authority values sort lower numbers ahead of higher numbers."""

    kb_id = uuid4()
    primary_doc = Document(id=uuid4(), kb_id=kb_id, name="primary", authority_level=2)
    reference_doc = Document(id=uuid4(), kb_id=kb_id, name="reference", authority_level=42)
    primary_chunk = Chunk(
        id=uuid4(),
        document_id=primary_doc.id,
        kb_id=kb_id,
        content="primary",
        chunk_index=0,
    )
    reference_chunk = Chunk(
        id=uuid4(),
        document_id=reference_doc.id,
        kb_id=kb_id,
        content="reference",
        chunk_index=1,
    )

    ranked = rank_scored_chunks_by_authority(
        [(reference_chunk, 0.99), (primary_chunk, 0.2)],
        {reference_chunk.id: 0.99, primary_chunk.id: 0.2},
        {primary_doc.id: primary_doc, reference_doc.id: reference_doc},
    )

    assert ranked[0][0] is primary_chunk


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


def test_visual_collection_name_is_companion_collection() -> None:
    """CLIP image vectors are stored in a separate collection per knowledge base."""

    assert visual_collection_name("kb_123") == "kb_123_visual"


async def test_clip_warmup_is_noop_when_multimodal_rag_is_disabled() -> None:
    """Startup model preloading should be skipped when multimodal RAG is disabled."""

    client = ClipEmbeddingClient(
        Settings(
            app_env="test",
            multimodal_rag_enabled=False,
            clip_preload_on_startup=True,
        )
    )

    await client.warmup()

    assert client.enabled is False


def test_chunks_by_asset_id_links_images_to_referencing_chunks() -> None:
    """Visual asset points should route back to the chunk that references the image."""

    document_id = uuid4()
    kb_id = uuid4()
    asset_id = uuid4()
    chunk = Chunk(
        id=uuid4(),
        document_id=document_id,
        kb_id=kb_id,
        chunk_index=0,
        content=f"See ![chart]({document_asset_api_url(document_id, asset_id)})",
    )
    asset = DocumentAsset(
        id=asset_id,
        document_id=document_id,
        kb_id=kb_id,
        asset_index=0,
        source_path="images/chart.png",
        minio_path="objects/chart.png",
        content_type="image/png",
        file_size=4,
        file_hash="hash",
    )

    matches = chunks_by_asset_id([chunk], [StoredParsedAsset(row=asset, content=b"data")])

    assert matches[asset_id] is chunk


def test_visual_asset_keys_from_points_attach_assets_to_chunks() -> None:
    """Visual Qdrant hits expose the image asset that caused the match."""

    chunk_id = uuid4()
    document_id = uuid4()
    asset_id = uuid4()
    point = models.ScoredPoint(
        id=str(asset_id),
        version=1,
        score=0.9,
        payload={
            "chunk_id": str(chunk_id),
            "doc_id": str(document_id),
            "asset_id": str(asset_id),
        },
    )

    assert visual_asset_keys_from_points([point]) == {chunk_id: [(document_id, asset_id)]}
    assert dedupe_asset_keys([(document_id, asset_id), (document_id, asset_id)]) == [
        (document_id, asset_id)
    ]
