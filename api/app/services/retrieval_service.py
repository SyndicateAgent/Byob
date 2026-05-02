import re
from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID, uuid4

from qdrant_client.http import models
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.config import Settings
from api.app.core.embedding import EmbeddingClient
from api.app.core.qdrant_client import QdrantStoreClient
from api.app.core.rerank import RerankClient
from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.document_asset import DocumentAsset
from api.app.models.knowledge_base import KnowledgeBase
from api.app.models.retrieval_log import RetrievalLog
from api.app.schemas.retrieval import (
    ParentChunkContext,
    RetrievalAssetRef,
    RetrievalDocument,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    RetrievalStats,
)
from api.app.services.ingestion_service import sparse_vector

RRF_K = 60
DEFAULT_REVIEW_STATUS = "published"
ASSET_API_PATH_RE = re.compile(
    r"/api/v1/documents/"
    r"(?P<document_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"/assets/"
    r"(?P<asset_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


@dataclass(frozen=True)
class Candidate:
    """Intermediate retrieval candidate."""

    chunk_id: UUID
    score: float


async def search(
    session: AsyncSession,
    settings: Settings,
    qdrant_client: QdrantStoreClient,
    embedding_client: EmbeddingClient,
    rerank_client: RerankClient,
    *,
    request_id: str,
    payload: RetrievalRequest,
) -> RetrievalResponse:
    """Run standard hybrid retrieval over Qdrant and PostgreSQL."""

    started = perf_counter()
    stages: dict[str, int] = {}
    stage_started = perf_counter()
    query_vectors = await embedding_client.embed_texts([payload.query])
    stages["embedding_ms"] = elapsed_ms(stage_started)
    dense_vector = query_vectors[0]

    knowledge_bases = await load_knowledge_bases(session, payload.kb_ids)
    query_filter = build_qdrant_filter(payload.filters)
    candidate_limit = payload.top_k * candidate_multiplier(payload.filters)

    dense_candidates: list[Candidate] = []
    sparse_candidates: list[Candidate] = []
    stage_started = perf_counter()
    for knowledge_base in knowledge_bases:
        dense_points = await qdrant_client.query_dense(
            knowledge_base.qdrant_collection,
            dense_vector,
            query_filter,
            candidate_limit,
        )
        dense_candidates.extend(points_to_candidates(dense_points))
    stages["vector_search_ms"] = elapsed_ms(stage_started)

    stage_started = perf_counter()
    sparse_query = sparse_vector(payload.query)
    for knowledge_base in knowledge_bases:
        sparse_points = await qdrant_client.query_sparse(
            knowledge_base.qdrant_collection,
            sparse_query,
            query_filter,
            candidate_limit,
        )
        sparse_candidates.extend(points_to_candidates(sparse_points))
    stages["sparse_search_ms"] = elapsed_ms(stage_started)

    fused = rrf_fuse([dense_candidates, sparse_candidates])
    if payload.options.score_threshold is not None:
        fused = [
            candidate
            for candidate in fused
            if candidate.score >= payload.options.score_threshold
        ]
    fused = fused[:candidate_limit]

    stage_started = perf_counter()
    chunks = await load_chunks(session, [candidate.chunk_id for candidate in fused])
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    documents = await load_documents(session, [chunk.document_id for chunk in chunks])
    document_by_id = {document.id: document for document in documents}
    stages["fetch_content_ms"] = elapsed_ms(stage_started)

    ordered_chunks = [
        chunk_by_id[candidate.chunk_id]
        for candidate in fused
        if candidate.chunk_id in chunk_by_id
    ]
    ordered_chunks = filter_chunks_by_governance(
        ordered_chunks,
        document_by_id,
        payload.filters,
    )
    base_scores = {
        candidate.chunk_id: candidate.score
        for candidate in fused
        if candidate.chunk_id in {chunk.id for chunk in ordered_chunks}
    }

    rerank_scores: list[float] | None = None
    stage_started = perf_counter()
    if payload.options.enable_rerank and ordered_chunks:
        rerank_scores = await rerank_client.rerank(
            payload.query,
            [chunk.content for chunk in ordered_chunks],
        )
    stages["rerank_ms"] = elapsed_ms(stage_started)

    if rerank_scores is not None:
        scored_chunks: list[tuple[Chunk, float | None]] = sorted(
            zip(ordered_chunks, rerank_scores, strict=True),
            key=lambda item: item[1] or 0.0,
            reverse=True,
        )
    else:
        scored_chunks = [
            (chunk, None)
            for chunk in sorted(
                ordered_chunks,
                key=lambda item: base_scores[item.id],
                reverse=True,
            )
        ]

    scored_chunks = rank_scored_chunks_by_authority(scored_chunks, base_scores, document_by_id)

    results = await build_results(
        session,
        scored_chunks[: payload.top_k],
        base_scores,
        document_by_id,
        include_metadata=payload.options.include_metadata,
        include_parent_context=payload.options.include_parent_context,
    )
    total_latency_ms = elapsed_ms(started)

    await write_retrieval_log(
        session,
        request_id=request_id,
        payload=payload,
        results=results,
        rerank_scores=rerank_scores,
        total_latency_ms=total_latency_ms,
        stages=stages,
    )

    return RetrievalResponse(
        request_id=request_id,
        results=results,
        stats=RetrievalStats(
            total_latency_ms=total_latency_ms,
            stages=stages,
            total_candidates=len(dense_candidates) + len(sparse_candidates),
            after_fusion=len(fused),
            after_rerank=len(results),
        ),
    )


def elapsed_ms(started: float) -> int:
    """Return elapsed milliseconds from a perf counter start."""

    return round((perf_counter() - started) * 1000)


async def load_knowledge_bases(
    session: AsyncSession,
    kb_ids: list[UUID],
) -> list[KnowledgeBase]:
    """Load active knowledge bases for retrieval."""

    result = await session.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id.in_(kb_ids),
            KnowledgeBase.status == "active",
        )
    )
    knowledge_bases = list(result.scalars().all())
    found_ids = {knowledge_base.id for knowledge_base in knowledge_bases}
    missing = set(kb_ids) - found_ids
    if missing:
        raise ValueError("One or more knowledge bases were not found")
    return knowledge_bases


