"""Add document deduplication lookup indexes.

Revision ID: 202605010003
Revises: 202605010002
Create Date: 2026-05-01 00:03:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202605010003"
down_revision: str | None = "202605010002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add indexes used by same-name and same-hash import deduplication."""

    op.create_index("idx_documents_kb_name", "documents", ["kb_id", "name"])
    op.create_index("idx_documents_kb_file_hash", "documents", ["kb_id", "file_hash"])


def downgrade() -> None:
    """Drop document deduplication lookup indexes."""

    op.drop_index("idx_documents_kb_file_hash", table_name="documents")
    op.drop_index("idx_documents_kb_name", table_name="documents")