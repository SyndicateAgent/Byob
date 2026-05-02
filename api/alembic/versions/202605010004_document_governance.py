"""Add document governance, versions, and audit logs.

Revision ID: 202605010004
Revises: 202605010003
Create Date: 2026-05-01 00:04:00
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "202605010004"
down_revision: str | None = "202605010003"
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
    """Add governance metadata and immutable change history."""

    op.add_column(
        "documents",
        sa.Column(
            "governance_source_type",
            sa.String(length=50),
            server_default="internal_sop",
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("authority_level", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "documents",
        sa.Column(
            "review_status",
            sa.String(length=20),
            server_default="published",
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_index("idx_documents_kb_review_status", "documents", ["kb_id", "review_status"])
    op.create_index("idx_documents_kb_authority", "documents", ["kb_id", "authority_level"])

    op.create_table(
        "document_versions",
        uuid_pk_column(),
        uuid_column("document_id", nullable=False),
        uuid_column("kb_id", nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("file_type", sa.String(length=50), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("minio_path", sa.String(length=500), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("governance_source_type", sa.String(length=50), nullable=False),
        sa.Column("authority_level", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        jsonb_column("metadata"),
        sa.Column("change_summary", sa.Text(), nullable=True),
        uuid_column("created_by_id", nullable=True),
        sa.Column("created_by_email", sa.String(length=255), nullable=True),
        created_timestamp(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_versions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_document_versions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_versions_document_number",
        ),
    )
    op.create_index("idx_document_versions_document", "document_versions", ["document_id"])
    op.create_index("idx_document_versions_kb", "document_versions", ["kb_id"])

    op.execute(
        """
        INSERT INTO document_versions (
            id, document_id, kb_id, version_number, name, file_type, file_size,
            minio_path, file_hash, source_type, source_url, governance_source_type,
            authority_level, review_status, metadata, change_summary, created_at
        )
        SELECT
            gen_random_uuid(), id, kb_id, 1, name, file_type, file_size,
            minio_path, file_hash, source_type, source_url, governance_source_type,
            authority_level, review_status, metadata, 'Initial migrated version', created_at
        FROM documents
        """
    )

    op.create_table(
        "document_audit_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        uuid_column("document_id", nullable=True),
        uuid_column("kb_id", nullable=True),
        uuid_column("actor_user_id", nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        jsonb_column("before"),
        jsonb_column("after"),
        created_timestamp(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_audit_logs_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_document_audit_logs_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_audit_logs")),
    )
    op.create_index("idx_document_audit_logs_document", "document_audit_logs", ["document_id"])
    op.create_index(
        "idx_document_audit_logs_kb_time",
        "document_audit_logs",
        ["kb_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    """Remove document governance metadata and history tables."""

    op.drop_index("idx_document_audit_logs_kb_time", table_name="document_audit_logs")
    op.drop_index("idx_document_audit_logs_document", table_name="document_audit_logs")
    op.drop_table("document_audit_logs")
    op.drop_index("idx_document_versions_kb", table_name="document_versions")
    op.drop_index("idx_document_versions_document", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("idx_documents_kb_authority", table_name="documents")
    op.drop_index("idx_documents_kb_review_status", table_name="documents")
    op.drop_column("documents", "current_version")
    op.drop_column("documents", "review_status")
    op.drop_column("documents", "authority_level")
    op.drop_column("documents", "governance_source_type")