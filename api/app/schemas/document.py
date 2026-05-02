from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, Field

GovernanceSourceType = Literal[
    "official_law",
    "official_guidance",
    "internal_sop",
    "expert_summary",
    "chat_record",
    "video_transcript",
    "other",
]
ReviewStatus = Literal["draft", "reviewed", "published", "deprecated"]


class DocumentGovernanceInput(BaseModel):
    """Required governance labels for newly imported documents."""

    model_config = ConfigDict(extra="forbid")

    governance_source_type: GovernanceSourceType
    authority_level: int = Field(ge=1, le=5)
    review_status: ReviewStatus


class DocumentTextCreateRequest(BaseModel):
    """Input for directly uploading plaintext or markdown content."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    file_type: str = Field(default="txt", pattern="^(txt|md|markdown)$")
    governance_source_type: GovernanceSourceType
    authority_level: int = Field(ge=1, le=5)
    review_status: ReviewStatus
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentUrlCreateRequest(BaseModel):
    """Input for ingesting a document from a URL."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=500)
    url: AnyUrl
    governance_source_type: GovernanceSourceType
    authority_level: int = Field(ge=1, le=5)
    review_status: ReviewStatus
    metadata: dict[str, object] = Field(default_factory=dict)


class DocumentGovernanceUpdateRequest(BaseModel):
    """Governance update that creates a new document version snapshot."""

    model_config = ConfigDict(extra="forbid")

    governance_source_type: GovernanceSourceType | None = None
    authority_level: int | None = Field(default=None, ge=1, le=5)
    review_status: ReviewStatus | None = None
    change_summary: str | None = Field(default=None, max_length=1000)


class DocumentResponse(BaseModel):
    """Document metadata and ingestion status."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")

    id: UUID
    kb_id: UUID
    name: str
    file_type: str | None
    file_size: int | None
    minio_path: str | None
    file_hash: str | None
    source_type: str
    source_url: str | None
    governance_source_type: str
    authority_level: int
    review_status: str
    current_version: int
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


class DocumentVersionResponse(BaseModel):
    """Immutable snapshot of a document version."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")

    id: UUID
    document_id: UUID
    kb_id: UUID
    version_number: int
    name: str
    file_type: str | None
    file_size: int | None
    minio_path: str | None
    file_hash: str | None
    source_type: str
    source_url: str | None
    governance_source_type: str
    authority_level: int
    review_status: str
    metadata: dict[str, object] = Field(alias="metadata_")
    change_summary: str | None
    created_by_id: UUID | None
    created_by_email: str | None
    created_at: datetime


class DocumentVersionListResponse(BaseModel):
    """List response for document version history."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[DocumentVersionResponse]


class DocumentAuditLogResponse(BaseModel):
    """One append-only document audit entry."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    document_id: UUID | None
    kb_id: UUID | None
    actor_user_id: UUID | None
    actor_email: str | None
    action: str
    summary: str | None
    before: dict[str, object]
    after: dict[str, object]
    created_at: datetime


class DocumentAuditLogListResponse(BaseModel):
    """List response for document audit history."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[DocumentAuditLogResponse]


class DocumentBatchUploadItem(BaseModel):
    """Result for one file in a batch upload request."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    status: Literal["created", "skipped"]
    reason: Literal["duplicate_name", "duplicate_file_hash", "empty_file"] | None = None
    detail: str | None = None
    document: DocumentResponse | None = None


class DocumentBatchUploadResponse(BaseModel):
    """Batch upload response with created and skipped file details."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    created_count: int
    skipped_count: int
    items: list[DocumentBatchUploadItem]


class ChunkResponse(BaseModel):
    """Chunk metadata and source-of-truth content."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")

    id: UUID
    document_id: UUID
    kb_id: UUID
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


class DocumentContentResponse(BaseModel):
    """Parsed full-content snapshot for document preview."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    document_id: UUID
    content: str
    content_type: str
    source: str


class DocumentAssetResponse(BaseModel):
    """Metadata for a binary asset extracted from a document."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")

    id: UUID
    document_id: UUID
    kb_id: UUID
    asset_index: int
    asset_type: str
    source_path: str
    minio_path: str
    content_type: str
    file_size: int
    file_hash: str
    metadata: dict[str, object] = Field(alias="metadata_")
    created_at: datetime


class DocumentAssetListResponse(BaseModel):
    """List response for parsed document assets."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[DocumentAssetResponse]
