import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from api.app.config import Settings, get_settings
from api.app.core.embedding import EmbeddingClient
from api.app.core.minio_client import MinioClient
from api.app.core.qdrant_client import QdrantStoreClient
from api.app.core.rerank import RerankClient
from api.app.db.session import create_engine, create_session_factory
from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.document_asset import DocumentAsset
from api.app.models.knowledge_base import KnowledgeBase
from api.app.schemas.retrieval import RetrievalOptions, RetrievalRequest
from api.app.services.document_service import (
    get_document,
    list_chunks,
)
from api.app.services.document_service import (
    get_document_asset as load_document_asset,
)
from api.app.services.document_service import (
    list_document_assets as list_assets_for_document,
)
from api.app.services.query_enhancer import enhance_query
from api.app.services.retrieval_service import search

JsonDict = dict[str, Any]
McpContext = Context[ServerSession, "ByobMcpContext"]
MCP_SERVER_NAME = "BYOB Vector Database"


@dataclass
class ByobMcpContext:
    """Shared runtime resources for BYOB MCP tools."""

    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    qdrant_client: QdrantStoreClient
    embedding_client: EmbeddingClient
    rerank_client: RerankClient
    minio_client: MinioClient


@asynccontextmanager
async def byob_mcp_lifespan(_server: FastMCP) -> AsyncIterator[ByobMcpContext]:
    """Initialize BYOB infrastructure clients for the MCP server process."""

    settings = get_settings()
    engine = create_engine(settings)
    qdrant_client = QdrantStoreClient(
        str(settings.qdrant_url),
        settings.dependency_health_timeout_seconds,
    )
    embedding_client = EmbeddingClient(settings)
    rerank_client = RerankClient(settings)
    minio_client = MinioClient(
        str(settings.minio_endpoint_url),
        settings.dependency_health_timeout_seconds,
        settings,
    )
    try:
        yield ByobMcpContext(
            settings=settings,
            engine=engine,
            session_factory=create_session_factory(engine),
            qdrant_client=qdrant_client,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            minio_client=minio_client,
        )
    finally:
        await qdrant_client.close()
        await embedding_client.close()
        await rerank_client.close()
        await minio_client.close()
        await engine.dispose()


mcp = FastMCP(
    MCP_SERVER_NAME,
    instructions=(
        "Use BYOB tools to discover local knowledge bases and retrieve source chunks for "
        "AI Agent context. Retrieval results include source text and any referenced "
        "document assets. Use get_document_asset when image or file bytes are needed "
        "for multimodal reasoning or direct answer attachments."
    ),
    lifespan=byob_mcp_lifespan,
)


@mcp.tool()
async def list_knowledge_bases(
    ctx: McpContext,
    include_inactive: bool = False,
) -> JsonDict:
    """List BYOB knowledge bases available to the local AI Agent."""

    app_context = mcp_app_context(ctx)
    async with app_context.session_factory() as session:
        statement = select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
        if not include_inactive:
            statement = statement.where(KnowledgeBase.status == "active")
        result = await session.execute(statement)
        knowledge_bases = list(result.scalars().all())

    return {
        "count": len(knowledge_bases),
        "knowledge_bases": [serialize_knowledge_base(item) for item in knowledge_bases],
    }


@mcp.tool()
async def list_documents(
    ctx: McpContext,
    kb_id: str | None = None,
    status: str | None = "completed",
    limit: int = 50,
) -> JsonDict:
    """List documents so an Agent can inspect what source material exists."""

    safe_limit = bounded_limit(limit, default=50, maximum=200)
    app_context = mcp_app_context(ctx)
    async with app_context.session_factory() as session:
        statement = select(Document).order_by(Document.created_at.desc()).limit(safe_limit)
        if kb_id is not None:
            statement = statement.where(Document.kb_id == parse_uuid(kb_id, "kb_id"))
        if status:
            statement = statement.where(Document.status == status)
        result = await session.execute(statement)
        documents = list(result.scalars().all())

    return {"count": len(documents), "documents": [serialize_document(item) for item in documents]}


