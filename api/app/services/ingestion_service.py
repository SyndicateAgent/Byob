import mimetypes
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
from re import findall
from uuid import UUID, uuid4

import httpx
from qdrant_client.http import models
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.app.config import Settings
from api.app.core.clip_embedding import ClipEmbeddingClient, is_clip_image_content_type
from api.app.core.embedding import EmbeddingClient
from api.app.core.minio_client import MinioClient
from api.app.core.qdrant_client import QdrantStoreClient, visual_collection_name
from api.app.db.session import create_engine, create_session_factory
from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.document_asset import DocumentAsset
from api.app.models.knowledge_base import KnowledgeBase
from api.app.services.document_service import (
    document_generated_object_prefix,
    document_governance_payload,
    list_document_qdrant_point_ids,
    list_document_visual_point_ids,
    metadata_with_ingestion_progress,
    refresh_knowledge_base_counts,
)
from workers.chunkers.semantic_chunker import chunk_text, merge_structured_chunks
from workers.parsers.base import ParsedAsset, ParsedChunk, ParsedDocument
from workers.parsers.pdf_parser import PdfParserConfig
from workers.parsers.registry import parse_document_bytes

SPARSE_INDEX_MODULUS = 1_000_003
PARSING_PROGRESS = 24
ASSETS_PROGRESS = 34
CHUNKING_PROGRESS = 40
CHUNKS_READY_PROGRESS = 46
EMBEDDING_START_PROGRESS = 46
EMBEDDING_END_PROGRESS = 84
STORING_CHUNKS_PROGRESS = 86
VISUAL_EMBEDDING_START_PROGRESS = 88
VISUAL_EMBEDDING_END_PROGRESS = 91
INDEXING_START_PROGRESS = 92
INDEXING_END_PROGRESS = 99


@dataclass(frozen=True)
class StoredParsedAsset:
    """Persisted asset row paired with its source bytes for CLIP indexing."""

    row: DocumentAsset
    content: bytes


@dataclass(frozen=True)
class StoredParsedAssets:
    """Stored parsed assets plus the references needed to rewrite content."""

    replacements: dict[str, str]
    assets: list[StoredParsedAsset]


def progress_between(start: int, end: int, completed: int, total: int) -> int:
    """Return an overall progress value for a bounded stage interval."""

    if total <= 0:
        return end
    ratio = max(0.0, min(1.0, completed / total))
    return start + int((end - start) * ratio)


def stage_percent(completed: int, total: int) -> int:
    """Return percentage completion for the current stage."""

    if total <= 0:
        return 100
    return int(max(0.0, min(1.0, completed / total)) * 100)


