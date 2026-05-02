from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.deps import get_current_user, get_db_session
from api.app.schemas.auth import CurrentUser
from api.app.schemas.knowledge_base import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseStatsResponse,
    KnowledgeBaseUpdateRequest,
)
from api.app.services.document_service import knowledge_base_object_prefix
from api.app.services.knowledge_base_service import (
    create_knowledge_base,
    delete_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    update_knowledge_base,
)

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base_endpoint(
    payload: KnowledgeBaseCreateRequest,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> KnowledgeBaseResponse:
    """Create a knowledge base and its Qdrant collection."""

    knowledge_base = await create_knowledge_base(session, payload)
    await request.app.state.qdrant_client.ensure_hybrid_collection(
        knowledge_base.qdrant_collection,
        knowledge_base.embedding_dim,
    )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases_endpoint(
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> KnowledgeBaseListResponse:
    """List knowledge bases for this instance."""

    rows = await list_knowledge_bases(session)
    return KnowledgeBaseListResponse(
        request_id=request.state.request_id,
        data=[KnowledgeBaseResponse.model_validate(row) for row in rows],
    )


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base_endpoint(
    kb_id: UUID,
    current_user: CurrentUserDep,
    session: DbSession,
) -> KnowledgeBaseResponse:
    """Return one knowledge base."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return KnowledgeBaseResponse.model_validate(knowledge_base)


@router.patch("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base_endpoint(
    kb_id: UUID,
    payload: KnowledgeBaseUpdateRequest,
    current_user: CurrentUserDep,
    session: DbSession,
) -> KnowledgeBaseResponse:
    """Update one knowledge base."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    updated = await update_knowledge_base(session, knowledge_base, payload)
    return KnowledgeBaseResponse.model_validate(updated)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base_endpoint(
    kb_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> None:
    """Delete one knowledge base."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    await request.app.state.minio_client.delete_prefix(
        knowledge_base_object_prefix(knowledge_base.id)
    )
    await request.app.state.qdrant_client.delete_collection(knowledge_base.qdrant_collection)
    await delete_knowledge_base(session, knowledge_base)
    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is not None and hasattr(redis_client, "delete_prefix"):
        await redis_client.delete_prefix("retrieval:")


@router.get("/{kb_id}/stats", response_model=KnowledgeBaseStatsResponse)
async def get_knowledge_base_stats_endpoint(
    kb_id: UUID,
    request: Request,
    current_user: CurrentUserDep,
    session: DbSession,
) -> KnowledgeBaseStatsResponse:
    """Return basic ingestion statistics for a knowledge base."""

    knowledge_base = await get_knowledge_base(session, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return KnowledgeBaseStatsResponse(
        request_id=request.state.request_id,
        kb_id=knowledge_base.id,
        document_count=knowledge_base.document_count,
        chunk_count=knowledge_base.chunk_count,
        status=knowledge_base.status,
    )
