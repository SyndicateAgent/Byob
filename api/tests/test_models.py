from api.app.models import Base


def test_initial_metadata_contains_phase_one_tables() -> None:
    """SQLAlchemy metadata contains the initial platform schema tables."""

    expected_tables = {
        "users",
        "knowledge_bases",
        "documents",
        "document_versions",
        "document_audit_logs",
        "chunks",
        "retrieval_logs",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_chunks_table_keeps_source_content_in_postgres() -> None:
    """Chunks table is the source of truth for chunk content."""

    chunks = Base.metadata.tables["chunks"]

    assert "content" in chunks.columns
    assert "qdrant_point_id" in chunks.columns


def test_documents_table_contains_governance_columns() -> None:
    """Documents carry the governance labels used by Agent retrieval."""

    documents = Base.metadata.tables["documents"]

    assert "governance_source_type" in documents.columns
    assert "authority_level" in documents.columns
    assert "review_status" in documents.columns
    assert "current_version" in documents.columns
