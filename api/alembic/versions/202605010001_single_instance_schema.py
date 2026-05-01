"""Remove SaaS-only tenant, API key, and usage schema.

Revision ID: 202605010001
Revises: 202604290001
Create Date: 2026-05-01 00:01:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202605010001"
down_revision: str | None = "202604290001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Convert the metadata store to a single self-hosted instance schema."""

    op.execute("DROP TABLE IF EXISTS usage_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS api_keys CASCADE")

    op.execute("DROP INDEX IF EXISTS idx_retrieval_logs_tenant_time")
    op.execute("ALTER TABLE retrieval_logs DROP COLUMN IF EXISTS tenant_id")
    op.execute("ALTER TABLE retrieval_logs DROP COLUMN IF EXISTS api_key_id")

    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS tenant_id")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS tenant_id")

    op.execute(
        "ALTER TABLE knowledge_bases "
        "DROP CONSTRAINT IF EXISTS fk_knowledge_bases_tenant_id_tenants"
    )
    op.execute(
        "ALTER TABLE knowledge_bases "
        "DROP CONSTRAINT IF EXISTS uq_knowledge_bases_tenant_name"
    )
    op.execute("ALTER TABLE knowledge_bases DROP COLUMN IF EXISTS tenant_id")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_knowledge_bases_name'
            ) THEN
                ALTER TABLE knowledge_bases
                ADD CONSTRAINT uq_knowledge_bases_name UNIQUE (name);
            END IF;
        END
        $$;
        """
    )

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_tenant_id_tenants")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS tenant_id")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE")


def downgrade() -> None:
    """The single-instance conversion is not losslessly reversible."""

    raise NotImplementedError("Downgrading from the single-instance schema is not supported.")
