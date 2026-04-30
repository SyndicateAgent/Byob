from uuid import uuid4

from api.app.config import Settings
from api.app.main import create_app
from api.app.models.chunk import Chunk
from api.app.services.ingestion_service import build_qdrant_point
from workers.chunkers.semantic_chunker import chunk_text
from workers.parsers.registry import parse_document_bytes


def test_phase_three_routes_are_mounted() -> None:
    """Knowledge base and document ingestion routes are registered."""

    app = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v1/knowledge-bases" in paths
    assert "/api/v1/knowledge-bases/{kb_id}/documents" in paths
    assert "/api/v1/documents/{document_id}/chunks" in paths


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


def test_qdrant_point_payload_excludes_chunk_content() -> None:
    """Qdrant payload stores identifiers and filters, not source text."""

    chunk_id = uuid4()
    document_id = uuid4()
    kb_id = uuid4()
    tenant_id = uuid4()
    chunk = Chunk(
        id=chunk_id,
        document_id=document_id,
        kb_id=kb_id,
        tenant_id=tenant_id,
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
    assert point.payload["tags"] == ["manual"]
