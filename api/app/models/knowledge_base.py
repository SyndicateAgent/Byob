from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base
from api.app.models.types import (
    created_at_column,
    jsonb_default,
    status_column,
    updated_at_column,
    uuid_pk,
)


class KnowledgeBase(Base):
    """Tenant-scoped knowledge base with its own Qdrant collection."""

    __tablename__ = "knowledge_bases"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_knowledge_bases_tenant_name"),)

    id: Mapped[UUID] = uuid_pk()
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    embedding_model: Mapped[str] = mapped_column(String(100), server_default="BAAI/bge-m3")
    embedding_dim: Mapped[int] = mapped_column(Integer, server_default="1024")
    chunk_size: Mapped[int] = mapped_column(Integer, server_default="512")
    chunk_overlap: Mapped[int] = mapped_column(Integer, server_default="50")
    retrieval_config: Mapped[dict[str, object]] = jsonb_default()
    qdrant_collection: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = status_column()
    document_count: Mapped[int] = mapped_column(Integer, server_default="0")
    chunk_count: Mapped[int] = mapped_column(Integer, server_default="0")
    created_at = created_at_column()
    updated_at = updated_at_column()
