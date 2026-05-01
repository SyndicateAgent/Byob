from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from api.app.config import Settings
from api.app.core.qdrant_client import QdrantStoreClient
from api.app.main import create_app
from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.knowledge_base import KnowledgeBase
from api.app.services.document_service import (
    find_duplicate_document,
    metadata_with_ingestion_progress,
)
from api.app.services.ingestion_service import (
    build_qdrant_point,
    parsed_content_type,
    rewrite_asset_references,
)
from workers.chunkers.semantic_chunker import chunk_text
from workers.parsers.registry import parse_document_bytes


def test_phase_three_routes_are_mounted() -> None:
    """Knowledge base and document ingestion routes are registered."""

    app = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v1/knowledge-bases" in paths
    assert "/api/v1/knowledge-bases/{kb_id}/documents" in paths
    assert "/api/v1/knowledge-bases/{kb_id}/documents/batch" in paths
    assert "/api/v1/documents/{document_id}/chunks" in paths
    assert "/api/v1/documents/{document_id}/content" in paths
    assert "/api/v1/documents/{document_id}/assets" in paths
    assert "/api/v1/documents/{document_id}/assets/{asset_id}" in paths


def test_text_parser_and_chunker_create_chunks() -> None:
    """Plain text parsing and semantic chunking produce bounded chunks."""

    parsed = parse_document_bytes(
        b"First paragraph has useful text.\n\nSecond paragraph has more useful text.",
        "txt",
    )
    chunks = chunk_text(parsed.text, chunk_size=5, chunk_overlap=1)

    assert parsed.metadata["file_type"] == "txt"
    assert len(chunks) >= 2
    assert all(chunk.content for chunk in chunks)


def test_chunker_splits_cjk_text_without_spaces() -> None:
    """PDF text extraction often returns long CJK paragraphs without spaces."""

    text = "这是一个没有空格的中文段落" * 20
    chunks = chunk_text(text, chunk_size=30, chunk_overlap=5)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 30 for chunk in chunks[:-1])
    assert chunks[1].content.startswith(chunks[0].content[-5:])


def test_chunker_splits_cjk_text_with_pdf_line_whitespace() -> None:
    """CJK PDF extraction may insert whitespace without useful word boundaries."""

    line = "这是一个带有PDF换行空白的中文段落"
    text = "\n".join([line for _ in range(20)])
    chunks = chunk_text(text, chunk_size=40, chunk_overlap=5)

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 40 for chunk in chunks[:-1])


def test_qdrant_point_payload_excludes_chunk_content() -> None:
    """Qdrant payload stores identifiers and filters, not source text."""

    chunk_id = uuid4()
    document_id = uuid4()
    kb_id = uuid4()
    chunk = Chunk(
        id=chunk_id,
        document_id=document_id,
        kb_id=kb_id,
        chunk_index=0,
        content="secret source text",
        chunk_type="text",
        qdrant_point_id=chunk_id,
        metadata_={"tags": ["manual"]},
    )

    point = build_qdrant_point(chunk, dense_vector=[0.1, 0.2], created_at="2026-04-30T00:00:00Z")

    assert point.payload is not None
    assert point.payload["chunk_id"] == str(chunk_id)
    assert "content" not in point.payload
    assert "tenant_id" not in point.payload
    assert point.payload["tags"] == ["manual"]


async def test_qdrant_delete_points_skips_empty_ids() -> None:
    """Deleting no point ids should not call Qdrant."""

    class FailingClient:
        async def collection_exists(self, collection_name: str) -> bool:
            raise AssertionError(f"Unexpected Qdrant call for {collection_name}")

    client = QdrantStoreClient.__new__(QdrantStoreClient)
    client._client = FailingClient()

    await client.delete_points("kb_collection", [])


def test_asset_references_are_rewritten_in_markdown_and_html() -> None:
    """Relative parser asset paths become backend-controlled API URLs."""

    rewritten = rewrite_asset_references(
        '![Figure](images/a.png) <img src="images/a.png"> [external](https://example.com/a.png)',
        {"images/a.png": "/api/v1/documents/doc/assets/asset"},
    )

    assert "![Figure](/api/v1/documents/doc/assets/asset)" in rewritten
    assert '<img src="/api/v1/documents/doc/assets/asset">' in rewritten
    assert "https://example.com/a.png" in rewritten


def test_parsed_content_type_prefers_markdown_for_pdf_snapshots() -> None:
    """PDF parser snapshots can contain Markdown plus sanitized HTML fragments."""

    assert parsed_content_type("pdf", "# Title\n\n<table><tr><td>A</td></tr></table>").startswith(
        "text/markdown"
    )
    assert parsed_content_type("html", "<main><p>Hello</p></main>").startswith("text/html")


def test_ingestion_progress_metadata_preserves_and_resets_run_identity() -> None:
    """Progress metadata keeps one run stable and resets for reprocessing."""

    started = {"ingestion_progress": {"started_at": "old-run"}}
    progressed = metadata_with_ingestion_progress(
        started,
        stage="embedding",
        progress=70,
        status="processing",
        detail="Embedding chunks",
    )
    reset = metadata_with_ingestion_progress(
        progressed,
        stage="queued",
        progress=10,
        status="pending",
        detail="Queued for worker",
        reset=True,
    )

    assert progressed["ingestion_progress"]["started_at"] == "old-run"
    assert reset["ingestion_progress"]["started_at"] != "old-run"


class FakeDuplicateSession:
    def __init__(self, matches: list[Document | None]) -> None:
        self.matches = matches

    async def scalar(self, statement: object) -> Document | None:
        return self.matches.pop(0)


async def test_duplicate_document_lookup_prefers_same_name() -> None:
    """Import deduplication should skip an existing document with the same name."""

    knowledge_base = KnowledgeBase(id=uuid4(), name="KB", qdrant_collection="kb")
    existing = Document(id=uuid4(), kb_id=knowledge_base.id, name="same.pdf", file_hash="old")
    session = cast(AsyncSession, FakeDuplicateSession([existing]))

    duplicate = await find_duplicate_document(
        session,
        knowledge_base,
        name="same.pdf",
        file_hash="new",
    )

    assert duplicate is not None
    assert duplicate.reason == "duplicate_name"
    assert duplicate.document is existing


async def test_duplicate_document_lookup_matches_same_hash() -> None:
    """Import deduplication should skip an existing document with the same file hash."""

    knowledge_base = KnowledgeBase(id=uuid4(), name="KB", qdrant_collection="kb")
    existing = Document(id=uuid4(), kb_id=knowledge_base.id, name="other.pdf", file_hash="abc")
    session = cast(AsyncSession, FakeDuplicateSession([None, existing]))

    duplicate = await find_duplicate_document(
        session,
        knowledge_base,
        name="new.pdf",
        file_hash="abc",
    )

    assert duplicate is not None
    assert duplicate.reason == "duplicate_file_hash"
    assert duplicate.document is existing