@mcp.tool()
async def search_knowledge_base(
    query: str,
    ctx: McpContext,
    kb_ids: list[str] | None = None,
    top_k: int = 5,
    filters: dict[str, object] | None = None,
    enable_rerank: bool = True,
    include_metadata: bool = True,
    include_parent_context: bool = False,
    score_threshold: float | None = None,
) -> JsonDict:
    """Run BYOB hybrid dense+sparse retrieval and return source chunks for Agent context."""

    app_context = mcp_app_context(ctx)
    async with app_context.session_factory() as session:
        payload = await build_retrieval_payload(
            session,
            query=query,
            kb_ids=kb_ids,
            top_k=top_k,
            filters=filters,
            enable_rerank=enable_rerank,
            include_metadata=include_metadata,
            include_parent_context=include_parent_context,
            score_threshold=score_threshold,
        )
        response = await search(
            session,
            app_context.settings,
            app_context.qdrant_client,
            app_context.embedding_client,
            app_context.rerank_client,
            request_id=str(uuid4()),
            payload=payload,
        )
    return response.model_dump(mode="json")


@mcp.tool()
async def advanced_search_knowledge_base(
    query: str,
    ctx: McpContext,
    kb_ids: list[str] | None = None,
    top_k: int = 5,
    query_rewrite: bool = True,
    hyde: bool = False,
    decompose: bool = False,
    max_sub_queries: int = 3,
    filters: dict[str, object] | None = None,
    enable_rerank: bool = True,
    include_metadata: bool = True,
    include_parent_context: bool = False,
    score_threshold: float | None = None,
) -> JsonDict:
    """Run enhanced retrieval with optional query rewrite, HyDE, and decomposition."""

    from api.app.api.v1.retrieval import dedupe_queries, merge_responses
    from api.app.schemas.retrieval import RetrievalEnhancements

    app_context = mcp_app_context(ctx)
    enhancement_info = enhance_query(
        query,
        RetrievalEnhancements(
            query_rewrite=query_rewrite,
            hyde=hyde,
            decompose=decompose,
            max_sub_queries=max_sub_queries,
        ),
    )
    queries = [enhancement_info.rewritten_query or query]
    if enhancement_info.hyde_doc is not None:
        queries.append(enhancement_info.hyde_doc)
    queries.extend(enhancement_info.sub_queries)

    async with app_context.session_factory() as session:
        responses = []
        for item in dedupe_queries(queries):
            payload = await build_retrieval_payload(
                session,
                query=item,
                kb_ids=kb_ids,
                top_k=top_k,
                filters=filters,
                enable_rerank=enable_rerank,
                include_metadata=include_metadata,
                include_parent_context=include_parent_context,
                score_threshold=score_threshold,
            )
            responses.append(
                await search(
                    session,
                    app_context.settings,
                    app_context.qdrant_client,
                    app_context.embedding_client,
                    app_context.rerank_client,
                    request_id=str(uuid4()),
                    payload=payload,
                )
            )
        merged = merge_responses(str(uuid4()), responses, top_k)

    return {
        **merged.model_dump(mode="json"),
        "enhancement_info": enhancement_info.model_dump(mode="json"),
    }


@mcp.tool()
async def multi_search_knowledge_base(
    queries: list[str],
    ctx: McpContext,
    kb_ids: list[str] | None = None,
    top_k: int = 5,
    filters: dict[str, object] | None = None,
    enable_rerank: bool = True,
    include_metadata: bool = True,
) -> JsonDict:
    """Run retrieval for multiple Agent sub-questions against BYOB knowledge bases."""

    if not queries:
        raise ValueError("queries must contain at least one query")
    if len(queries) > 20:
        raise ValueError("queries cannot contain more than 20 items")

    app_context = mcp_app_context(ctx)
    async with app_context.session_factory() as session:
        data: list[JsonDict] = []
        for query in queries:
            payload = await build_retrieval_payload(
                session,
                query=query,
                kb_ids=kb_ids,
                top_k=top_k,
                filters=filters,
                enable_rerank=enable_rerank,
                include_metadata=include_metadata,
                include_parent_context=False,
                score_threshold=None,
            )
            response = await search(
                session,
                app_context.settings,
                app_context.qdrant_client,
                app_context.embedding_client,
                app_context.rerank_client,
                request_id=str(uuid4()),
                payload=payload,
            )
            data.append({"query": query, "response": response.model_dump(mode="json")})

    return {"request_id": str(uuid4()), "data": data}


