"""Create initial platform schema.

Revision ID: 202604290001
Revises:
Create Date: 2026-04-29 00:01:00
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202604290001"
down_revision: str | None = None
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


def jsonb_column(name: str, default: str = "{}") -> sa.Column[object]:
    """Return a JSONB column with a server-side default."""

    return sa.Column(
        name,
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=default,
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
    """Create PostgreSQL tables, indexes, and UUID extension."""

    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.create_table(
        "tenants",
        uuid_pk_column(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plan", sa.String(length=50), server_default="free", nullable=False),
        jsonb_column("quota"),
        jsonb_column("config"),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        created_timestamp(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
    )
    op.create_table(
        "users",
        uuid_pk_column(),
        uuid_column("tenant_id", nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), server_default="viewer", nullable=False),
        created_timestamp(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_users_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "api_keys",
        uuid_pk_column(),
        uuid_column("tenant_id", nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("key_prefix", sa.String(length=20), nullable=True),
        jsonb_column("scopes", "[]"),
        sa.Column("rate_limit", sa.Integer(), server_default="100", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), server_default="false", nullable=False),
        created_timestamp(),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_api_keys_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )
    op.create_index("idx_api_keys_hash", "api_keys", ["key_hash"])
    op.create_index("idx_api_keys_tenant", "api_keys", ["tenant_id"])
    op.create_table(
        "knowledge_bases",
        uuid_pk_column(),
        uuid_column("tenant_id", nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "embedding_model", sa.String(length=100), server_default="bge-m3", nullable=False
        ),
        sa.Column("embedding_dim", sa.Integer(), server_default="1024", nullable=False),
        sa.Column("chunk_size", sa.Integer(), server_default="512", nullable=False),
        sa.Column("chunk_overlap", sa.Integer(), server_default="50", nullable=False),
        jsonb_column("retrieval_config"),
        sa.Column("qdrant_collection", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("document_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        created_timestamp(),
        created_timestamp("updated_at"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_knowledge_bases_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_bases")),
        sa.UniqueConstraint("qdrant_collection", name=op.f("uq_knowledge_bases_qdrant_collection")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_knowledge_bases_tenant_name"),
    )
    op.create_table(
        "documents",
        uuid_pk_column(),
        uuid_column("kb_id", nullable=False),
        uuid_column("tenant_id", nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("file_type", sa.String(length=50), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("minio_path", sa.String(length=500), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("source_type", sa.String(length=50), server_default="upload", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        jsonb_column("metadata"),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        created_timestamp(),
        created_timestamp("updated_at"),
        sa.ForeignKeyConstraint(
            ["kb_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_documents_kb_id_knowledge_bases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index("idx_documents_kb_status", "documents", ["kb_id", "status"])
    op.create_index("idx_documents_metadata", "documents", ["metadata"], postgresql_using="gin")
    op.create_table(
        "chunks",
        uuid_pk_column(),
        uuid_column("document_id", nullable=False),
        uuid_column("kb_id", nullable=False),
        uuid_column("tenant_id", nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("chunk_type", sa.String(length=20), server_default="text", nullable=False),
        uuid_column("parent_chunk_id", nullable=True),
        sa.Column("page_num", sa.Integer(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        uuid_column("qdrant_point_id", nullable=True),
        jsonb_column("metadata"),
        created_timestamp(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_chunk_id"], ["chunks.id"], name=op.f("fk_chunks_parent_chunk_id_chunks")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    op.create_index("idx_chunks_document", "chunks", ["document_id"])
    op.create_index("idx_chunks_kb", "chunks", ["kb_id"])
    op.create_index("idx_chunks_qdrant_point", "chunks", ["qdrant_point_id"])
    op.create_table(
        "retrieval_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        uuid_column("request_id", nullable=False),
        uuid_column("tenant_id", nullable=False),
        uuid_column("api_key_id", nullable=True),
        sa.Column("kb_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column("sub_queries", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "retrieved_chunk_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True
        ),
        sa.Column("rerank_scores", postgresql.ARRAY(sa.Float()), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column("stage_latencies", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("feedback", sa.String(length=20), nullable=True),
        sa.Column("feedback_detail", sa.Text(), nullable=True),
        created_timestamp(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_logs")),
    )
    op.create_index("idx_retrieval_logs_request", "retrieval_logs", ["request_id"])
    op.create_index(
        "idx_retrieval_logs_tenant_time",
        "retrieval_logs",
        ["tenant_id", sa.text("created_at DESC")],
    )
    op.create_table(
        "usage_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        uuid_column("tenant_id", nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("api_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retrieval_calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("documents_uploaded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunks_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("storage_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_daily")),
        sa.UniqueConstraint("tenant_id", "date", name="uq_usage_daily_tenant_date"),
    )


def downgrade() -> None:
    """Drop PostgreSQL tables and indexes created by this migration."""

    op.drop_table("usage_daily")
    op.drop_index("idx_retrieval_logs_tenant_time", table_name="retrieval_logs")
    op.drop_index("idx_retrieval_logs_request", table_name="retrieval_logs")
    op.drop_table("retrieval_logs")
    op.drop_index("idx_chunks_qdrant_point", table_name="chunks")
    op.drop_index("idx_chunks_kb", table_name="chunks")
    op.drop_index("idx_chunks_document", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("idx_documents_metadata", table_name="documents")
    op.drop_index("idx_documents_kb_status", table_name="documents")
    op.drop_table("documents")
    op.drop_table("knowledge_bases")
    op.drop_index("idx_api_keys_tenant", table_name="api_keys")
    op.drop_index("idx_api_keys_hash", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("tenants")
