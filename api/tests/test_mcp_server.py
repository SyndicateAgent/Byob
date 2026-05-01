from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.app.mcp_server import (
    MCP_SERVER_NAME,
    bounded_limit,
    parse_uuid,
    serialize_asset,
    serialize_chunk,
    serialize_document,
    serialize_knowledge_base,
)


def test_mcp_server_has_product_name() -> None:
    """The MCP server is branded for Agent-facing BYOB retrieval."""

    assert MCP_SERVER_NAME == "BYOB Vector Database"


def test_mcp_serializers_return_json_friendly_values() -> None:
    """MCP tools return structured JSON-friendly IDs and timestamps."""

    now = datetime(2026, 5, 1, tzinfo=UTC)
    kb_id = uuid4()
    document_id = uuid4()
    chunk_id = uuid4()
    asset_id = uuid4()

    knowledge_base = SimpleNamespace(
        id=kb_id,
        name="Docs",
        description="Agent context",
        status="active",
        document_count=2,
        chunk_count=12,
        qdrant_collection="kb_docs",
        created_at=now,
        updated_at=now,
    )
    document = SimpleNamespace(
        id=document_id,
        kb_id=kb_id,
        name="manual.md",
        status="completed",
        source_type="upload",
        file_type="md",
        file_size=123,
        file_hash="abc",
        source_url=None,
        chunk_count=1,
        error_message=None,
        metadata_={"topic": "manual"},
        created_at=now,
        updated_at=now,
    )
    chunk = SimpleNamespace(
        id=chunk_id,
        document_id=document_id,
        kb_id=kb_id,
        chunk_index=0,
        content="source text",
        content_hash="def",
        chunk_type="text",
        parent_chunk_id=None,
        page_num=None,
        bbox=None,
        metadata_={"section": "intro"},
        created_at=now,
    )
    asset = SimpleNamespace(
        id=asset_id,
        document_id=document_id,
        kb_id=kb_id,
        asset_index=0,
        asset_type="image",
        source_path="images/plot.png",
        content_type="image/png",
        file_size=456,
        file_hash="ghi",
        metadata_={"alt": "plot"},
        created_at=now,
    )

    assert serialize_knowledge_base(knowledge_base)["id"] == str(kb_id)
    assert serialize_document(document)["metadata"] == {"topic": "manual"}
    assert serialize_chunk(chunk)["content"] == "source text"
    assert serialize_asset(asset)["url"] == f"/api/v1/documents/{document_id}/assets/{asset_id}"


def test_mcp_input_helpers_validate_bounds_and_uuids() -> None:
    """MCP helper validation keeps tool arguments predictable."""

    value = uuid4()

    assert parse_uuid(str(value), "kb_id") == value
    assert bounded_limit(-1, default=50, maximum=200) == 50
    assert bounded_limit(500, default=50, maximum=200) == 200

    with pytest.raises(ValueError, match="document_id must be a valid UUID"):
        parse_uuid("not-a-uuid", "document_id")