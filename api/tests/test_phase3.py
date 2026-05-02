from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from pytest import MonkeyPatch
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.app.api.v1 import documents as documents_api
from api.app.api.v1 import knowledge_bases as knowledge_bases_api
from api.app.config import Settings
from api.app.core.qdrant_client import QdrantStoreClient
from api.app.main import create_app
from api.app.models.chunk import Chunk
from api.app.models.document import Document
from api.app.models.knowledge_base import KnowledgeBase
from api.app.schemas.auth import CurrentUser
from api.app.services.document_service import (
    find_duplicate_document,
    metadata_with_ingestion_progress,
)
from api.app.services.ingestion_service import (
    build_qdrant_point,
    parsed_content_type,
    rewrite_asset_references,
    sparse_vector,
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


def test_chunker_preserves_markdown_asset_reference() -> None:
    """Single-token Markdown image references should not be split into spaced chars."""

    asset_url = (
        "/api/v1/documents/2a5747ab-9c85-4ae6-835d-e8b81c729058"
        "/assets/d3265b90-751e-4400-b3a8-18f94f2215a5"
    )
    text = (
        "This paragraph has enough regular words to share a chunk with the next block. " * 4
        + f"\n\n![]({asset_url})\n\n"
        + "Based on the available evidence, the timeline is consistent."
    )

    content = "\n".join(chunk.content for chunk in chunk_text(text, chunk_size=90, chunk_overlap=5))

    assert f"![]({asset_url})" in content
    assert "! [ ]" not in content
    assert "/ a p i /" not in content


def test_chunker_repairs_spaced_markdown_asset_reference() -> None:
    """Already-spaced image references from PDF extraction are normalized for chunks."""

    text = "Conclusion\n\n! [ ] ( / a p i / v 1 / documents / doc / assets / asset )"
    content = "\n".join(chunk.content for chunk in chunk_text(text, chunk_size=80, chunk_overlap=0))

    assert "![](/api/v1/documents/doc/assets/asset)" in content


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
    assert point.payload["review_status"] == "published"
    assert point.payload["authority_level"] == 3


def test_sparse_vector_merges_hash_index_collisions(monkeypatch: MonkeyPatch) -> None:
    """Qdrant sparse vectors must not contain duplicate indices."""

    monkeypatch.setattr("api.app.services.ingestion_service.SPARSE_INDEX_MODULUS", 1)

    vector = sparse_vector("alpha beta alpha")

    assert vector.indices == [0]
    assert vector.values == [3.0]


async def test_qdrant_delete_points_skips_empty_ids() -> None:
    """Deleting no point ids should not call Qdrant."""

    class FailingClient:
        async def collection_exists(self, collection_name: str) -> bool:
            raise AssertionError(f"Unexpected Qdrant call for {collection_name}")

    client = QdrantStoreClient.__new__(QdrantStoreClient)
    client._client = FailingClient()

    await client.delete_points("kb_collection", [])


async def test_qdrant_upsert_wraps_unexpected_response() -> None:
    """Qdrant upsert failures include collection and vector shape context."""

    class FailingClient:
        async def upsert(
            self,
            *,
            collection_name: str,
            points: list[models.PointStruct],
            wait: bool,
        ) -> None:
            raise UnexpectedResponse(
                422,
                "Unprocessable Entity",
                b'{"status":{"error":"bad vector"}}',
                headers={},
            )

    point = models.PointStruct(
        id=str(uuid4()),
        vector={
            "dense": [0.1, 0.2],
            "sparse": models.SparseVector(indices=[1, 2], values=[1.0, 2.0]),
        },
        payload={},
    )
    client = QdrantStoreClient.__new__(QdrantStoreClient)
    client._client = FailingClient()

    with pytest.raises(RuntimeError) as exc_info:
        await client.upsert_chunks("kb_collection", [point])

    message = str(exc_info.value)
    assert "collection='kb_collection'" in message
    assert "point_count=1" in message
    assert "dense:dense:2" in message
    assert "sparse:sparse:2" in message
    assert "bad vector" in message


async def test_reprocess_deletes_existing_qdrant_points_before_reset(
    monkeypatch: MonkeyPatch,
) -> None:
    """Reprocessing must delete old Qdrant points before chunk rows are cleared."""

    now = datetime.now(UTC)
    kb_id = uuid4()
    document_id = uuid4()
    old_point_id = uuid4()
    old_visual_point_id = uuid4()
    document = Document(
        id=document_id,
        kb_id=kb_id,
        name="paper.pdf",
        file_type="pdf",
        file_size=128,
        minio_path="documents/paper.pdf",
        file_hash="hash",
        source_type="upload",
        governance_source_type="internal_sop",
        authority_level=3,
        review_status="published",
        current_version=1,
        status="completed",
        error_message=None,
        metadata_={},
        chunk_count=1,
    )
    document.created_at = now
    document.updated_at = now
    knowledge_base = KnowledgeBase(id=kb_id, name="KB", qdrant_collection="kb_collection")
    calls: list[str] = []

    class FakeQdrantClient:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, list[str]]] = []

        async def delete_points(self, collection_name: str, point_ids: list[str]) -> None:
            calls.append("delete_points")
            self.deleted.append((collection_name, point_ids))

    class FakeMinioClient:
        def __init__(self) -> None:
            self.deleted_prefixes: list[str] = []

        async def delete_prefix(self, prefix: str) -> int:
            calls.append("delete_prefix")
            self.deleted_prefixes.append(prefix)
            return 1

    qdrant_client = FakeQdrantClient()
    minio_client = FakeMinioClient()
    request = cast(
        Request,
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(qdrant_client=qdrant_client, minio_client=minio_client)
            )
        ),
    )

    async def fake_get_document(session: AsyncSession, lookup_id: UUID) -> Document | None:
        calls.append("get_document")
        assert lookup_id == document_id
        return document

    async def fake_get_knowledge_base(
        session: AsyncSession,
        lookup_id: UUID,
    ) -> KnowledgeBase | None:
        calls.append("get_knowledge_base")
        assert lookup_id == kb_id
        return knowledge_base

    async def fake_list_document_qdrant_point_ids(
        session: AsyncSession,
        selected_document: Document,
    ) -> list[str]:
        calls.append("list_point_ids")
        assert selected_document is document
        return [str(old_point_id)]

    async def fake_list_document_visual_point_ids(
        session: AsyncSession,
        selected_document: Document,
    ) -> list[str]:
        calls.append("list_visual_point_ids")
        assert selected_document is document
        return [str(old_visual_point_id)]

    async def fake_reset_document_for_reprocess(
        session: AsyncSession,
        selected_document: Document,
        **kwargs: object,
    ) -> Document:
        calls.append("reset")
        assert selected_document is document
        assert "actor" in kwargs
        assert qdrant_client.deleted == [
            ("kb_collection", [str(old_point_id)]),
            ("kb_collection_visual", [str(old_visual_point_id)]),
        ]
        assert minio_client.deleted_prefixes == [
            f"knowledge_bases/{kb_id}/documents/{document_id}/"
        ]
        document.status = "pending"
        document.chunk_count = 0
        return document

    def fake_enqueue_document(queued_document_id: UUID) -> None:
        calls.append("enqueue")
        assert queued_document_id == document_id

    monkeypatch.setattr(documents_api, "get_document", fake_get_document)
    monkeypatch.setattr(documents_api, "get_knowledge_base", fake_get_knowledge_base)
    monkeypatch.setattr(
        documents_api,
        "list_document_qdrant_point_ids",
        fake_list_document_qdrant_point_ids,
    )
    monkeypatch.setattr(
        documents_api,
        "list_document_visual_point_ids",
        fake_list_document_visual_point_ids,
    )
    monkeypatch.setattr(
        documents_api,
        "reset_document_for_reprocess",
        fake_reset_document_for_reprocess,
    )
    monkeypatch.setattr(documents_api, "enqueue_document", fake_enqueue_document)

    response = await documents_api.reprocess_document_endpoint(
        document_id,
        request,
        current_user=CurrentUser(id=uuid4(), email="admin@example.com", role="admin"),
        session=cast(AsyncSession, object()),
    )

    assert calls == [
        "get_document",
        "get_knowledge_base",
        "list_point_ids",
        "list_visual_point_ids",
        "delete_points",
        "delete_points",
        "delete_prefix",
        "reset",
        "enqueue",
    ]
    assert response.id == document_id
    assert response.status == "pending"


