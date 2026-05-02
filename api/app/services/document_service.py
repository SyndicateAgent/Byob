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
from api.app.models.document_audit_log import DocumentAuditLog
from api.app.models.document_version import DocumentVersion
from api.app.models.knowledge_base import KnowledgeBase
from api.app.schemas.document import (
    DocumentContentUpdateRequest,
    DocumentGovernanceInput,
    DocumentGovernanceUpdateRequest,
    DocumentTextCreateRequest,
    DocumentUrlCreateRequest,
)

DuplicateDocumentReason = Literal["duplicate_name", "duplicate_file_hash"]


def knowledge_base_object_prefix(kb_id: UUID) -> str:
    """Return the MinIO prefix containing all objects for one knowledge base."""

    return f"knowledge_bases/{kb_id}/"


def document_generated_object_prefix(document: Document) -> str:
    """Return the MinIO prefix for parsed snapshots and extracted assets."""

    return f"knowledge_bases/{document.kb_id}/documents/{document.id}/"


def document_source_object_key(document: Document) -> str | None:
    """Return the original uploaded object key for a document, if any."""

    if document.source_type != "upload":
        return None
    return document.minio_path


@dataclass(frozen=True)
class DuplicateDocumentMatch:
    """Existing document that should make a new import a no-op."""

    document: Document
    reason: DuplicateDocumentReason


@dataclass(frozen=True)
class AuditActor:
    """User identity stored with version and audit records."""

    user_id: UUID | None = None
    email: str | None = None


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
    governance: DocumentGovernanceInput,
    metadata: dict[str, object] | None = None,
    actor: AuditActor | None = None,
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
        governance_source_type=governance.governance_source_type,
        authority_level=governance.authority_level,
        review_status=governance.review_status,
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
    await session.flush()
    await record_document_version(
        session,
        document,
        version_number=1,
        change_summary="Initial uploaded document",
        actor=actor,
    )
    record_document_audit_log(
        session,
        document=document,
        action="document.created",
        summary="Uploaded document created",
        before={},
        after=document_snapshot(document),
        actor=actor,
    )
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
    *,
    actor: AuditActor | None = None,
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
        governance_source_type=payload.governance_source_type,
        authority_level=payload.authority_level,
        review_status=payload.review_status,
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
    await session.flush()
    await record_document_version(
        session,
        document,
        version_number=1,
        change_summary="Initial text document",
        actor=actor,
    )
    record_document_audit_log(
        session,
        document=document,
        action="document.created",
        summary="Text document created",
        before={},
        after=document_snapshot(document),
        actor=actor,
    )
    await session.commit()
    await session.refresh(document)
    return document


async def create_url_document(
    session: AsyncSession,
    knowledge_base: KnowledgeBase,
    payload: DocumentUrlCreateRequest,
    *,
    actor: AuditActor | None = None,
) -> Document:
    """Create a document record for URL ingestion."""

    source_url = str(payload.url)
    document = Document(
        kb_id=knowledge_base.id,
        name=payload.name or source_url,
        file_type="html",
        source_type="url",
        source_url=source_url,
        governance_source_type=payload.governance_source_type,
        authority_level=payload.authority_level,
        review_status=payload.review_status,
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
    await session.flush()
    await record_document_version(
        session,
        document,
        version_number=1,
        change_summary="Initial URL document",
        actor=actor,
    )
    record_document_audit_log(
        session,
        document=document,
        action="document.created",
        summary="URL document created",
        before={},
        after=document_snapshot(document),
        actor=actor,
    )
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


async def list_document_versions(
    session: AsyncSession,
    document: Document,
) -> list[DocumentVersion]:
    """Return immutable version snapshots for one document."""

    result = await session.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.version_number.desc())
    )
    return list(result.scalars().all())


async def list_document_audit_logs(
    session: AsyncSession,
    document: Document,
) -> list[DocumentAuditLog]:
    """Return audit log entries for one document."""

    result = await session.execute(
        select(DocumentAuditLog)
        .where(DocumentAuditLog.document_id == document.id)
        .order_by(DocumentAuditLog.created_at.desc(), DocumentAuditLog.id.desc())
    )
    return list(result.scalars().all())


async def update_document_governance(
    session: AsyncSession,
    document: Document,
    payload: DocumentGovernanceUpdateRequest,
    *,
    actor: AuditActor | None = None,
) -> Document:
    """Update governance fields and persist a version plus audit record."""

    before = document_snapshot(document)
    updates = payload.model_dump(exclude_unset=True, exclude={"change_summary"})
    if not updates:
        return document

    for field_name, value in updates.items():
        setattr(document, field_name, value)

    next_version = await next_document_version_number(session, document.id)
    document.current_version = next_version
    summary = payload.change_summary or "Governance metadata updated"
    await record_document_version(
        session,
        document,
        version_number=next_version,
        change_summary=summary,
        actor=actor,
    )
    record_document_audit_log(
        session,
        document=document,
        action="document.governance_updated",
        summary=summary,
        before=before,
        after=document_snapshot(document),
        actor=actor,
    )
    await session.commit()
    await session.refresh(document)
    return document