def count_clip_image_assets(
    assets: list[StoredParsedAsset],
    clip_embedding_client: ClipEmbeddingClient,
) -> int:
    """Return assets that will actually receive CLIP image embeddings."""

    if not clip_embedding_client.enabled:
        return 0
    return sum(
        1
        for asset in assets
        if asset.row.asset_type == "image" and is_clip_image_content_type(asset.row.content_type)
    )


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
        settings.qdrant_timeout_seconds,
        health_timeout_seconds=settings.dependency_health_timeout_seconds,
        upsert_batch_size=settings.qdrant_upsert_batch_size,
    )
    embedding_client = EmbeddingClient(settings)
    clip_embedding_client = ClipEmbeddingClient(settings)
    document: Document | None = None

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
        await update_document_progress(
            session_factory,
            document.id,
            stage="parsing",
            progress=PARSING_PROGRESS,
            detail="Parsing document content",
            stage_progress=0,
        )
        parsed = parse_document_bytes(
            content,
            document.file_type,
            source_name=document.name,
            pdf_config=PdfParserConfig(
                parser=settings.pdf_parser,
                mineru_command=settings.mineru_command,
                mineru_backend=settings.mineru_backend,
                mineru_parse_method=settings.mineru_parse_method,
                mineru_lang=settings.mineru_lang,
                mineru_timeout_seconds=settings.mineru_timeout_seconds,
                mineru_api_url=(settings.mineru_api_url or None),
                mineru_formula_enable=settings.mineru_formula_enable,
                mineru_table_enable=settings.mineru_table_enable,
                mineru_fallback_to_pypdf=settings.mineru_fallback_to_pypdf,
            ),
        )
        await minio_client.delete_prefix(document_generated_object_prefix(document))
        await update_document_progress(
            session_factory,
            document.id,
            stage="assets",
            progress=ASSETS_PROGRESS,
            detail=f"Storing {len(parsed.assets)} parsed assets",
            completed=0,
            total=len(parsed.assets),
            unit="assets",
            stage_progress=0,
        )
        async with session_factory() as session:
            stale_visual_point_ids = await list_document_visual_point_ids(session, document)
        await qdrant_client.delete_points(
            visual_collection_name(knowledge_base.qdrant_collection),
            stale_visual_point_ids,
        )
        if not await document_exists(session_factory, document.id):
            return
        async with session_factory() as session:
            stored_assets = await store_parsed_assets(
                session,
                minio_client,
                document,
                parsed.assets,
            )
            await session.commit()
        if parsed.assets:
            await update_document_progress(
                session_factory,
                document.id,
                stage="assets",
                progress=CHUNKING_PROGRESS - 1,
                detail=f"Stored {len(parsed.assets)}/{len(parsed.assets)} parsed assets",
                completed=len(parsed.assets),
                total=len(parsed.assets),
                unit="assets",
                stage_progress=100,
            )

        parsed_text = rewrite_asset_references(parsed.text, stored_assets.replacements)
        parsed_metadata = {
            **parsed.metadata,
            "document_asset_count": len(parsed.assets),
        }
        if not await document_exists(session_factory, document.id):
            return
        parsed_content_metadata = await store_parsed_content(
            minio_client,
            document,
            parsed_text,
            content_type=parsed_content_type(document.file_type, parsed_text),
        )
        await update_document_progress(
            session_factory,
            document.id,
            stage="chunking",
            progress=CHUNKING_PROGRESS,
            detail="Chunking parsed content",
            stage_progress=0,
        )
        parsed_chunks = build_ingestion_chunks(
            parsed,
            parsed_text=parsed_text,
            asset_replacements=stored_assets.replacements,
            file_type=document.file_type,
            chunk_size=knowledge_base.chunk_size,
            chunk_overlap=knowledge_base.chunk_overlap,
        )
        await update_document_progress(
            session_factory,
            document.id,
            stage="chunking",
            progress=CHUNKS_READY_PROGRESS,
            detail=f"Built {len(parsed_chunks)} chunks",
            completed=len(parsed_chunks),
            total=len(parsed_chunks),
            unit="chunks",
            stage_progress=100,
        )
        await update_document_progress(
            session_factory,
            document.id,
            stage="embedding",
            progress=EMBEDDING_START_PROGRESS,
            detail=f"Embedding {len(parsed_chunks)} chunks",
            completed=0,
            total=len(parsed_chunks),
            unit="chunks",
            stage_progress=0,
        )

        async def report_embedding_progress(completed: int, total: int) -> None:
            await update_document_progress(
                session_factory,
                document.id,
                stage="embedding",
                progress=progress_between(
                    EMBEDDING_START_PROGRESS,
                    EMBEDDING_END_PROGRESS,
                    completed,
                    total,
                ),
                detail=f"Embedded {completed}/{total} chunks",
                completed=completed,
                total=total,
                unit="chunks",
                stage_progress=stage_percent(completed, total),
            )

        embeddings = await embedding_client.embed_texts(
            [chunk.content for chunk in parsed_chunks],
            progress_callback=report_embedding_progress,
        )
        await update_document_progress(
            session_factory,
            document.id,
            stage="storing_chunks",
            progress=STORING_CHUNKS_PROGRESS,
            detail=f"Persisting {len(parsed_chunks)} chunks",
            completed=len(parsed_chunks),
            total=len(parsed_chunks),
            unit="chunks",
            stage_progress=0,
        )

        async with session_factory() as session:
            document_result = await session.execute(
                select(Document).where(Document.id == document.id)
            )
            current_document = document_result.scalar_one_or_none()
            if current_document is None:
                return
            existing_point_ids = await list_document_qdrant_point_ids(session, current_document)
        await qdrant_client.delete_points(knowledge_base.qdrant_collection, existing_point_ids)

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
                    page_num=parsed_chunk.page_num,
                    bbox=parsed_chunk.bbox,
                    qdrant_point_id=point_id,
                    metadata_={**parsed_metadata, **parsed_chunk.metadata},
                )
                chunks.append(chunk)
                points.append(
                    build_qdrant_point(
                        chunk,
                        dense_vector=embeddings[index],
                        created_at=document.created_at.isoformat(),
                        document=document,
                    )
                )

            session.add_all(chunks)
            document_result = await session.execute(
                select(Document).where(Document.id == document.id)
            )
            current_document = document_result.scalar_one_or_none()
            if current_document is None:
                return
            kb_result = await session.execute(
                select(KnowledgeBase).where(KnowledgeBase.id == document.kb_id)
            )
            current_kb = kb_result.scalar_one_or_none()
            if current_kb is None:
                return
            current_document.error_message = None
            current_document.metadata_ = {
                **current_document.metadata_,
                "parsed_content": parsed_content_metadata,
            }
            current_document.chunk_count = len(chunks)
            await refresh_knowledge_base_counts(session, current_kb.id)
            await session.commit()

        visual_points: list[models.PointStruct] = []
        visual_asset_total = count_clip_image_assets(stored_assets.assets, clip_embedding_client)
        if visual_asset_total and chunks:
            await update_document_progress(
                session_factory,
                document.id,
                stage="visual_embedding",
                progress=VISUAL_EMBEDDING_START_PROGRESS,
                detail=f"Embedding {visual_asset_total} extracted images with CLIP",
                completed=0,
                total=visual_asset_total,
                unit="images",
                stage_progress=0,
            )
            visual_points = await build_visual_qdrant_points(
                stored_assets.assets,
                chunks,
                document=document,
                clip_embedding_client=clip_embedding_client,
            )
            await update_document_progress(
                session_factory,
                document.id,
                stage="visual_embedding",
                progress=VISUAL_EMBEDDING_END_PROGRESS,
                detail=f"Embedded {len(visual_points)}/{visual_asset_total} image vectors",
                completed=len(visual_points),
                total=visual_asset_total,
                unit="images",
                stage_progress=stage_percent(len(visual_points), visual_asset_total),
            )

        total_vector_points = len(points) + len(visual_points)
        await update_document_progress(
            session_factory,
            document.id,
            stage="indexing",
            progress=INDEXING_START_PROGRESS,
            detail=f"Writing {total_vector_points} vectors to Qdrant",
            completed=0,
            total=total_vector_points,
            unit="vectors",
            stage_progress=0,
        )
        await qdrant_client.ensure_hybrid_collection(
            knowledge_base.qdrant_collection,
            knowledge_base.embedding_dim,
        )

        async def report_text_indexing(completed: int, total: int) -> None:
            await update_document_progress(
                session_factory,
                document.id,
                stage="indexing",
                progress=progress_between(
                    INDEXING_START_PROGRESS,
                    INDEXING_END_PROGRESS,
                    completed,
                    total_vector_points,
                ),
                detail=f"Indexed {completed}/{total_vector_points} vectors",
                completed=completed,
                total=total_vector_points,
                unit="vectors",
                stage_progress=stage_percent(completed, total_vector_points),
            )

        await qdrant_client.upsert_chunks(
            knowledge_base.qdrant_collection,
            points,
            progress_callback=report_text_indexing,
        )
        if visual_points:
            visual_collection = visual_collection_name(knowledge_base.qdrant_collection)
            await qdrant_client.ensure_visual_collection(
                visual_collection,
                settings.clip_embedding_dimension,
            )

            async def report_visual_indexing(completed: int, total: int) -> None:
                overall_completed = len(points) + completed
                await update_document_progress(
                    session_factory,
                    document.id,
                    stage="indexing",
                    progress=progress_between(
                        INDEXING_START_PROGRESS,
                        INDEXING_END_PROGRESS,
                        overall_completed,
                        total_vector_points,
                    ),
                    detail=f"Indexed {overall_completed}/{total_vector_points} vectors",
                    completed=overall_completed,
                    total=total_vector_points,
                    unit="vectors",
                    stage_progress=stage_percent(overall_completed, total_vector_points),
                )

            await qdrant_client.upsert_chunks(
                visual_collection,
                visual_points,
                progress_callback=report_visual_indexing,
            )

        async with session_factory() as session:
            document_result = await session.execute(
                select(Document).where(Document.id == document.id)
            )
            current_document = document_result.scalar_one_or_none()
            if current_document is None:
                return
            current_document.status = "completed"
            current_document.error_message = None
            current_document.metadata_ = metadata_with_ingestion_progress(
                current_document.metadata_,
                stage="completed",
                progress=100,
                status="completed",
                detail=f"{len(chunks)} chunks indexed",
                completed=len(chunks),
                total=len(chunks),
                unit="chunks",
                stage_progress=100,
            )
            current_document.chunk_count = len(chunks)
            await refresh_knowledge_base_counts(session, current_document.kb_id)
            await session.commit()
    except IntegrityError as exc:
        if not await document_exists(session_factory, document_id):
            if document is not None:
                await minio_client.delete_prefix(document_generated_object_prefix(document))
            return
        await mark_document_failed(session_factory, document_id, str(exc))
        raise
    except Exception as exc:
        await mark_document_failed(session_factory, document_id, str(exc))
        raise
    finally:
        await embedding_client.close()
        await clip_embedding_client.close()
        await qdrant_client.close()
        await minio_client.close()
        await engine.dispose()


