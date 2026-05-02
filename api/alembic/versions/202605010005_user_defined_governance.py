"""Make document governance source taxonomy user-defined.

Revision ID: 202605010005
Revises: 202605010004
Create Date: 2026-05-01 00:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202605010005"
down_revision: str | None = "202605010004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove fixed governance defaults and widen user-defined source labels."""

    op.alter_column(
        "documents",
        "governance_source_type",
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "documents",
        "authority_level",
        existing_type=sa.Integer(),
        server_default=None,
        existing_nullable=False,
    )
    op.alter_column(
        "document_versions",
        "governance_source_type",
        existing_type=sa.String(length=50),
        type_=sa.String(length=100),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Restore legacy governance defaults and source label width."""

    op.alter_column(
        "document_versions",
        "governance_source_type",
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        existing_nullable=False,
    )
    op.alter_column(
        "documents",
        "authority_level",
        existing_type=sa.Integer(),
        server_default="3",
        existing_nullable=False,
    )
    op.alter_column(
        "documents",
        "governance_source_type",
        existing_type=sa.String(length=100),
        type_=sa.String(length=50),
        server_default="internal_sop",
        existing_nullable=False,
    )
