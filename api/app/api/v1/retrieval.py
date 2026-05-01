from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.deps import get_db_session
from api.app.models.retrieval_log import RetrievalLog
from api.app.schemas.retrieval import (
    AdvancedRetrievalRequest,
    AdvancedRetrievalResponse,
    EmbedRequest,
    EmbedResponse,
    FeedbackRequest,
    FeedbackResponse,
    MultiSearchItem,
    MultiSearchRequest,
    MultiSearchResponse,
    RerankRequest,
    RerankResponse,
    RerankResult,
    RetrievalRequest,
    RetrievalResponse,
)
from api.app.services.query_enhancer import enhance_query
from api.app.services.retrieval_service import search

router = APIRouter(prefix="/retrieval", tags=["retrieval"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/search", response_model=RetrievalResponse)
async def search_endpoint(
    payload: RetrievalRequest,
    request: Request,
    session: DbSession,
) -> RetrievalResponse:
    """Run standard Qdrant dense+sparse hybrid retrieval."""

    return await run_search(payload, request, session)


@router.post("/search/advanced", response_model=AdvancedRetrievalResponse)
async def advanced_search_endpoint(
    payload: AdvancedRetrievalRequest,
    request: Request,
    session: DbSession,
) -> AdvancedRetrievalResponse:
    """Run enhanced retrieval with query rewrite, HyDE, and decomposition."""

    enhancement_info = enhance_query(payload.query, payload.enhancements)
    queries = [enhancement_info.rewritten_query or payload.query]
    if enhancement_info.hyde_doc is not None:
        queries.append(enhancement_info.hyde_doc)
    queries.extend(enhancement_info.sub_queries)

    responses: list[RetrievalResponse] = []
    for query in dedupe_queries(queries):
        search_payload = RetrievalRequest(
            kb_ids=payload.kb_ids,
            query=query,
            top_k=payload.top_k,
            filters=payload.filters,
            options=payload.options,
        )
        responses.append(await run_search(search_payload, request, session, use_cache=False))

    merged = merge_responses(request.state.request_id, responses, payload.top_k)
    return AdvancedRetrievalResponse(
        **merged.model_dump(),
        enhancement_info=enhancement_info,
    )


@router.post("/multi-search", response_model=MultiSearchResponse)
async def multi_search_endpoint(
    payload: MultiSearchRequest,
    request: Request,
    session: DbSession,
) -> MultiSearchResponse:
    """Run standard retrieval for multiple queries."""

    data: list[MultiSearchItem] = []
    for query in payload.queries:
        search_payload = RetrievalRequest(
            kb_ids=payload.kb_ids,
            query=query,
            top_k=payload.top_k,
            filters=payload.filters,
            options=payload.options,
        )
        data.append(
            MultiSearchItem(
                query=query,
                response=await run_search(search_payload, request, session),
            )
        )
    return MultiSearchResponse(request_id=request.state.request_id, data=data)


@router.post("/rerank", response_model=RerankResponse)
async def rerank_endpoint(payload: RerankRequest, request: Request) -> RerankResponse:
    """Rerank a caller-provided candidate set."""

    scores = await request.app.state.rerank_client.rerank(payload.query, payload.documents)
    if scores is None:
        scores = [0.0 for _ in payload.documents]
    ranked = sorted(
        [
            RerankResult(index=index, document=document, score=scores[index])
            for index, document in enumerate(payload.documents)
        ],
        key=lambda item: item.score,
        reverse=True,
    )
    return RerankResponse(request_id=request.state.request_id, results=ranked)


@router.post("/embed", response_model=EmbedResponse)
async def embed_endpoint(payload: EmbedRequest, request: Request) -> EmbedResponse:
    """Embed caller-provided texts with the configured embedding service."""

    embeddings = await request.app.state.embedding_client.embed_texts(payload.input)
    return EmbedResponse(
        request_id=request.state.request_id,
        model=request.app.state.embedding_client.model,
        data=embeddings,
    )


@router.post("/{request_id}/feedback", response_model=FeedbackResponse)
async def feedback_endpoint(
    request_id: UUID,
    payload: FeedbackRequest,
    request: Request,
    session: DbSession,
) -> FeedbackResponse:
    """Attach feedback to a retrieval log row."""

    result = await session.execute(
        select(RetrievalLog).where(RetrievalLog.request_id == request_id)
    )
    retrieval_log = result.scalar_one_or_none()
    if retrieval_log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Retrieval log not found")

    retrieval_log.feedback = payload.feedback
    retrieval_log.feedback_detail = payload.detail
    await session.commit()
    return FeedbackResponse(request_id=request.state.request_id, updated=True)


async def run_search(
    payload: RetrievalRequest,
    request: Request,
    session: AsyncSession,
    *,
    use_cache: bool = True,
) -> RetrievalResponse:
    """Run retrieval with optional cache and logging."""

    cache_key = build_cache_key(payload)
    cached = await request.app.state.redis_client.get_text(cache_key) if use_cache else None
    if use_cache and cached is not None:
        response = RetrievalResponse.model_validate_json(cached)
        response.request_id = request.state.request_id
        response.stats.cache_hit = True
        await write_cache_hit_log(
            session,
            request_id=request.state.request_id,
            payload=payload,
            response=response,
        )
        return response

    try:
        response = await search(
            session,
            request.app.state.settings,
            request.app.state.qdrant_client,
            request.app.state.embedding_client,
            request.app.state.rerank_client,
            request_id=request.state.request_id,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if use_cache:
        await request.app.state.redis_client.set_text(
            cache_key,
            response.model_dump_json(),
            request.app.state.settings.retrieval_cache_ttl_seconds,
        )
    return response


def build_cache_key(payload: RetrievalRequest) -> str:
    """Return a stable cache key for a retrieval request."""

    digest = sha256(payload.model_dump_json().encode("utf-8")).hexdigest()
    return f"retrieval:{digest}"


def dedupe_queries(queries: list[str]) -> list[str]:
    """Return non-empty unique queries while preserving order."""

    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        normalized = query.strip()
        if not normalized or normalized in seen:
            continue
        unique.append(normalized)
        seen.add(normalized)
    return unique


def merge_responses(
    request_id: str,
    responses: list[RetrievalResponse],
    top_k: int,
) -> RetrievalResponse:
    """Merge multiple retrieval responses by best score per chunk."""

    from api.app.schemas.retrieval import RetrievalResult, RetrievalStats

    best_results: dict[UUID, RetrievalResult] = {}
    for response in responses:
        for result in response.results:
            existing = best_results.get(result.chunk_id)
            if existing is None or result.score > existing.score:
                best_results[result.chunk_id] = result

    results = sorted(best_results.values(), key=lambda item: item.score, reverse=True)[:top_k]
    total_latency = sum(response.stats.total_latency_ms for response in responses)
    stages: dict[str, int] = {}
    for response in responses:
        for name, latency in response.stats.stages.items():
            stages[name] = stages.get(name, 0) + latency

    return RetrievalResponse(
        request_id=request_id,
        results=results,
        stats=RetrievalStats(
            total_latency_ms=total_latency,
            stages=stages,
            total_candidates=sum(response.stats.total_candidates for response in responses),
            after_fusion=sum(response.stats.after_fusion for response in responses),
            after_rerank=len(results),
        ),
    )


async def write_cache_hit_log(
    session: AsyncSession,
    *,
    request_id: str,
    payload: RetrievalRequest,
    response: RetrievalResponse,
) -> None:
    """Persist retrieval audit logs even when serving cached results."""

    try:
        log_request_id = UUID(request_id)
    except ValueError:
        log_request_id = uuid4()

    session.add(
        RetrievalLog(
            request_id=log_request_id,
            kb_ids=payload.kb_ids,
            query=payload.query,
            retrieved_chunk_ids=[result.chunk_id for result in response.results],
            rerank_scores=[result.rerank_score or 0.0 for result in response.results],
            total_latency_ms=0,
            stage_latencies={"cache_hit": True},
        )
    )
    await session.commit()
