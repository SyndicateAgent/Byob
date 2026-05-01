from collections import Counter
from hashlib import sha256
from re import findall
from uuid import UUID, uuid4

import httpx
from qdrant_client.http import models
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.app.config import Settings
from api.app.core.embedding import EmbeddingClient
from api.app.core.minio_client import MinioClient
from api.app.core.qdrant_client import QdrantStoreClient
from api.app.db.session import create_engine, create_session_factory
from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.knowledge_base import KnowledgeBase
from api.app.services.document_service import refresh_knowledge_base_counts
from workers.chunkers.semantic_chunker import chunk_text
from workers.parsers.registry import parse_document_bytes

SPARSE_INDEX_MODULUS = 1_000_003


async def process_document_by_id(settings: Settings, document_id: UUID) -> None:
    """Run parse, chunk, embed, persist, and vector upsert for one document."""

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    minio_client = MinioClient(
        str(settings.minio_endpoint_url),
        settings.dependency_health_timeout_seconds,
        settings,
    )
    qdrant_client = QdrantStoreClient(
        str(settings.qdrant_url),
        settings.dependency_health_timeout_seconds,
    )
    embedding_client = EmbeddingClient(settings)

    try:
        async with session_factory() as session:
            result = await session.execute(select(Document).where(Document.id == document_id))
            document = result.scalar_one_or_none()
            if document is None:
                return
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == document.kb_id)
            )
            knowledge_base = kb_result.scalar_one()
            await mark_document_processing(session_factory, document.id)

        content = await load_document_content(document, minio_client)
        parsed = parse_document_bytes(content, document.file_type)
        parsed_chunks = chunk_text(
            parsed.text,
            chunk_size=knowledge_base.chunk_size,
            chunk_overlap=knowledge_base.chunk_overlap,
        )
        embeddings = await embedding_client.embed_texts([chunk.content for chunk in parsed_chunks])

        async with session_factory() as session:
            await session.execute(delete(Chunk).where(Chunk.document_id == document.id))
            chunks: list[Chunk] = []
            points: list[models.PointStruct] = []
            for index, parsed_chunk in enumerate(parsed_chunks):
                point_id = uuid4()
                chunk = Chunk(
                    id=point_id,
                    document_id=document.id,
                    kb_id=document.kb_id,
                    chunk_index=index,
                    content=parsed_chunk.content,
                    content_hash=sha256(parsed_chunk.content.encode("utf-8")).hexdigest(),
                    chunk_type=parsed_chunk.chunk_type,
                    qdrant_point_id=point_id,
                    metadata_={**parsed.metadata, **parsed_chunk.metadata},
                )
                chunks.append(chunk)
                points.append(
                    build_qdrant_point(
                        chunk,
                        dense_vector=embeddings[index],
                        created_at=document.created_at.isoformat(),
                    )
                )

            session.add_all(chunks)
            document_result = await session.execute(
                select(Document).where(Document.id == document.id)
            )
            current_document = document_result.scalar_one()
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == document.kb_id)
            )
            current_kb = kb_result.scalar_one()
            current_document.status = "completed"
            current_document.error_message = None
            current_document.chunk_count = len(chunks)
            await refresh_knowledge_base_counts(session, current_kb.id)
            await session.commit()

        await qdrant_client.ensure_hybrid_collection(
            knowledge_base.qdrant_collection,
            knowledge_base.embedding_dim,
        )
        await qdrant_client.upsert_chunks(knowledge_base.qdrant_collection, points)
    except Exception as exc:
        await mark_document_failed(session_factory, document_id, str(exc))
        raise
    finally:
        await embedding_client.close()
        await qdrant_client.close()
        await minio_client.close()
        await engine.dispose()


async def mark_document_processing(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
) -> None:
    """Set document status to processing."""

    async with session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if document is None:
            return
        document.status = "processing"
        document.error_message = None
        await session.commit()


async def mark_document_failed(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
    error_message: str,
) -> None:
    """Persist ingestion failure details for polling clients."""

    async with session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if document is None:
            return
        document.status = "failed"
        document.error_message = error_message[:2000]
        await session.commit()


async def load_document_content(document: Document, minio_client: MinioClient) -> bytes:
    """Load source content for upload, text, or URL documents."""

    if document.source_type == "text":
        inline_content = document.metadata_.get("inline_content")
        if not isinstance(inline_content, str):
            raise ValueError("Text document is missing inline content")
        return inline_content.encode("utf-8")

    if document.source_type == "url":
        if document.source_url is None:
            raise ValueError("URL document is missing source_url")
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            response = await client.get(document.source_url)
            response.raise_for_status()
            return response.content

    if document.minio_path is None:
        raise ValueError("Uploaded document is missing MinIO path")
    return await minio_client.get_object(document.minio_path)


def build_qdrant_point(
    chunk: Chunk,
    *,
    dense_vector: list[float],
    created_at: str,
) -> models.PointStruct:
    """Build a Qdrant point with dense and sparse vectors and no source content."""

    return models.PointStruct(
        id=str(chunk.qdrant_point_id or chunk.id),
        vector={
            "dense": dense_vector,
            "sparse": sparse_vector(chunk.content),
        },
        payload={
            "chunk_id": str(chunk.id),
            "doc_id": str(chunk.document_id),
            "chunk_type": chunk.chunk_type,
            "tags": chunk.metadata_.get("tags", []),
            "created_at": created_at,
        },
    )


def sparse_vector(text: str) -> models.SparseVector:
    """Create a deterministic sparse keyword vector from token counts."""

    tokens = findall(r"[\w]+", text.lower())
    counts = Counter(tokens)
    indices: list[int] = []
    values: list[float] = []
    for token, count in counts.items():
        index = int(sha256(token.encode("utf-8")).hexdigest(), 16) % SPARSE_INDEX_MODULUS
        indices.append(index)
        values.append(float(count))
    return models.SparseVector(indices=indices, values=values)
