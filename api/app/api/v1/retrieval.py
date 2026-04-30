from hashlib import sha256
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.deps import get_db_session
from api.app.models.retrieval_log import RetrievalLog
from api.app.schemas.retrieval import RetrievalRequest, RetrievalResponse
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

    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing tenant context",
        )

    api_key_id = getattr(request.state, "api_key_id", None)
    cache_key = build_cache_key(UUID(str(tenant_id)), payload)
    cached = await request.app.state.redis_client.get_text(cache_key)
    if cached is not None:
        response = RetrievalResponse.model_validate_json(cached)
        response.request_id = request.state.request_id
        response.stats.cache_hit = True
        await write_cache_hit_log(
            session,
            request_id=request.state.request_id,
            tenant_id=UUID(str(tenant_id)),
            api_key_id=UUID(str(api_key_id)) if api_key_id is not None else None,
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
            tenant_id=UUID(str(tenant_id)),
            api_key_id=UUID(str(api_key_id)) if api_key_id is not None else None,
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    await request.app.state.redis_client.set_text(
        cache_key,
        response.model_dump_json(),
        request.app.state.settings.retrieval_cache_ttl_seconds,
    )
    return response


def build_cache_key(tenant_id: UUID, payload: RetrievalRequest) -> str:
    """Return a stable cache key for one tenant retrieval request."""

    digest = sha256(payload.model_dump_json().encode("utf-8")).hexdigest()
    return f"retrieval:{tenant_id}:{digest}"


async def write_cache_hit_log(
    session: AsyncSession,
    *,
    request_id: str,
    tenant_id: UUID,
    api_key_id: UUID | None,
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
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            kb_ids=payload.kb_ids,
            query=payload.query,
            retrieved_chunk_ids=[result.chunk_id for result in response.results],
            rerank_scores=[result.rerank_score or 0.0 for result in response.results],
            total_latency_ms=0,
            stage_latencies={"cache_hit": True},
        )
    )
    await session.commit()
