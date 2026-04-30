from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base
from api.app.models.types import created_at_column, uuid_pk


class Chunk(Base):
    """Persisted source-of-truth text chunk stored outside Qdrant payloads."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index("idx_chunks_document", "document_id"),
        Index("idx_chunks_kb", "kb_id"),
        Index("idx_chunks_qdrant_point", "qdrant_point_id"),
    )

    id: Mapped[UUID] = uuid_pk()
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    kb_id: Mapped[UUID] = mapped_column(nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    chunk_type: Mapped[str] = mapped_column(String(20), server_default="text")
    parent_chunk_id: Mapped[UUID | None] = mapped_column(ForeignKey("chunks.id"))
    page_num: Mapped[int | None] = mapped_column(Integer)
    bbox: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    qdrant_point_id: Mapped[UUID | None] = mapped_column()
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, server_default="{}")
    created_at = created_at_column()
