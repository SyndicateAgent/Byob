from api.app.models import Base


def test_initial_metadata_contains_phase_one_tables() -> None:
    """SQLAlchemy metadata contains the initial platform schema tables."""

    expected_tables = {
        "users",
        "knowledge_bases",
        "documents",
        "chunks",
        "retrieval_logs",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_chunks_table_keeps_source_content_in_postgres() -> None:
    """Chunks table is the source of truth for chunk content."""

    chunks = Base.metadata.tables["chunks"]

    assert "content" in chunks.columns
    assert "qdrant_point_id" in chunks.columns
