from uuid import UUID

from sqlalchemy import BigInteger, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base
from api.app.models.types import created_at_column


class RetrievalLog(Base):
    """Audit and quality log for retrieval requests."""

    __tablename__ = "retrieval_logs"
    __table_args__ = (
        Index("idx_retrieval_logs_request", "request_id"),
        Index("idx_retrieval_logs_tenant_time", "tenant_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[UUID] = mapped_column(nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    api_key_id: Mapped[UUID | None] = mapped_column()
    kb_ids: Mapped[list[UUID] | None] = mapped_column(ARRAY(item_type=PG_UUID(as_uuid=True)))
    query: Mapped[str | None] = mapped_column(Text)
    rewritten_query: Mapped[str | None] = mapped_column(Text)
    sub_queries: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    retrieved_chunk_ids: Mapped[list[UUID] | None] = mapped_column(
        ARRAY(item_type=PG_UUID(as_uuid=True))
    )
    rerank_scores: Mapped[list[float] | None] = mapped_column(ARRAY(Float))
    total_latency_ms: Mapped[int | None] = mapped_column(Integer)
    stage_latencies: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    feedback: Mapped[str | None] = mapped_column(String(20))
    feedback_detail: Mapped[str | None] = mapped_column(Text)
    created_at = created_at_column()
