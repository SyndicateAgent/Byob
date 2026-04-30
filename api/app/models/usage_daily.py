from datetime import date
from uuid import UUID

from sqlalchemy import BigInteger, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base


class UsageDaily(Base):
    """Daily tenant usage aggregate."""

    __tablename__ = "usage_daily"
    __table_args__ = (UniqueConstraint("tenant_id", "date", name="uq_usage_daily_tenant_date"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    api_calls: Mapped[int] = mapped_column(Integer, server_default="0")
    retrieval_calls: Mapped[int] = mapped_column(Integer, server_default="0")
    documents_uploaded: Mapped[int] = mapped_column(Integer, server_default="0")
    chunks_created: Mapped[int] = mapped_column(Integer, server_default="0")
    embedding_tokens: Mapped[int] = mapped_column(BigInteger, server_default="0")
    storage_bytes: Mapped[int] = mapped_column(BigInteger, server_default="0")
