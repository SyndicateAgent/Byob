from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

type UuidPk = Mapped[UUID]
type Timestamp = Mapped[datetime]


def uuid_pk() -> UuidPk:
    """Return a UUID primary key column with server-side generation."""

    return mapped_column(primary_key=True, server_default=func.gen_random_uuid())


def created_at_column() -> Timestamp:
    """Return a timezone-aware created_at column."""

    return mapped_column(DateTime(timezone=True), server_default=func.now())


def updated_at_column() -> Timestamp:
    """Return a timezone-aware updated_at column."""

    return mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def jsonb_default() -> Mapped[dict[str, object]]:
    """Return a JSONB object column with a database-side empty object default."""

    return mapped_column(JSONB, server_default="{}")


def status_column(default: str = "active") -> Mapped[str]:
    """Return a status column with a stable string default."""

    return mapped_column(String(20), server_default=default)