async def update_document_progress(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
    *,
    stage: str,
    progress: int,
    detail: str,
    completed: int | None = None,
    total: int | None = None,
    unit: str | None = None,
    stage_progress: int | None = None,
) -> None:
    """Persist an ingestion progress milestone for clients that poll documents."""

    async with session_factory() as session:
        result = await session.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        if document is None:
            return
        document.metadata_ = metadata_with_ingestion_progress(
            document.metadata_,
            stage=stage,
            progress=progress,
            status=document.status,
            detail=detail,
            completed=completed,
            total=total,
            unit=unit,
            stage_progress=stage_progress,
        )
        await session.commit()


async def store_parsed_assets(
    session: AsyncSession,
    minio_client: MinioClient,
    document: Document,
    assets: list[ParsedAsset],
) -> StoredParsedAssets:
    """Upload parsed assets to MinIO, persist metadata, and return path replacements."""

    await session.execute(delete(DocumentAsset).where(DocumentAsset.document_id == document.id))
    replacements: dict[str, str] = {}
    if not assets:
        return StoredParsedAssets(replacements=replacements, assets=[])

    rows: list[DocumentAsset] = []
    stored_assets: list[StoredParsedAsset] = []
    for index, asset in enumerate(assets):
        asset_id = uuid4()
        filename = safe_asset_filename(asset.source_path, asset.content_type, index)
        minio_path = (
            f"knowledge_bases/{document.kb_id}/documents/{document.id}"
            f"/assets/{asset_id}/{filename}"
        )
        await minio_client.put_object(minio_path, asset.content, asset.content_type)
        file_hash = sha256(asset.content).hexdigest()
        asset_url = f"/api/v1/documents/{document.id}/assets/{asset_id}"
        aliases = asset_aliases(asset)
        row = DocumentAsset(
            id=asset_id,
            document_id=document.id,
            kb_id=document.kb_id,
            asset_index=index,
            asset_type=asset.asset_type,
            source_path=asset.source_path,
            minio_path=minio_path,
            content_type=asset.content_type,
            file_size=len(asset.content),
            file_hash=file_hash,
            metadata_={**asset.metadata, "aliases": aliases},
        )
        rows.append(row)
        stored_assets.append(StoredParsedAsset(row=row, content=asset.content))
        for alias in aliases:
            replacements[alias] = asset_url

    session.add_all(rows)
    return StoredParsedAssets(replacements=replacements, assets=stored_assets)