@mcp.tool()
async def get_document_chunks(
    document_id: str,
    ctx: McpContext,
    offset: int = 0,
    limit: int = 50,
) -> JsonDict:
    """Return ordered source chunks for a document selected by an Agent."""

    safe_offset = max(0, offset)
    safe_limit = bounded_limit(limit, default=50, maximum=200)
    app_context = mcp_app_context(ctx)
    async with app_context.session_factory() as session:
        document = await get_document(session, parse_uuid(document_id, "document_id"))
        if document is None:
            raise ValueError("document was not found")
        chunks = await list_chunks(session, document)
        page = chunks[safe_offset : safe_offset + safe_limit]

    return {
        "document": serialize_document(document),
        "offset": safe_offset,
        "limit": safe_limit,
        "total": len(chunks),
        "chunks": [serialize_chunk(chunk) for chunk in page],
    }


@mcp.tool()
async def list_document_assets(
    document_id: str,
    ctx: McpContext,
) -> JsonDict:
    """List images and other parsed binary assets extracted from a document."""

    app_context = mcp_app_context(ctx)
    async with app_context.session_factory() as session:
        document = await get_document(session, parse_uuid(document_id, "document_id"))
        if document is None:
            raise ValueError("document was not found")
        assets = await list_assets_for_document(session, document)

    return {
        "document": serialize_document(document),
        "count": len(assets),
        "assets": [serialize_asset(asset) for asset in assets],
    }


@mcp.tool()
async def get_document_asset(
    document_id: str,
    asset_id: str,
    ctx: McpContext,
    max_bytes: int = 2_000_000,
) -> JsonDict:
    """Return one parsed asset as base64 so an Agent can inspect image/file bytes."""

    safe_max_bytes = max(1, min(max_bytes, 10_000_000))
    app_context = mcp_app_context(ctx)
    async with app_context.session_factory() as session:
        document = await get_document(session, parse_uuid(document_id, "document_id"))
        if document is None:
            raise ValueError("document was not found")
        asset = await load_document_asset(session, document, parse_uuid(asset_id, "asset_id"))
        if asset is None:
            raise ValueError("document asset was not found")

    if asset.file_size > safe_max_bytes:
        raise ValueError(
            f"asset is {asset.file_size} bytes, larger than max_bytes={safe_max_bytes}"
        )

    stored_object = await app_context.minio_client.get_stored_object(asset.minio_path)
    content_type = asset.content_type or stored_object.content_type
    encoded = base64.b64encode(stored_object.content).decode("ascii")
    data_uri = (
        f"data:{content_type};base64,{encoded}"
        if content_type.startswith("image/")
        else None
    )
    return {
        "asset": serialize_asset(asset),
        "content_type": content_type,
        "encoding": "base64",
        "data": encoded,
        "data_uri": data_uri,
    }


def mcp_app_context(ctx: McpContext) -> ByobMcpContext:
    """Return the typed BYOB MCP lifespan context."""

    app_context = ctx.request_context.lifespan_context
    if not isinstance(app_context, ByobMcpContext):
        raise RuntimeError("BYOB MCP context is not initialized")
    return app_context


