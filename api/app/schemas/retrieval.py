from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RetrievalOptions(BaseModel):
    """Optional retrieval behavior toggles."""

    model_config = ConfigDict(extra="forbid")

    enable_rerank: bool = True
    include_parent_context: bool = False
    include_metadata: bool = True
    score_threshold: float | None = Field(default=None, ge=0)


class RetrievalRequest(BaseModel):
    """Standard hybrid retrieval request."""

    model_config = ConfigDict(extra="forbid")

    kb_ids: list[UUID] = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, object] = Field(default_factory=dict)
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)


class RetrievalDocument(BaseModel):
    """Document metadata included with a retrieval hit."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    metadata: dict[str, object]


class ParentChunkContext(BaseModel):
    """Optional parent chunk context."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    content: str


class RetrievalResult(BaseModel):
    """One retrieval search result."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    content: str
    score: float
    rerank_score: float | None
    document: RetrievalDocument
    kb_id: UUID
    chunk_type: str
    page_num: int | None
    bbox: dict[str, object] | None
    metadata: dict[str, object]
    parent_chunk: ParentChunkContext | None = None


class RetrievalStats(BaseModel):
    """Timings and candidate counts for retrieval."""

    model_config = ConfigDict(extra="forbid")

    total_latency_ms: int
    stages: dict[str, int]
    total_candidates: int
    after_fusion: int
    after_rerank: int
    cache_hit: bool = False


class RetrievalResponse(BaseModel):
    """Standard retrieval response."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    results: list[RetrievalResult]
    stats: RetrievalStats