async def test_content_update_deletes_vectors_before_reindex(
    monkeypatch: MonkeyPatch,
) -> None:
    """Editing source content must remove old vectors before queueing a new run."""

    now = datetime.now(UTC)
    kb_id = uuid4()
    document_id = uuid4()
    old_point_id = uuid4()
    old_visual_point_id = uuid4()
    document = Document(
        id=document_id,
        kb_id=kb_id,
        name="policy.pdf",
        file_type="pdf",
        file_size=256,
        minio_path="documents/policy.pdf",
        file_hash="hash",
        source_type="upload",
        governance_source_type="internal_sop",
        authority_level=3,
        review_status="published",
        current_version=1,
        status="completed",
        error_message=None,
        metadata_={},
        chunk_count=3,
    )
    document.created_at = now
    document.updated_at = now
    knowledge_base = KnowledgeBase(id=kb_id, name="KB", qdrant_collection="kb_collection")
    calls: list[str] = []

    class FakeQdrantClient:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, list[str]]] = []

        async def delete_points(self, collection_name: str, point_ids: list[str]) -> None:
            calls.append("delete_points")
            self.deleted.append((collection_name, point_ids))

    class FakeMinioClient:
        def __init__(self) -> None:
            self.deleted_prefixes: list[str] = []
            self.deleted_objects: list[str] = []

        async def delete_prefix(self, prefix: str) -> int:
            calls.append("delete_prefix")
            self.deleted_prefixes.append(prefix)
            return 2

        async def delete_object(self, key: str | None) -> None:
            calls.append("delete_object")
            if key is not None:
                self.deleted_objects.append(key)

    qdrant_client = FakeQdrantClient()
    minio_client = FakeMinioClient()
    request = cast(
        Request,
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(qdrant_client=qdrant_client, minio_client=minio_client)
            )
        ),
    )

    async def fake_get_document(session: AsyncSession, lookup_id: UUID) -> Document | None:
        calls.append("get_document")
        assert lookup_id == document_id
        return document

    async def fake_get_knowledge_base(
        session: AsyncSession,
        lookup_id: UUID,
    ) -> KnowledgeBase | None:
        calls.append("get_knowledge_base")
        assert lookup_id == kb_id
        return knowledge_base

    async def fake_list_document_qdrant_point_ids(
        session: AsyncSession,
        selected_document: Document,
    ) -> list[str]:
        calls.append("list_point_ids")
        assert selected_document is document
        return [str(old_point_id)]

    async def fake_list_document_visual_point_ids(
        session: AsyncSession,
        selected_document: Document,
    ) -> list[str]:
        calls.append("list_visual_point_ids")
        assert selected_document is document
        return [str(old_visual_point_id)]

    async def fake_update_document_content_source(
        session: AsyncSession,
        selected_document: Document,
        payload: object,
        **kwargs: object,
    ) -> Document:
        calls.append("update_content")
        assert selected_document is document
        assert "actor" in kwargs
        assert qdrant_client.deleted == [
            ("kb_collection", [str(old_point_id)]),
            ("kb_collection_visual", [str(old_visual_point_id)]),
        ]
        assert minio_client.deleted_prefixes == [
            f"knowledge_bases/{kb_id}/documents/{document_id}/"
        ]
        assert minio_client.deleted_objects == ["documents/policy.pdf"]
        assert isinstance(payload, documents_api.DocumentContentUpdateRequest)
        assert payload.content == "edited source"
        document.source_type = "text"
        document.status = "pending"
        document.chunk_count = 0
        return document

    def fake_enqueue_document(queued_document_id: UUID) -> None:
        calls.append("enqueue")
        assert queued_document_id == document_id

    monkeypatch.setattr(documents_api, "get_document", fake_get_document)
    monkeypatch.setattr(documents_api, "get_knowledge_base", fake_get_knowledge_base)
    monkeypatch.setattr(
        documents_api,
        "list_document_qdrant_point_ids",
        fake_list_document_qdrant_point_ids,
    )
    monkeypatch.setattr(
        documents_api,
        "list_document_visual_point_ids",
        fake_list_document_visual_point_ids,
    )
    monkeypatch.setattr(
        documents_api,
        "update_document_content_source",
        fake_update_document_content_source,
    )
    monkeypatch.setattr(documents_api, "enqueue_document", fake_enqueue_document)

    response = await documents_api.update_document_content_endpoint(
        document_id,
        documents_api.DocumentContentUpdateRequest(content="edited source", file_type="md"),
        request,
        current_user=CurrentUser(id=uuid4(), email="admin@example.com", role="admin"),
        session=cast(AsyncSession, object()),
    )

    assert calls == [
        "get_document",
        "get_knowledge_base",
        "list_point_ids",
        "list_visual_point_ids",
        "delete_points",
        "delete_points",
        "delete_prefix",
        "delete_object",
        "update_content",
        "enqueue",
    ]
    assert response.id == document_id
    assert response.source_type == "text"
    assert response.status == "pending"


