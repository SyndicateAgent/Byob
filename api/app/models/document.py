from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base
from api.app.models.types import created_at_column, status_column, updated_at_column, uuid_pk


class Document(Base):
    """Source document registered under one tenant knowledge base."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("idx_documents_kb_status", "kb_id", "status"),
        Index("idx_documents_metadata", "metadata", postgresql_using="gin"),
    )

    id: Mapped[UUID] = uuid_pk()
    kb_id: Mapped[UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(50))
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    minio_path: Mapped[str | None] = mapped_column(String(500))
    file_hash: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(50), server_default="upload")
    source_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = status_column("pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, server_default="{}")
    chunk_count: Mapped[int] = mapped_column(server_default="0")
    created_at = created_at_column()
    updated_at = updated_at_column()
