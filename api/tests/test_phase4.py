from uuid import uuid4

from qdrant_client.http import models

from api.app.api.v1.retrieval import build_cache_key
from api.app.config import Settings
from api.app.main import create_app
from api.app.schemas.retrieval import RetrievalRequest
from api.app.services.retrieval_service import Candidate, build_qdrant_filter, rrf_fuse


def test_phase_four_search_route_is_mounted() -> None:
    """Standard retrieval route is registered under /api/v1."""

    app = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v1/retrieval/search" in paths


def test_rrf_fuse_combines_dense_and_sparse_rankings() -> None:
    """RRF rewards candidates appearing in multiple rankings."""

    first = uuid4()
    second = uuid4()
    third = uuid4()

    fused = rrf_fuse(
        [
            [Candidate(first, 0.9), Candidate(second, 0.8)],
            [Candidate(second, 2.0), Candidate(third, 1.0)],
        ]
    )

    assert fused[0].chunk_id == second
    assert {candidate.chunk_id for candidate in fused} == {first, second, third}


def test_qdrant_filter_always_includes_tenant() -> None:
    """Qdrant filters are always scoped to authenticated tenant context."""

    tenant_id = uuid4()
    query_filter = build_qdrant_filter(
        tenant_id,
        {"chunk_type": "text", "tags": ["manual"]},
    )

    assert isinstance(query_filter.must, list)
    assert len(query_filter.must) == 3
    assert all(isinstance(condition, models.FieldCondition) for condition in query_filter.must)


def test_retrieval_cache_key_is_tenant_scoped() -> None:
    """Retrieval cache keys include tenant identity."""

    payload = RetrievalRequest(kb_ids=[uuid4()], query="hello")
    tenant_a = uuid4()
    tenant_b = uuid4()

    assert build_cache_key(tenant_a, payload) != build_cache_key(tenant_b, payload)