def build_qdrant_filter(filters: dict[str, object]) -> models.Filter:
    """Build a Qdrant filter from stable chunk-level public filters."""

    conditions: list[models.Condition] = []
    chunk_type = filters.get("chunk_type")
    if isinstance(chunk_type, str):
        conditions.append(
            models.FieldCondition(
                key="chunk_type",
                match=models.MatchValue(value=chunk_type),
            )
        )
    tags = filters.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str):
                conditions.append(
                    models.FieldCondition(
                        key="tags",
                        match=models.MatchValue(value=tag),
                    )
                )
    return models.Filter(must=conditions)


def candidate_multiplier(filters: dict[str, object]) -> int:
    """Return a wider candidate window when SQL-level governance filtering applies."""

    if filters.get("include_unpublished") is True and not has_governance_filters(filters):
        return 5
    return 20


def has_governance_filters(filters: dict[str, object]) -> bool:
    """Return whether caller requested explicit governance filtering."""

    return any(
        key in filters
        for key in (
            "review_status",
            "governance_source_type",
            "authority_level",
            "max_authority_level",
        )
    )


def governance_review_status_filter(filters: dict[str, object]) -> str | None:
    """Return the effective review status filter, defaulting to published only."""

    if filters.get("include_unpublished") is True:
        return None
    value = filters.get("review_status", DEFAULT_REVIEW_STATUS)
    if isinstance(value, str) and value:
        return value
    return DEFAULT_REVIEW_STATUS


def filter_chunks_by_governance(
    chunks: list[Chunk],
    document_by_id: dict[UUID, Document],
    filters: dict[str, object],
) -> list[Chunk]:
    """Apply the same governance rules after SQL hydration as a safety net."""

    return [
        chunk
        for chunk in chunks
        if document_matches_governance_filters(document_by_id[chunk.document_id], filters)
    ]


