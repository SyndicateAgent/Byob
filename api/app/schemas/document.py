from datetime import datetime
from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class DocumentTextCreateRequest(BaseModel):
    """Input for directly uploading plaintext or markdown content."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    file_type: str = Field(default="txt", pattern="^(txt|md|markdown)$")
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentUrlCreateRequest(BaseModel):
    """Input for ingesting a document from a URL."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=500)
    url: AnyUrl
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    """Document metadata and ingestion status."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")

    id: UUID
    kb_id: UUID
    tenant_id: UUID
    name: str
    file_type: str | None
    file_size: int | None
    minio_path: str | None
    file_hash: str | None
    source_type: str
    source_url: str | None
    status: str
    error_message: str | None
    metadata: dict[str, object] = Field(alias="metadata_")
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """List response for documents in one knowledge base."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[DocumentResponse]


class ChunkResponse(BaseModel):
    """Chunk metadata and source-of-truth content."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")

    id: UUID
    document_id: UUID
    kb_id: UUID
    tenant_id: UUID
    chunk_index: int
    content: str
    content_hash: str | None
    chunk_type: str
    parent_chunk_id: UUID | None
    page_num: int | None
    bbox: dict[str, object] | None
    qdrant_point_id: UUID | None
    metadata: dict[str, object] = Field(alias="metadata_")
    created_at: datetime


class ChunkListResponse(BaseModel):
    """List response for document chunks."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[ChunkResponse]
