from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base
from api.app.models.types import created_at_column


class DocumentAuditLog(Base):
    """Append-only audit log for document governance and lifecycle changes."""

    __tablename__ = "document_audit_logs"
    __table_args__ = (
        Index("idx_document_audit_logs_document", "document_id"),
        Index("idx_document_audit_logs_kb_time", "kb_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    kb_id: Mapped[UUID | None] = mapped_column(nullable=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    after: Mapped[dict[str, object]] = mapped_column(JSONB, server_default="{}")
    created_at = created_at_column()