def document_matches_governance_filters(document: Document, filters: dict[str, object]) -> bool:
    """Return whether a hydrated document is visible under governance filters."""

    review_status = governance_review_status_filter(filters)
    if review_status is not None and document.review_status != review_status:
        return False

    governance_source_type = filters.get("governance_source_type")
    if (
        isinstance(governance_source_type, str)
        and document.governance_source_type != governance_source_type
    ):
        return False

    authority_level = filters.get("authority_level")
    if isinstance(authority_level, int) and document.authority_level != authority_level:
        return False

    max_authority_level = filters.get("max_authority_level")
    if isinstance(max_authority_level, int) and document.authority_level > max_authority_level:
        return False

    return True


def rank_scored_chunks_by_authority(
    scored_chunks: list[tuple[Chunk, float | None]],
    base_scores: dict[UUID, float],
    document_by_id: dict[UUID, Document],
) -> list[tuple[Chunk, float | None]]:
    """Prefer higher-authority sources before relevance tie-breaking."""

    return sorted(
        scored_chunks,
        key=lambda item: (
            authority_weight(document_by_id[item[0].document_id].authority_level),
            item[1] if item[1] is not None else base_scores.get(item[0].id, 0.0),
        ),
        reverse=True,
    )


def authority_weight(authority_level: int) -> int:
    """Return a descending weight where level 1 is most authoritative."""

    return max(1, 6 - authority_level)


def points_to_candidates(points: list[models.ScoredPoint]) -> list[Candidate]:
    """Convert Qdrant points to chunk candidates."""

    candidates: list[Candidate] = []
    for point in points:
        payload = point.payload or {}
        chunk_id = payload.get("chunk_id")
        if isinstance(chunk_id, str):
            candidates.append(Candidate(chunk_id=UUID(chunk_id), score=float(point.score)))
    return candidates


