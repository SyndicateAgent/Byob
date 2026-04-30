from hashlib import sha256
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.knowledge_base import KnowledgeBase
from api.app.schemas.document import DocumentTextCreateRequest, DocumentUrlCreateRequest


def hash_content(content: bytes) -> str:
    """Return the SHA256 hash for uploaded document content."""

    return sha256(content).hexdigest()


async def create_file_document(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
    *,
    name: str,
    file_type: str | None,
    file_size: int,
    minio_path: str,
    file_hash: str,
    metadata: dict[str, object] | None = None,
) -> Document:
    """Create a document record for an uploaded object."""

    document = Document(
        kb_id=knowledge_base.id,
        tenant_id=knowledge_base.tenant_id,
        name=name,
        file_type=file_type,
        file_size=file_size,
        minio_path=minio_path,
        file_hash=file_hash,
        source_type="upload",
        metadata_=metadata or {},
    )
    session.add(document)
    knowledge_base.document_count += 1
    await session.commit()
    await session.refresh(document)
    return document


async def create_text_document(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
    payload: DocumentTextCreateRequest,
) -> Document:
    """Create a document record for direct text ingestion."""

    encoded = payload.content.encode("utf-8")
    document = Document(
        kb_id=knowledge_base.id,
        tenant_id=knowledge_base.tenant_id,
        name=payload.name,
        file_type="md" if payload.file_type == "markdown" else payload.file_type,
        file_size=len(encoded),
        file_hash=hash_content(encoded),
        source_type="text",
        metadata_={**payload.metadata, "inline_content": payload.content},
    )
    session.add(document)
    knowledge_base.document_count += 1
    await session.commit()
    await session.refresh(document)
    return document


async def create_url_document(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
    payload: DocumentUrlCreateRequest,
) -> Document:
    """Create a document record for URL ingestion."""

    source_url = str(payload.url)
    document = Document(
        kb_id=knowledge_base.id,
        tenant_id=knowledge_base.tenant_id,
        name=payload.name or source_url,
        file_type="html",
        source_type="url",
        source_url=source_url,
        metadata_=payload.metadata,
    )
    session.add(document)
    knowledge_base.document_count += 1
    await session.commit()
    await session.refresh(document)
    return document


async def list_documents(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
) -> list[Document]:
    """Return documents for one knowledge base."""

    result = await session.execute(
        select(Document)
        .where(
            Document.kb_id == knowledge_base.id,
            Document.tenant_id == knowledge_base.tenant_id,
        )
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document(
    session: AsyncSession,
    tenant_id: UUID,
    document_id: UUID,
) -> Document | None:
    """Return a tenant-owned document if present."""

    result = await session.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def list_chunks(session: AsyncSession, document: Document) -> list[Chunk]:
    """Return persisted chunks for one document."""

    result = await session.execute(
        select(Chunk)
        .where(
            Chunk.document_id == document.id,
            Chunk.tenant_id == document.tenant_id,
        )
        .order_by(Chunk.chunk_index.asc())
    )
    return list(result.scalars().all())


async def reset_document_for_reprocess(session: AsyncSession, document: Document) -> Document:
    """Clear existing chunks and mark a document pending for reprocessing."""

    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    document.status = "pending"
    document.error_message = None
    document.chunk_count = 0
    await refresh_knowledge_base_counts(session, document.kb_id)
    await session.commit()
    await session.refresh(document)
    return document


async def delete_document(session: AsyncSession, document: Document) -> None:
    """Delete a document and its chunks."""

    kb_id = document.kb_id
    await session.delete(document)
    await session.flush()
    await refresh_knowledge_base_counts(session, kb_id)
    await session.commit()


async def refresh_knowledge_base_counts(session: AsyncSession, kb_id: UUID) -> None:
    """Synchronize denormalized knowledge base counters with persisted rows."""

    knowledge_base = await session.scalar(select(KnowledgeBase).where(KnowledgeBase.id == kb_id))
    if knowledge_base is None:
        return

    document_count = await session.scalar(
        select(func.count()).select_from(Document).where(Document.kb_id == kb_id)
    )
    chunk_count = await session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.kb_id == kb_id)
    )
    knowledge_base.document_count = document_count or 0
    knowledge_base.chunk_count = chunk_count or 0