async def build_retrieval_payload(
    session: AsyncSession,
    *,
    query: str,
    kb_ids: list[str] | None,
    top_k: int,
    filters: dict[str, object] | None,
    enable_rerank: bool,
    include_metadata: bool,
    include_parent_context: bool,
    score_threshold: float | None,
) -> RetrievalRequest:
    """Build and validate a retrieval request for MCP tools."""

    try:
        return RetrievalRequest(
            kb_ids=await resolve_kb_ids(session, kb_ids),
            query=query,
            top_k=top_k,
            filters=filters or {},
            options=RetrievalOptions(
                enable_rerank=enable_rerank,
                include_metadata=include_metadata,
                include_parent_context=include_parent_context,
                score_threshold=score_threshold,
            ),
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid retrieval request: {exc}") from exc


async def resolve_kb_ids(session: AsyncSession, kb_ids: list[str] | None) -> list[UUID]:
    """Resolve requested KB ids, defaulting to all active knowledge bases."""

    if kb_ids:
        return [parse_uuid(kb_id, "kb_ids") for kb_id in kb_ids]

    result = await session.execute(
        select(KnowledgeBase.id)
        .where(KnowledgeBase.status == "active")
        .order_by(KnowledgeBase.created_at.desc())
    )
    resolved_ids = list(result.scalars().all())
    if not resolved_ids:
        raise ValueError("No active knowledge bases are available")
    return resolved_ids


def parse_uuid(value: str, field_name: str) -> UUID:
    """Parse a UUID string with a tool-friendly error."""

    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid UUID") from exc


def bounded_limit(value: int, *, default: int, maximum: int) -> int:
    """Return a safe positive pagination limit."""

    if value <= 0:
        return default
    return min(value, maximum)


def serialize_knowledge_base(knowledge_base: KnowledgeBase) -> JsonDict:
    """Serialize a knowledge base for MCP structured tool output."""

    return {
        "id": str(knowledge_base.id),
        "name": knowledge_base.name,
        "description": knowledge_base.description,
        "status": knowledge_base.status,
        "document_count": knowledge_base.document_count,
        "chunk_count": knowledge_base.chunk_count,
        "qdrant_collection": knowledge_base.qdrant_collection,
        "created_at": knowledge_base.created_at.isoformat(),
        "updated_at": knowledge_base.updated_at.isoformat(),
    }


def serialize_document(document: Document) -> JsonDict:
    """Serialize a document for MCP structured tool output."""

    return {
        "id": str(document.id),
        "kb_id": str(document.kb_id),
        "name": document.name,
        "status": document.status,
        "source_type": document.source_type,
        "file_type": document.file_type,
        "file_size": document.file_size,
        "file_hash": document.file_hash,
        "source_url": document.source_url,
        "governance_source_type": document.governance_source_type,
        "authority_level": document.authority_level,
        "review_status": document.review_status,
        "current_version": document.current_version,
        "chunk_count": document.chunk_count,
        "error_message": document.error_message,
        "metadata": document.metadata_,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
    }


def serialize_chunk(chunk: Chunk) -> JsonDict:
    """Serialize a chunk for MCP structured tool output."""

    return {
        "id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "kb_id": str(chunk.kb_id),
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "content_hash": chunk.content_hash,
        "chunk_type": chunk.chunk_type,
        "parent_chunk_id": str(chunk.parent_chunk_id) if chunk.parent_chunk_id else None,
        "page_num": chunk.page_num,
        "bbox": chunk.bbox,
        "metadata": chunk.metadata_,
        "created_at": chunk.created_at.isoformat(),
    }


def serialize_asset(asset: DocumentAsset) -> JsonDict:
    """Serialize a parsed document asset for Agent-facing MCP output."""

    return {
        "id": str(asset.id),
        "document_id": str(asset.document_id),
        "kb_id": str(asset.kb_id),
        "asset_index": asset.asset_index,
        "asset_type": asset.asset_type,
        "source_path": asset.source_path,
        "url": f"/api/v1/documents/{asset.document_id}/assets/{asset.id}",
        "content_type": asset.content_type,
        "file_size": asset.file_size,
        "file_hash": asset.file_hash,
        "metadata": asset.metadata_,
        "created_at": asset.created_at.isoformat(),
    }


def main() -> None:
    """Run the BYOB MCP server."""

    import argparse

    parser = argparse.ArgumentParser(description="Run the BYOB MCP server for AI Agents.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP transport to use.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for streamable-http transport.")
    parser.add_argument(
        "--port",
        type=int,
        default=8010,
        help="Port for streamable-http transport.",
    )
    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()