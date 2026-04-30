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
from api.app.models.knowledge_base import KnowledgeBase
from api.app.models.retrieval_log import RetrievalLog
from api.app.schemas.retrieval import (
    ParentChunkContext,
    RetrievalDocument,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    RetrievalStats,
)
from api.app.services.ingestion_service import sparse_vector

RRF_K = 60


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
    tenant_id: UUID,
    api_key_id: UUID | None,
    payload: RetrievalRequest,
) -> RetrievalResponse:
    """Run standard hybrid retrieval over Qdrant and PostgreSQL."""

    started = perf_counter()
    stages: dict[str, int] = {}
    stage_started = perf_counter()
    query_vectors = await embedding_client.embed_texts([payload.query])
    stages["embedding_ms"] = elapsed_ms(stage_started)
    dense_vector = query_vectors[0]

    knowledge_bases = await load_knowledge_bases(session, tenant_id, payload.kb_ids)
    query_filter = build_qdrant_filter(tenant_id, payload.filters)

    dense_candidates: list[Candidate] = []
    sparse_candidates: list[Candidate] = []
    stage_started = perf_counter()
    for knowledge_base in knowledge_bases:
        dense_points = await qdrant_client.query_dense(
            knowledge_base.qdrant_collection,
            dense_vector,
            query_filter,
            payload.top_k * 5,
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
            payload.top_k * 5,
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
    fused = fused[: payload.top_k * 5]

    stage_started = perf_counter()
    chunks = await load_chunks(session, tenant_id, [candidate.chunk_id for candidate in fused])
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    documents = await load_documents(session, tenant_id, [chunk.document_id for chunk in chunks])
    document_by_id = {document.id: document for document in documents}
    stages["fetch_content_ms"] = elapsed_ms(stage_started)

    ordered_chunks = [
        chunk_by_id[candidate.chunk_id]
        for candidate in fused
        if candidate.chunk_id in chunk_by_id
    ]
    base_scores = {
        candidate.chunk_id: candidate.score
        for candidate in fused
        if candidate.chunk_id in chunk_by_id
    }

    rerank_scores: list[float] | None = None
    stage_started = perf_counter()
    if payload.options.enable_rerank:
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
        tenant_id=tenant_id,
        api_key_id=api_key_id,
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
    tenant_id: UUID,
    kb_ids: list[UUID],
) -> list[KnowledgeBase]:
    """Load tenant-owned knowledge bases for retrieval."""

    result = await session.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.tenant_id == tenant_id,
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


def build_qdrant_filter(tenant_id: UUID, filters: dict[str, object]) -> models.Filter:
    """Build a Qdrant filter from tenant context and allowed filters."""

    conditions: list[models.Condition] = [
        models.FieldCondition(key="tenant_id", match=models.MatchValue(value=str(tenant_id)))
    ]
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


async def load_chunks(session: AsyncSession, tenant_id: UUID, chunk_ids: list[UUID]) -> list[Chunk]:
    """Load chunks by IDs under tenant isolation."""

    if not chunk_ids:
        return []
    result = await session.execute(
        select(Chunk).where(Chunk.tenant_id == tenant_id, Chunk.id.in_(chunk_ids))
    )
    return list(result.scalars().all())


async def load_documents(
    session: AsyncSession,
    tenant_id: UUID,
    document_ids: list[UUID],
) -> list[Document]:
    """Load documents by IDs under tenant isolation."""

    if not document_ids:
        return []
    result = await session.execute(
        select(Document).where(Document.tenant_id == tenant_id, Document.id.in_(document_ids))
    )
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

    results: list[RetrievalResult] = []
    for chunk, rerank_score in scored_chunks:
        document = document_by_id[chunk.document_id]
        parent_chunk = None
        if include_parent_context and chunk.parent_chunk_id is not None:
            parent = parent_by_id.get(chunk.parent_chunk_id)
            if parent is not None:
                parent_chunk = ParentChunkContext(id=parent.id, content=parent.content)

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
                ),
                kb_id=chunk.kb_id,
                chunk_type=chunk.chunk_type,
                page_num=chunk.page_num,
                bbox=chunk.bbox,
                metadata=chunk.metadata_ if include_metadata else {},
                parent_chunk=parent_chunk,
            )
        )
    return results


async def write_retrieval_log(
    session: AsyncSession,
    *,
    request_id: str,
    tenant_id: UUID,
    api_key_id: UUID | None,
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
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            kb_ids=payload.kb_ids,
            query=payload.query,
            retrieved_chunk_ids=[result.chunk_id for result in results],
            rerank_scores=rerank_scores,
            total_latency_ms=total_latency_ms,
            stage_latencies=stages,
        )
    )
    await session.commit()