async def build_visual_qdrant_points(
    assets: list[StoredParsedAsset],
    chunks: list[Chunk],
    *,
    document: Document,
    clip_embedding_client: ClipEmbeddingClient,
) -> list[models.PointStruct]:
    """Build CLIP image vector points linked to the chunks that reference them."""

    if not clip_embedding_client.enabled:
        return []

    image_assets = [
        asset
        for asset in assets
        if asset.row.asset_type == "image" and is_clip_image_content_type(asset.row.content_type)
    ]
    if not image_assets:
        return []

    embeddings = await clip_embedding_client.embed_images([asset.content for asset in image_assets])
    chunk_by_asset_id = chunks_by_asset_id(chunks, image_assets)
    fallback_chunk = chunks[0]
    points: list[models.PointStruct] = []
    for index, asset in enumerate(image_assets):
        chunk = chunk_by_asset_id.get(asset.row.id, fallback_chunk)
        points.append(
            build_visual_qdrant_point(
                asset.row,
                chunk,
                visual_vector=embeddings[index],
                created_at=document.created_at.isoformat(),
                document=document,
            )
        )
    return points


def chunks_by_asset_id(
    chunks: list[Chunk],
    assets: list[StoredParsedAsset],
) -> dict[UUID, Chunk]:
    """Return the first chunk that explicitly references each asset URL."""

    matches: dict[UUID, Chunk] = {}
    for asset in assets:
        url = document_asset_api_url(asset.row.document_id, asset.row.id)
        for chunk in chunks:
            if url in chunk.content:
                matches[asset.row.id] = chunk
                break
    return matches