async def test_delete_document_removes_minio_before_db_delete(
    monkeypatch: MonkeyPatch,
) -> None:
    """Deleting a document must remove vectors and MinIO objects before DB deletion."""

    now = datetime.now(UTC)
    kb_id = uuid4()
    document_id = uuid4()
    old_point_id = uuid4()
    old_visual_point_id = uuid4()
    document = Document(
        id=document_id,
        kb_id=kb_id,
        name="source.pdf",
        file_type="pdf",
        file_size=256,
        minio_path="knowledge_bases/source-file",
        file_hash="hash",
        source_type="upload",
        governance_source_type="internal_sop",
        authority_level=3,
        review_status="published",
        current_version=1,
        status="completed",
        error_message=None,
        metadata_={},
        chunk_count=3,
    )
    document.created_at = now
    document.updated_at = now
    knowledge_base = KnowledgeBase(id=kb_id, name="KB", qdrant_collection="kb_collection")
    calls: list[str] = []

    class FakeQdrantClient:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, list[str]]] = []

        async def delete_points(self, collection_name: str, point_ids: list[str]) -> None:
            calls.append("delete_points")
            self.deleted.append((collection_name, point_ids))

    class FakeMinioClient:
        async def delete_prefix(self, prefix: str) -> int:
            calls.append("delete_prefix")
            assert prefix == f"knowledge_bases/{kb_id}/documents/{document_id}/"
            return 2

        async def delete_object(self, key: str | None) -> None:
            calls.append("delete_object")
            assert key == "knowledge_bases/source-file"

    request = cast(
        Request,
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                        qdrant_client=(qdrant_client := FakeQdrantClient()),
                    minio_client=FakeMinioClient(),
                )
            )
        ),
    )

    async def fake_get_document(session: AsyncSession, lookup_id: UUID) -> Document | None:
        calls.append("get_document")
        assert lookup_id == document_id
        return document

    async def fake_get_knowledge_base(
        session: AsyncSession,
        lookup_id: UUID,
    ) -> KnowledgeBase | None:
        calls.append("get_knowledge_base")
        assert lookup_id == kb_id
        return knowledge_base

    async def fake_list_document_qdrant_point_ids(
        session: AsyncSession,
        selected_document: Document,
    ) -> list[str]:
        calls.append("list_point_ids")
        assert selected_document is document
        return [str(old_point_id)]

    async def fake_list_document_visual_point_ids(
        session: AsyncSession,
        selected_document: Document,
    ) -> list[str]:
        calls.append("list_visual_point_ids")
        assert selected_document is document
        return [str(old_visual_point_id)]

    async def fake_delete_document(
        session: AsyncSession,
        selected_document: Document,
        **kwargs: object,
    ) -> None:
        calls.append("delete_document")
        assert selected_document is document
        assert "actor" in kwargs

    monkeypatch.setattr(documents_api, "get_document", fake_get_document)
    monkeypatch.setattr(documents_api, "get_knowledge_base", fake_get_knowledge_base)
    monkeypatch.setattr(
        documents_api,
        "list_document_qdrant_point_ids",
        fake_list_document_qdrant_point_ids,
    )
    monkeypatch.setattr(
        documents_api,
        "list_document_visual_point_ids",
        fake_list_document_visual_point_ids,
    )
    monkeypatch.setattr(documents_api, "delete_document", fake_delete_document)

    await documents_api.delete_document_endpoint(
        document_id,
        request,
        current_user=CurrentUser(id=uuid4(), email="admin@example.com", role="admin"),
        session=cast(AsyncSession, object()),
    )

    assert calls == [
        "get_document",
        "get_knowledge_base",
        "list_point_ids",
        "list_visual_point_ids",
        "delete_points",
        "delete_points",
        "delete_prefix",
        "delete_object",
        "delete_document",
    ]
    assert qdrant_client.deleted == [
        ("kb_collection", [str(old_point_id)]),
        ("kb_collection_visual", [str(old_visual_point_id)]),
    ]