def rrf_fuse(rankings: list[list[Candidate]], k: int = RRF_K) -> list[Candidate]:
    """Fuse multiple rankings with Reciprocal Rank Fusion."""

    scores: defaultdict[UUID, float] = defaultdict(float)
    for ranking in rankings:
        seen: set[UUID] = set()
        for rank, candidate in enumerate(ranking, start=1):
            if candidate.chunk_id in seen:
                continue
            scores[candidate.chunk_id] += 1 / (k + rank)
            seen.add(candidate.chunk_id)

    return [
        Candidate(chunk_id=chunk_id, score=score)
        for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


async def load_chunks(session: AsyncSession, chunk_ids: list[UUID]) -> list[Chunk]:
    """Load chunks by IDs."""

    if not chunk_ids:
        return []
    result = await session.execute(select(Chunk).where(Chunk.id.in_(chunk_ids)))
    return list(result.scalars().all())


async def load_documents(
    session: AsyncSession,
    document_ids: list[UUID],
) -> list[Document]:
    """Load documents by IDs."""

    if not document_ids:
        return []
    result = await session.execute(select(Document).where(Document.id.in_(document_ids)))
    return list(result.scalars().all())


async def build_results(
    session: AsyncSession,
    scored_chunks: list[tuple[Chunk, float | None]],
    base_scores: dict[UUID, float],
    document_by_id: dict[UUID, Document],
    *,
    include_metadata: bool,
    include_parent_context: bool,
) -> list[RetrievalResult]:
    """Build public retrieval results."""

    parent_ids = [
        chunk.parent_chunk_id
        for chunk, _ in scored_chunks
        if include_parent_context and chunk.parent_chunk_id is not None
    ]
    parent_by_id: dict[UUID, Chunk] = {}
    if parent_ids:
        result = await session.execute(select(Chunk).where(Chunk.id.in_(parent_ids)))
        parent_by_id = {chunk.id: chunk for chunk in result.scalars().all()}

    asset_by_key = await load_referenced_assets(session, [chunk for chunk, _ in scored_chunks])

    results: list[RetrievalResult] = []
    for chunk, rerank_score in scored_chunks:
        document = document_by_id[chunk.document_id]
        parent_chunk = None
        if include_parent_context and chunk.parent_chunk_id is not None:
            parent = parent_by_id.get(chunk.parent_chunk_id)
            if parent is not None:
                parent_chunk = ParentChunkContext(id=parent.id, content=parent.content)

        assets = [
            retrieval_asset_ref(asset)
            for key in referenced_asset_keys(chunk.content)
            if (asset := asset_by_key.get(key)) is not None
        ]

        results.append(
            RetrievalResult(
                chunk_id=chunk.id,
                content=chunk.content,
                score=base_scores[chunk.id],
                rerank_score=rerank_score,
                document=RetrievalDocument(
                    id=document.id,
                    name=document.name,
                    metadata=document.metadata_ if include_metadata else {},
                    governance_source_type=document.governance_source_type,
                    authority_level=document.authority_level,
                    review_status=document.review_status,
                    version=document.current_version,
                ),
                kb_id=chunk.kb_id,
                chunk_type=chunk.chunk_type,
                page_num=chunk.page_num,
                bbox=chunk.bbox,
                metadata=chunk.metadata_ if include_metadata else {},
                assets=assets,
                parent_chunk=parent_chunk,
            )
        )
    return results


async def load_referenced_assets(
    session: AsyncSession,
    chunks: list[Chunk],
) -> dict[tuple[UUID, UUID], DocumentAsset]:
    """Load assets explicitly referenced by retrieved chunk content."""

    keys: list[tuple[UUID, UUID]] = []
    seen: set[tuple[UUID, UUID]] = set()
    for chunk in chunks:
        for key in referenced_asset_keys(chunk.content):
            if key in seen:
                continue
            keys.append(key)
            seen.add(key)

    if not keys:
        return {}

    asset_ids = [asset_id for _, asset_id in keys]
    result = await session.execute(select(DocumentAsset).where(DocumentAsset.id.in_(asset_ids)))
    assets = list(result.scalars().all())
    return {
        (asset.document_id, asset.id): asset
        for asset in assets
        if (asset.document_id, asset.id) in seen
    }


def referenced_asset_keys(content: str) -> list[tuple[UUID, UUID]]:
    """Return stable document/asset IDs referenced by BYOB asset URLs in content."""

    keys: list[tuple[UUID, UUID]] = []
    seen: set[tuple[UUID, UUID]] = set()
    for match in ASSET_API_PATH_RE.finditer(content):
        key = (UUID(match.group("document_id")), UUID(match.group("asset_id")))
        if key in seen:
            continue
        keys.append(key)
        seen.add(key)
    return keys


def retrieval_asset_ref(asset: DocumentAsset) -> RetrievalAssetRef:
    """Build a public retrieval asset reference from a persisted document asset."""

    return RetrievalAssetRef(
        id=asset.id,
        document_id=asset.document_id,
        kb_id=asset.kb_id,
        asset_type=asset.asset_type,
        source_path=asset.source_path,
        url=asset_api_url(asset.document_id, asset.id),
        content_type=asset.content_type,
        file_size=asset.file_size,
        metadata=asset.metadata_,
    )


def asset_api_url(document_id: UUID, asset_id: UUID) -> str:
    """Return the backend-controlled URL for a parsed document asset."""

    return f"/api/v1/documents/{document_id}/assets/{asset_id}"


async def write_retrieval_log(
    session: AsyncSession,
    *,
    request_id: str,
    payload: RetrievalRequest,
    results: list[RetrievalResult],
    rerank_scores: list[float] | None,
    total_latency_ms: int,
    stages: dict[str, int],
) -> None:
    """Persist an audit log row for retrieval."""

    try:
        log_request_id = UUID(request_id)
    except ValueError:
        log_request_id = uuid4()

    session.add(
        RetrievalLog(
            request_id=log_request_id,
            kb_ids=payload.kb_ids,
            query=payload.query,
            retrieved_chunk_ids=[result.chunk_id for result in results],
            rerank_scores=rerank_scores,
            total_latency_ms=total_latency_ms,
            stage_latencies=stages,
        )
    )
    await session.commit()