def document_asset_api_url(document_id: UUID, asset_id: UUID) -> str:
    """Return the backend-controlled URL for an asset."""

    return f"/api/v1/documents/{document_id}/assets/{asset_id}"


def build_visual_qdrant_point(
    asset: DocumentAsset,
    chunk: Chunk,
    *,
    visual_vector: list[float],
    created_at: str,
    document: Document,
) -> models.PointStruct:
    """Build a Qdrant point for one CLIP-indexed image asset."""

    return models.PointStruct(
        id=str(asset.id),
        vector={"visual": visual_vector},
        payload={
            "asset_id": str(asset.id),
            "chunk_id": str(chunk.id),
            "doc_id": str(asset.document_id),
            "kb_id": str(asset.kb_id),
            "chunk_type": "image",
            "asset_type": asset.asset_type,
            "content_type": asset.content_type,
            "source_path": asset.source_path,
            "file_hash": asset.file_hash,
            "tags": chunk.metadata_.get("tags", []),
            "created_at": created_at,
            **document_governance_payload(document),
        },
    )


async def store_parsed_content(
    minio_client: MinioClient,
    document: Document,
    content: str,
    *,
    content_type: str,
) -> dict[str, object]:
    """Persist the full parsed content snapshot before chunking mutates shape."""

    encoded = content.encode("utf-8")
    file_hash = sha256(encoded).hexdigest()
    minio_path = f"knowledge_bases/{document.kb_id}/documents/{document.id}/parsed/content"
    await minio_client.put_object(minio_path, encoded, content_type)
    return {
        "minio_path": minio_path,
        "content_type": content_type,
        "file_size": len(encoded),
        "file_hash": file_hash,
    }


def parsed_content_type(file_type: str | None, content: str) -> str:
    """Return a preview-friendly content type for a parsed content snapshot."""

    normalized_type = (file_type or "txt").lower().lstrip(".")
    if normalized_type in {"html", "htm"} and looks_like_html(content):
        return "text/html; charset=utf-8"
    if normalized_type in {"md", "markdown", "pdf"} or looks_like_markdown(content):
        return "text/markdown; charset=utf-8"
    return "text/plain; charset=utf-8"


def looks_like_markdown(content: str) -> bool:
    """Return whether parsed content contains Markdown structure."""

    sample = content[:6000]
    return bool(
        re.search(r"^#{1,6}\s+\S", sample, flags=re.MULTILINE)
        or "```" in sample
        or re.search(r"!\[[^\]]*]\([^)]+\)", sample)
        or re.search(r"\|.+\|\s*\r?\n\|[-:|\s]+\|", sample)
    )


def looks_like_html(content: str) -> bool:
    """Return whether parsed content looks like an HTML document or fragment."""

    sample = content[:6000]
    return bool(
        re.search(r"^\s*<!doctype\s+html", sample, flags=re.IGNORECASE)
        or re.search(
            r"<\s*(html|body|main|article|section|h[1-6]|p|table|ul|ol|pre|blockquote)\b",
            sample,
            flags=re.IGNORECASE,
        )
    )


def safe_asset_filename(source_path: str, content_type: str, index: int) -> str:
    """Return a stable object filename for a parsed asset."""

    filename = PurePosixPath(source_path.replace("\\", "/")).name or f"asset-{index + 1}"
    if "." not in filename:
        extension = mimetypes.guess_extension(content_type) or ".bin"
        filename = f"{filename}{extension}"
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)


def asset_aliases(asset: ParsedAsset) -> list[str]:
    """Return source path aliases that should be rewritten to the controlled asset URL."""

    aliases = [normalize_asset_reference(asset.source_path)]
    metadata_aliases = asset.metadata.get("aliases")
    if isinstance(metadata_aliases, list):
        for value in metadata_aliases:
            if isinstance(value, str):
                aliases.append(normalize_asset_reference(value))
    return [alias for alias in dict.fromkeys(aliases) if alias]