async def test_delete_knowledge_base_removes_storage_before_db_delete(
    monkeypatch: MonkeyPatch,
) -> None:
    """Deleting a KB must remove its MinIO tree and Qdrant collection first."""

    kb_id = uuid4()
    knowledge_base = KnowledgeBase(id=kb_id, name="KB", qdrant_collection="kb_collection")
    calls: list[str] = []

    class FakeMinioClient:
        async def delete_prefix(self, prefix: str) -> int:
            calls.append("delete_prefix")
            assert prefix == f"knowledge_bases/{kb_id}/"
            return 5

    class FakeQdrantClient:
        def __init__(self) -> None:
            self.deleted_collections: list[str] = []

        async def delete_collection(self, collection_name: str) -> None:
            calls.append("delete_collection")
            self.deleted_collections.append(collection_name)

    class FakeRedisClient:
        async def delete_prefix(self, prefix: str) -> int:
            calls.append("clear_cache")
            assert prefix == "retrieval:"
            return 1

    request = cast(
        Request,
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    minio_client=FakeMinioClient(),
                        qdrant_client=(qdrant_client := FakeQdrantClient()),
                    redis_client=FakeRedisClient(),
                )
            )
        ),
    )

    async def fake_get_knowledge_base(
        session: AsyncSession,
        lookup_id: UUID,
    ) -> KnowledgeBase | None:
        calls.append("get_knowledge_base")
        assert lookup_id == kb_id
        return knowledge_base

    async def fake_delete_knowledge_base(
        session: AsyncSession,
        selected_knowledge_base: KnowledgeBase,
    ) -> None:
        calls.append("delete_kb")
        assert selected_knowledge_base is knowledge_base

    monkeypatch.setattr(knowledge_bases_api, "get_knowledge_base", fake_get_knowledge_base)
    monkeypatch.setattr(knowledge_bases_api, "delete_knowledge_base", fake_delete_knowledge_base)

    await knowledge_bases_api.delete_knowledge_base_endpoint(
        kb_id,
        request,
        current_user=CurrentUser(id=uuid4(), email="admin@example.com", role="admin"),
        session=cast(AsyncSession, object()),
    )

    assert calls == [
        "get_knowledge_base",
        "delete_prefix",
        "delete_collection",
        "delete_collection",
        "delete_kb",
        "clear_cache",
    ]
    assert qdrant_client.deleted_collections == ["kb_collection", "kb_collection_visual"]


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
