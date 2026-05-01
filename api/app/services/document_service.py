from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.document_asset import DocumentAsset
from api.app.models.knowledge_base import KnowledgeBase
from api.app.schemas.document import DocumentTextCreateRequest, DocumentUrlCreateRequest

DuplicateDocumentReason = Literal["duplicate_name", "duplicate_file_hash"]


@dataclass(frozen=True)
class DuplicateDocumentMatch:
    """Existing document that should make a new import a no-op."""

    document: Document
    reason: DuplicateDocumentReason


def metadata_with_ingestion_progress(
    metadata: dict[str, object] | None,
    *,
    stage: str,
    progress: int,
    status: str,
    detail: str,
    reset: bool = False,
) -> dict[str, object]:
    """Return document metadata with persisted ingestion progress."""

    now = datetime.now(UTC).isoformat()
    base_metadata = dict(metadata or {})
    existing = base_metadata.get("ingestion_progress")
    started_at = None
    if not reset and isinstance(existing, dict):
        existing_started_at = existing.get("started_at")
        if isinstance(existing_started_at, str):
            started_at = existing_started_at

    base_metadata["ingestion_progress"] = {
        "stage": stage,
        "progress": max(0, min(100, progress)),
        "status": status,
        "detail": detail,
        "started_at": started_at or now,
        "updated_at": now,
    }
    return base_metadata


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
        name=name,
        file_type=file_type,
        file_size=file_size,
        minio_path=minio_path,
        file_hash=file_hash,
        source_type="upload",
        metadata_=metadata_with_ingestion_progress(
            metadata,
            stage="queued",
            progress=10,
            status="pending",
            detail="Queued for worker",
            reset=True,
        ),
    )
    session.add(document)
    knowledge_base.document_count += 1
    await session.commit()
    await session.refresh(document)
    return document


async def find_duplicate_document(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
    *,
    name: str,
    file_hash: str | None,
) -> DuplicateDocumentMatch | None:
    """Return an existing document in the same knowledge base with the same name or hash."""

    name_match = await session.scalar(
        select(Document).where(Document.kb_id == knowledge_base.id, Document.name == name)
    )
    if name_match is not None:
        return DuplicateDocumentMatch(document=name_match, reason="duplicate_name")

    if file_hash is None:
        return None

    hash_match = await session.scalar(
        select(Document).where(Document.kb_id == knowledge_base.id, Document.file_hash == file_hash)
    )
    if hash_match is not None:
        return DuplicateDocumentMatch(document=hash_match, reason="duplicate_file_hash")

    return None


async def create_text_document(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
    payload: DocumentTextCreateRequest,
) -> Document:
    """Create a document record for direct text ingestion."""

    encoded = payload.content.encode("utf-8")
    document = Document(
        kb_id=knowledge_base.id,
        name=payload.name,
        file_type="md" if payload.file_type == "markdown" else payload.file_type,
        file_size=len(encoded),
        file_hash=hash_content(encoded),
        source_type="text",
        metadata_=metadata_with_ingestion_progress(
            {**payload.metadata, "inline_content": payload.content},
            stage="queued",
            progress=10,
            status="pending",
            detail="Queued for worker",
            reset=True,
        ),
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
        name=payload.name or source_url,
        file_type="html",
        source_type="url",
        source_url=source_url,
        metadata_=metadata_with_ingestion_progress(
            payload.metadata,
            stage="queued",
            progress=10,
            status="pending",
            detail="Queued for worker",
            reset=True,
        ),
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
        .where(Document.kb_id == knowledge_base.id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document(
    session: AsyncSession,
    document_id: UUID,
) -> Document | None:
    """Return a document if present."""

    result = await session.execute(select(Document).where(Document.id == document_id))
    return result.scalar_one_or_none()


async def list_chunks(session: AsyncSession, document: Document) -> list[Chunk]:
    """Return persisted chunks for one document."""

    result = await session.execute(
        select(Chunk)
        .where(Chunk.document_id == document.id)
        .order_by(Chunk.chunk_index.asc())
    )
    return list(result.scalars().all())


async def list_document_qdrant_point_ids(session: AsyncSession, document: Document) -> list[str]:
    """Return Qdrant point ids for chunks belonging to one document."""

    result = await session.execute(
        select(Chunk.qdrant_point_id)
        .where(Chunk.document_id == document.id, Chunk.qdrant_point_id.is_not(None))
        .order_by(Chunk.chunk_index.asc())
    )
    return [str(point_id) for point_id in result.scalars().all() if point_id is not None]


async def list_document_assets(session: AsyncSession, document: Document) -> list[DocumentAsset]:
    """Return parsed binary assets for one document."""

    result = await session.execute(
        select(DocumentAsset)
        .where(DocumentAsset.document_id == document.id)
        .order_by(DocumentAsset.asset_index.asc())
    )
    return list(result.scalars().all())


async def get_document_asset(
    session: AsyncSession,
    document: Document,
    asset_id: UUID,
) -> DocumentAsset | None:
    """Return one parsed binary asset for a document."""

    result = await session.execute(
        select(DocumentAsset).where(
            DocumentAsset.id == asset_id,
            DocumentAsset.document_id == document.id,
        )
    )
    return result.scalar_one_or_none()


def parsed_content_metadata(document: Document) -> dict[str, object] | None:
    """Return parsed full-content metadata stored on a document, if present."""

    value = document.metadata_.get("parsed_content")
    if not isinstance(value, dict):
        return None
    path = value.get("minio_path")
    if not isinstance(path, str) or not path:
        return None
    return value


async def reset_document_for_reprocess(session: AsyncSession, document: Document) -> Document:
    """Clear existing chunks and mark a document pending for reprocessing."""

    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    await session.execute(delete(DocumentAsset).where(DocumentAsset.document_id == document.id))
    metadata_without_snapshot = {
        key: value for key, value in document.metadata_.items() if key != "parsed_content"
    }
    document.metadata_ = metadata_with_ingestion_progress(
        metadata_without_snapshot,
        stage="queued",
        progress=10,
        status="pending",
        detail="Queued for worker",
        reset=True,
    )
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