async def update_document_content_source(
    session: AsyncSession,
    document: Document,
    payload: DocumentContentUpdateRequest,
    *,
    actor: AuditActor | None = None,
) -> Document:
    """Replace source content with edited text and queue re-indexing."""

    before = document_snapshot(document)
    encoded = payload.content.encode("utf-8")
    file_type = "md" if payload.file_type == "markdown" else payload.file_type
    metadata = {
        key: value
        for key, value in document.metadata_.items()
        if key not in {"parsed_content", "ingestion_progress"}
    }
    metadata["inline_content"] = payload.content
    metadata["content_edit"] = {
        "updated_at": datetime.now(UTC).isoformat(),
        "change_summary": payload.change_summary or "Source content updated",
        "actor_email": actor.email if actor else None,
    }

    await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
    await session.execute(delete(DocumentAsset).where(DocumentAsset.document_id == document.id))
    document.source_type = "text"
    document.source_url = None
    document.minio_path = None
    document.file_type = file_type
    document.file_size = len(encoded)
    document.file_hash = hash_content(encoded)
    document.metadata_ = metadata_with_ingestion_progress(
        metadata,
        stage="queued",
        progress=10,
        status="pending",
        detail="Queued after content edit",
        reset=True,
    )
    document.status = "pending"
    document.error_message = None
    document.chunk_count = 0

    next_version = await next_document_version_number(session, document.id)
    summary = payload.change_summary or "Source content updated"
    await record_document_version(
        session,
        document,
        version_number=next_version,
        change_summary=summary,
        actor=actor,
    )
    record_document_audit_log(
        session,
        document=document,
        action="document.content_updated",
        summary=summary,
        before=before,
        after=document_snapshot(document),
        actor=actor,
    )
    await refresh_knowledge_base_counts(session, document.kb_id)
    await session.commit()
    await session.refresh(document)
    return document


def parsed_content_metadata(document: Document) -> dict[str, object] | None:
    """Return parsed full-content metadata stored on a document, if present."""

    value = document.metadata_.get("parsed_content")
    if not isinstance(value, dict):
        return None
    path = value.get("minio_path")
    if not isinstance(path, str) or not path:
        return None
    return value


async def reset_document_for_reprocess(
    session: AsyncSession,
    document: Document,
    *,
    actor: AuditActor | None = None,
) -> Document:
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
    record_document_audit_log(
        session,
        document=document,
        action="document.reprocessed",
        summary="Document queued for reprocessing",
        before={},
        after=document_snapshot(document),
        actor=actor,
    )
    await refresh_knowledge_base_counts(session, document.kb_id)
    await session.commit()
    await session.refresh(document)
    return document


async def delete_document(
    session: AsyncSession,
    document: Document,
    *,
    actor: AuditActor | None = None,
) -> None:
    """Delete a document and its chunks."""

    kb_id = document.kb_id
    record_document_audit_log(
        session,
        document=document,
        action="document.deleted",
        summary="Document deleted",
        before=document_snapshot(document),
        after={},
        actor=actor,
    )
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


async def next_document_version_number(session: AsyncSession, document_id: UUID) -> int:
    """Return the next version number for a document."""

    current = await session.scalar(
        select(func.max(DocumentVersion.version_number)).where(
            DocumentVersion.document_id == document_id
        )
    )
    return (current or 0) + 1


async def record_document_version(
    session: AsyncSession,
    document: Document,
    *,
    version_number: int,
    change_summary: str,
    actor: AuditActor | None = None,
) -> DocumentVersion:
    """Persist an immutable snapshot of the document's current governance state."""

    document.current_version = version_number
    version = DocumentVersion(
        document_id=document.id,
        kb_id=document.kb_id,
        version_number=version_number,
        name=document.name,
        file_type=document.file_type,
        file_size=document.file_size,
        minio_path=document.minio_path,
        file_hash=document.file_hash,
        source_type=document.source_type,
        source_url=document.source_url,
        governance_source_type=document.governance_source_type,
        authority_level=document.authority_level,
        review_status=document.review_status,
        metadata_=document.metadata_,
        change_summary=change_summary,
        created_by_id=actor.user_id if actor else None,
        created_by_email=actor.email if actor else None,
    )
    session.add(version)
    return version


def record_document_audit_log(
    session: AsyncSession,
    *,
    document: Document,
    action: str,
    summary: str | None,
    before: dict[str, object],
    after: dict[str, object],
    actor: AuditActor | None = None,
) -> DocumentAuditLog:
    """Append a document audit event to the current transaction."""

    entry = DocumentAuditLog(
        document_id=document.id,
        kb_id=document.kb_id,
        actor_user_id=actor.user_id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        summary=summary,
        before=before,
        after=after,
    )
    session.add(entry)
    return entry


def document_snapshot(document: Document) -> dict[str, object]:
    """Return a JSON-safe governance snapshot for audit/version metadata."""

    return {
        "id": str(document.id),
        "kb_id": str(document.kb_id),
        "name": document.name,
        "file_type": document.file_type,
        "file_size": document.file_size,
        "minio_path": document.minio_path,
        "file_hash": document.file_hash,
        "source_type": document.source_type,
        "source_url": document.source_url,
        "governance_source_type": document.governance_source_type,
        "authority_level": document.authority_level,
        "review_status": document.review_status,
        "current_version": document.current_version,
        "status": document.status,
        "chunk_count": document.chunk_count,
    }


def document_governance_payload(document: Document) -> dict[str, object]:
    """Return governance fields that must be mirrored into Qdrant payloads."""

    return {
        "governance_source_type": document.governance_source_type,
        "authority_level": document.authority_level,
        "review_status": document.review_status,
        "document_version": document.current_version,
    }
