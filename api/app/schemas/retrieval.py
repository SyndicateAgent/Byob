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


class RetrievalAssetRef(BaseModel):
    """Binary asset referenced by a retrieved source chunk."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_id: UUID
    kb_id: UUID
    asset_type: str
    source_path: str
    url: str
    content_type: str
    file_size: int
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
    assets: list[RetrievalAssetRef] = Field(default_factory=list)
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


class RetrievalEnhancements(BaseModel):
    """Advanced retrieval enhancement toggles."""

    model_config = ConfigDict(extra="forbid")

    query_rewrite: bool = False
    hyde: bool = False
    decompose: bool = False
    max_sub_queries: int = Field(default=3, ge=1, le=8)


class AdvancedRetrievalRequest(RetrievalRequest):
    """Advanced retrieval request with query enhancement controls."""

    enhancements: RetrievalEnhancements = Field(default_factory=RetrievalEnhancements)


class EnhancementInfo(BaseModel):
    """Details about generated query enhancements."""

    model_config = ConfigDict(extra="forbid")

    rewritten_query: str | None
    sub_queries: list[str]
    hyde_doc: str | None


class AdvancedRetrievalResponse(RetrievalResponse):
    """Advanced retrieval response including enhancement metadata."""

    enhancement_info: EnhancementInfo


class MultiSearchRequest(BaseModel):
    """Batch retrieval request for multiple queries."""

    model_config = ConfigDict(extra="forbid")

    kb_ids: list[UUID] = Field(min_length=1)
    queries: list[str] = Field(min_length=1, max_length=20)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, object] = Field(default_factory=dict)
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)


class MultiSearchItem(BaseModel):
    """One query result inside a batch retrieval response."""

    model_config = ConfigDict(extra="forbid")

    query: str
    response: RetrievalResponse


class MultiSearchResponse(BaseModel):
    """Batch retrieval response."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    data: list[MultiSearchItem]


class RerankRequest(BaseModel):
    """Standalone rerank request."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1, max_length=100)


class RerankResult(BaseModel):
    """One reranked document score."""

    model_config = ConfigDict(extra="forbid")

    index: int
    document: str
    score: float


class RerankResponse(BaseModel):
    """Standalone rerank response."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    results: list[RerankResult]


class EmbedRequest(BaseModel):
    """Standalone embedding request."""

    model_config = ConfigDict(extra="forbid")

    input: list[str] = Field(min_length=1, max_length=100)


class EmbedResponse(BaseModel):
    """Standalone embedding response."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    model: str
    data: list[list[float]]


class FeedbackRequest(BaseModel):
    """Feedback for a retrieval request."""

    model_config = ConfigDict(extra="forbid")

    feedback: str = Field(pattern="^(good|bad)$")
    detail: str | None = None


class FeedbackResponse(BaseModel):
    """Feedback update response."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    updated: bool
