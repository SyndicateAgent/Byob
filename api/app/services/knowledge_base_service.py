from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.knowledge_base import KnowledgeBase
from api.app.schemas.knowledge_base import KnowledgeBaseCreateRequest, KnowledgeBaseUpdateRequest


def qdrant_collection_name(kb_id: UUID) -> str:
    """Return the deterministic Qdrant collection name for a knowledge base."""

    return f"kb_{str(kb_id).replace('-', '_')}"


async def create_knowledge_base(
    session: AsyncSession,
    payload: KnowledgeBaseCreateRequest,
) -> KnowledgeBase:
    """Create a knowledge base record for this instance."""

    knowledge_base = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        embedding_model=payload.embedding_model,
        embedding_dim=payload.embedding_dim,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        retrieval_config=payload.retrieval_config,
        qdrant_collection="pending",
    )
    session.add(knowledge_base)
    await session.flush()
    knowledge_base.qdrant_collection = qdrant_collection_name(knowledge_base.id)
    await session.commit()
    await session.refresh(knowledge_base)
    return knowledge_base


async def list_knowledge_bases(session: AsyncSession) -> list[KnowledgeBase]:
    """Return knowledge bases in this instance."""

    result = await session.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()))
    return list(result.scalars().all())


async def get_knowledge_base(
    session: AsyncSession,
    kb_id: UUID,
) -> KnowledgeBase | None:
    """Return one knowledge base if present."""

    result = await session.execute(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    return result.scalar_one_or_none()


async def update_knowledge_base(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
    payload: KnowledgeBaseUpdateRequest,
) -> KnowledgeBase:
    """Apply mutable knowledge base updates."""

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(knowledge_base, field, value)

    await session.commit()
    await session.refresh(knowledge_base)
    return knowledge_base


async def delete_knowledge_base(session: AsyncSession, knowledge_base: KnowledgeBase) -> None:
    """Delete a knowledge base and cascading documents/chunks."""

    await session.delete(knowledge_base)
    await session.commit()
