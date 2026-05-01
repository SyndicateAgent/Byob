from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.app.schemas.retrieval import RetrievalAssetRef, RetrievalDocument


class AgentRetrievalOptions(BaseModel):
    """Retrieval controls used by the simple MCP-backed QA Agent."""

    model_config = ConfigDict(extra="forbid")

    query_rewrite: bool = True
    hyde: bool = False
    decompose: bool = False
    max_sub_queries: int = Field(default=3, ge=1, le=8)
    enable_rerank: bool = True
    include_parent_context: bool = True
    score_threshold: float | None = Field(default=None, ge=0)


class AgentAskRequest(BaseModel):
    """Question submitted to the MCP-backed QA Agent."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    kb_ids: list[UUID] | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    use_llm: bool = True
    options: AgentRetrievalOptions = Field(default_factory=AgentRetrievalOptions)


class AgentSource(BaseModel):
    """One source chunk used by the QA Agent."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    chunk_id: UUID
    kb_id: UUID
    document: RetrievalDocument
    content: str
    score: float
    rerank_score: float | None
    chunk_type: str
    page_num: int | None
    metadata: dict[str, object]
    assets: list[RetrievalAssetRef] = Field(default_factory=list)


class AgentStats(BaseModel):
    """Timings and MCP details for one Agent request."""

    model_config = ConfigDict(extra="forbid")
    total_latency_ms: int
    retrieval_latency_ms: int
    generation_latency_ms: int
    mcp_session_id: str | None = None


class AgentAskResponse(BaseModel):
    """Markdown answer plus the MCP source chunks used to produce it."""

    model_config = ConfigDict(extra="forbid")
    request_id: str
    answer: str
    answer_format: Literal["markdown"] = "markdown"
    model: str | None
    mcp_tool: str
    sources: list[AgentSource]
    stats: AgentStats
    warnings: list[str] = Field(default_factory=list)
