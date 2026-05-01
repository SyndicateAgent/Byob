from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base
from api.app.models.types import created_at_column, uuid_pk


class DocumentAsset(Base):
    """Binary asset extracted from a parsed source document."""

    __tablename__ = "document_assets"
    __table_args__ = (
        Index("idx_document_assets_document", "document_id"),
        Index("idx_document_assets_kb", "kb_id"),
        Index("idx_document_assets_source_path", "document_id", "source_path"),
    )

    id: Mapped[UUID] = uuid_pk()
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    kb_id: Mapped[UUID] = mapped_column(nullable=False)
    asset_index: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), server_default="image")
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    minio_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_: Mapped[dict[str, object]] = mapped_column("metadata", JSONB, server_default="{}")
    created_at = created_at_column()