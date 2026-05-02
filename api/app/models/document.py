from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base
from api.app.models.types import created_at_column, status_column, updated_at_column, uuid_pk


class Document(Base):
    """Source document registered under one knowledge base."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("idx_documents_kb_status", "kb_id", "status"),
        Index("idx_documents_kb_review_status", "kb_id", "review_status"),
        Index("idx_documents_kb_authority", "kb_id", "authority_level"),
        Index("idx_documents_kb_name", "kb_id", "name"),
        Index("idx_documents_kb_file_hash", "kb_id", "file_hash"),
        Index("idx_documents_metadata", "metadata", postgresql_using="gin"),
    )

    id: Mapped[UUID] = uuid_pk()
    kb_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(50))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    minio_path: Mapped[str | None] = mapped_column(String(500))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(50), server_default="upload")
    source_url: Mapped[str | None] = mapped_column(Text)
    governance_source_type: Mapped[str] = mapped_column(
        String(50), default="internal_sop", server_default="internal_sop"
    )
    authority_level: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    review_status: Mapped[str] = mapped_column(
        String(20), default="draft", server_default="draft"
    )
    current_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = status_column("pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, server_default="{}")
    chunk_count: Mapped[int] = mapped_column(server_default="0")
    created_at = created_at_column()
    updated_at = updated_at_column()