def normalize_asset_reference(value: str) -> str:
    """Normalize a parser-emitted asset reference for Markdown/HTML matching."""

    return value.strip().replace("\\", "/")


def rewrite_asset_references(text: str, replacements: Mapping[str, str]) -> str:
    """Rewrite relative Markdown/HTML asset references to backend-controlled URLs."""

    rewritten = text
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if is_external_asset_reference(source):
            continue
        rewritten = rewrite_markdown_asset_reference(rewritten, source, target)
        rewritten = rewrite_html_asset_reference(rewritten, source, target)
    return rewritten


def build_ingestion_chunks(
    parsed: ParsedDocument,
    *,
    parsed_text: str,
    asset_replacements: Mapping[str, str],
    file_type: str | None,
    chunk_size: int,
    chunk_overlap: int,
) -> list[ParsedChunk]:
    """Build final chunks from parser-emitted structured chunks or plain text."""

    if not parsed.chunks:
        return chunk_text(parsed_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    structured_chunks = [
        rewrite_parsed_chunk(
            chunk,
            asset_replacements=asset_replacements,
        )
        for chunk in parsed.chunks
    ]
    return merge_structured_chunks(
        structured_chunks,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def rewrite_parsed_chunk(
    chunk: ParsedChunk,
    *,
    asset_replacements: Mapping[str, str],
) -> ParsedChunk:
    """Rewrite parser chunk content into the persisted ingestion representation."""

    content = rewrite_asset_references(chunk.content, asset_replacements)
    metadata = dict(chunk.metadata)
    if chunk.page_num is not None:
        metadata.setdefault("page_num", chunk.page_num)
    if chunk.bbox is not None:
        metadata.setdefault("bbox", chunk.bbox)
    return ParsedChunk(
        content=content,
        chunk_type=chunk.chunk_type,
        page_num=chunk.page_num,
        bbox=chunk.bbox,
        metadata=metadata,
    )


def rewrite_markdown_asset_reference(text: str, source: str, target: str) -> str:
    """Rewrite Markdown image/link targets that match a parsed asset source."""

    pattern = re.compile(r"(\]\()\s*" + re.escape(source) + r"\s*(\))")
    return pattern.sub(lambda match: f"{match.group(1)}{target}{match.group(2)}", text)


def rewrite_html_asset_reference(text: str, source: str, target: str) -> str:
    """Rewrite quoted HTML src/href attributes that match a parsed asset source."""

    pattern = re.compile(
        r"((?:src|href)\s*=\s*[\"'])" + re.escape(source) + r"([\"'])",
        flags=re.IGNORECASE,
    )
    return pattern.sub(lambda match: f"{match.group(1)}{target}{match.group(2)}", text)


def is_external_asset_reference(value: str) -> bool:
    """Return whether an asset reference should not be rewritten as a local file."""

    normalized = value.lower()
    return normalized.startswith(("http://", "https://", "data:", "/api/"))


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
        document.metadata_ = metadata_with_ingestion_progress(
            document.metadata_,
            stage="reading_source",
            progress=18,
            status="processing",
            detail="Reading source content",
        )
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
        document.metadata_ = metadata_with_ingestion_progress(
            document.metadata_,
            stage="failed",
            progress=100,
            status="failed",
            detail="Failed during ingestion",
        )
        await session.commit()


async def document_exists(
    session_factory: async_sessionmaker[AsyncSession],
    document_id: UUID,
) -> bool:
    """Return whether a document still exists while ingestion is running."""

    async with session_factory() as session:
        result = await session.execute(select(Document.id).where(Document.id == document_id))
        return result.scalar_one_or_none() is not None


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
    document: Document | None = None,
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
            **(document_governance_payload(document) if document is not None else {}),
        },
    )


def sparse_vector(text: str) -> models.SparseVector:
    """Create a deterministic sparse keyword vector from token counts."""

    tokens = findall(r"[\w]+", text.lower())
    counts = Counter(tokens)
    values_by_index: Counter[int] = Counter()
    for token, count in counts.items():
        index = int(sha256(token.encode("utf-8")).hexdigest(), 16) % SPARSE_INDEX_MODULUS
        values_by_index[index] += count
    indices = sorted(values_by_index)
    values = [float(values_by_index[index]) for index in indices]
    return models.SparseVector(indices=indices, values=values)
