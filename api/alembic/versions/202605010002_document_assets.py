"""Add parsed document assets.

Revision ID: 202605010002
Revises: 202605010001
Create Date: 2026-05-01 00:02:00
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202605010002"
down_revision: str | None = "202605010001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_column(name: str, *, nullable: bool) -> sa.Column[UUID]:
    """Return a PostgreSQL UUID column."""

    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def uuid_pk_column() -> sa.Column[UUID]:
    """Return a server-generated UUID primary key column."""

    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def created_timestamp(name: str = "created_at") -> sa.Column[datetime]:
    """Return a timezone-aware timestamp with a now() default."""

    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    """Create parsed document asset metadata table."""

    op.create_table(
        "document_assets",
        uuid_pk_column(),
        uuid_column("document_id", nullable=False),
        uuid_column("kb_id", nullable=False),
        sa.Column("asset_index", sa.Integer(), nullable=False),
        sa.Column("asset_type", sa.String(length=50), server_default="image", nullable=False),
        sa.Column("source_path", sa.String(length=1000), nullable=False),
        sa.Column("minio_path", sa.String(length=1000), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        created_timestamp(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_assets_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_assets")),
    )
    op.create_index("idx_document_assets_document", "document_assets", ["document_id"])
    op.create_index("idx_document_assets_kb", "document_assets", ["kb_id"])
    op.create_index(
        "idx_document_assets_source_path",
        "document_assets",
        ["document_id", "source_path"],
    )


def downgrade() -> None:
    """Drop parsed document asset metadata table."""

    op.drop_index("idx_document_assets_source_path", table_name="document_assets")
    op.drop_index("idx_document_assets_kb", table_name="document_assets")
    op.drop_index("idx_document_assets_document", table_name="document_assets")
    op.drop_table("document_assets")