from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeBaseCreateRequest(BaseModel):
    """Input for creating a tenant-scoped knowledge base."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    embedding_model: str = Field(default="BAAI/bge-m3", min_length=1, max_length=100)
    embedding_dim: int = Field(default=1024, ge=1)
    chunk_size: int = Field(default=512, ge=128)
    chunk_overlap: int = Field(default=50, ge=0)
    retrieval_config: dict[str, object] = Field(default_factory=dict)


class KnowledgeBaseUpdateRequest(BaseModel):
    """Partial update for mutable knowledge base settings."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    chunk_size: int | None = Field(default=None, ge=128)
    chunk_overlap: int | None = Field(default=None, ge=0)
    retrieval_config: dict[str, object] | None = None
    status: str | None = Field(default=None, pattern="^(active|archived|disabled)$")


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base metadata exposed to management clients."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    embedding_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    retrieval_config: dict[str, object]
    qdrant_collection: str
    status: str
    document_count: int
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListResponse(BaseModel):
    """List response for knowledge bases."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[KnowledgeBaseResponse]


class KnowledgeBaseStatsResponse(BaseModel):
    """Knowledge base ingestion statistics."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    kb_id: UUID
    document_count: int
    chunk_count: int
    status: str
