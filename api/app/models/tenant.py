from uuid import UUID

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from api.app.models.base import Base
from api.app.models.types import created_at_column, jsonb_default, status_column, uuid_pk


class Tenant(Base):
    """Tenant account for the multi-tenant SaaS hierarchy."""

    __tablename__ = "tenants"

    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), server_default="free")
    quota: Mapped[dict[str, object]] = jsonb_default()
    config: Mapped[dict[str, object]] = jsonb_default()
    status: Mapped[str] = status_column()
    created_at = created_at_column()
