import json
from datetime import timedelta
from time import perf_counter
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult
from pydantic import ValidationError

from api.app.config import Settings
from api.app.schemas.agent import (
    AgentAskRequest,
    AgentAskResponse,
    AgentSource,
    AgentStats,
)
from api.app.schemas.retrieval import RetrievalResponse, RetrievalResult

JsonDict = dict[str, Any]
MCP_AGENT_TOOL = "advanced_search_knowledge_base"


class AgentServiceError(RuntimeError):
    """Base error for MCP-backed Agent failures."""


class AgentMcpUnavailableError(AgentServiceError):
    """Raised when the configured MCP service cannot be reached."""


async def answer_with_mcp_agent(
    settings: Settings,
    *,
    request_id: str,
    payload: AgentAskRequest,
) -> AgentAskResponse:
    """Retrieve context through MCP and generate a simple Markdown QA answer."""

    total_started_at = perf_counter()
    retrieval_started_at = perf_counter()
    retrieval_payload, mcp_session_id = await call_mcp_retrieval(settings, payload)
    retrieval_latency_ms = elapsed_ms(retrieval_started_at)

    retrieval_response = parse_retrieval_response(retrieval_payload)
    sources = [
        source_from_result(index, result)
        for index, result in enumerate(retrieval_response.results, 1)
    ]

    generation_started_at = perf_counter()
    answer, model, warnings = await generate_agent_answer(settings, payload, sources)
    generation_latency_ms = elapsed_ms(generation_started_at)

    return AgentAskResponse(
        request_id=request_id,
        answer=answer,
        model=model,
        mcp_tool=MCP_AGENT_TOOL,
        sources=sources,
        stats=AgentStats(
            total_latency_ms=elapsed_ms(total_started_at),
            retrieval_latency_ms=retrieval_latency_ms,
            generation_latency_ms=generation_latency_ms,
            mcp_session_id=mcp_session_id,
        ),
        warnings=warnings,
    )


async def call_mcp_retrieval(
    settings: Settings,
    payload: AgentAskRequest,
) -> tuple[JsonDict, str | None]:
    """Call BYOB's Streamable HTTP MCP retrieval tool."""

    arguments: JsonDict = {
        "query": payload.question,
        "top_k": payload.top_k,
        "query_rewrite": payload.options.query_rewrite,
        "hyde": payload.options.hyde,
        "decompose": payload.options.decompose,
        "max_sub_queries": payload.options.max_sub_queries,
        "enable_rerank": payload.options.enable_rerank,
        "include_metadata": True,
        "include_parent_context": payload.options.include_parent_context,
    }
    if payload.kb_ids is not None:
        arguments["kb_ids"] = [str(kb_id) for kb_id in payload.kb_ids]
    if payload.options.score_threshold is not None:
        arguments["score_threshold"] = payload.options.score_threshold

    try:
        async with streamablehttp_client(
            str(settings.mcp_server_url),
            timeout=settings.mcp_client_timeout_seconds,
            sse_read_timeout=settings.mcp_client_timeout_seconds,
        ) as (read_stream, write_stream, get_session_id):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    MCP_AGENT_TOOL,
                    arguments=arguments,
                    read_timeout_seconds=timedelta(seconds=settings.mcp_client_timeout_seconds),
                )
                return extract_tool_payload(result), get_session_id()
    except AgentServiceError:
        raise
    except Exception as exc:
        raise AgentMcpUnavailableError(
            "MCP service is unavailable. Start it with: "
            "uv run python -m api.app.mcp_server --transport streamable-http "
            "--host 127.0.0.1 --port 8010"
        ) from exc


def extract_tool_payload(result: CallToolResult) -> JsonDict:
    """Return structured JSON data from an MCP tool result."""

    if result.isError:
        message = "MCP tool returned an error"
        text_parts = [str(getattr(item, "text", "")) for item in result.content]
        details = "\n".join(part for part in text_parts if part)
        raise AgentServiceError(f"{message}: {details}" if details else message)

    if result.structuredContent is not None:
        return result.structuredContent

    for content_item in result.content:
        text = getattr(content_item, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed

    raise AgentServiceError("MCP tool did not return structured JSON content")


def parse_retrieval_response(payload: JsonDict) -> RetrievalResponse:
    """Validate the retrieval-shaped subset returned by the MCP tool."""

    retrieval_payload = {
        "request_id": payload.get("request_id"),
        "results": payload.get("results", []),
        "stats": payload.get("stats", {}),
    }
    try:
        return RetrievalResponse.model_validate(retrieval_payload)
    except ValidationError as exc:
        raise AgentServiceError("MCP retrieval response was not valid") from exc


def source_from_result(index: int, result: RetrievalResult) -> AgentSource:
    """Convert a retrieval hit into an Agent source item."""

    return AgentSource(
        source_id=f"S{index}",
        chunk_id=result.chunk_id,
        kb_id=result.kb_id,
        document=result.document,
        content=result.content,
        score=result.score,
        rerank_score=result.rerank_score,
        chunk_type=result.chunk_type,
        page_num=result.page_num,
        metadata=result.metadata,
    )


async def generate_agent_answer(
    settings: Settings,
    payload: AgentAskRequest,
    sources: list[AgentSource],
) -> tuple[str, str | None, list[str]]:
    """Generate a Markdown answer with an optional OpenAI-compatible chat model."""

    warnings: list[str] = []
    if not payload.use_llm:
        return (
            build_extract_answer(
                payload,
                sources,
                "LLM generation is disabled for this request.",
            ),
            None,
            warnings,
        )

    if settings.agent_llm_endpoint_url is None:
        warnings.append(
            "AGENT_LLM_ENDPOINT_URL is not configured; returned an extractive MCP answer."
        )
        return build_extract_answer(payload, sources, warnings[0]), None, warnings

    if not sources:
        return no_source_answer(payload.question), settings.agent_llm_model, warnings

    try:
        answer = await call_chat_completion(settings, payload, sources)
    except Exception as exc:
        warnings.append(f"LLM generation failed; returned an extractive MCP answer. Detail: {exc}")
        return build_extract_answer(payload, sources, warnings[0]), None, warnings

    return answer, settings.agent_llm_model, warnings


async def call_chat_completion(
    settings: Settings,
    payload: AgentAskRequest,
    sources: list[AgentSource],
) -> str:
    """Call an OpenAI-compatible chat completions endpoint."""

    headers = {"Content-Type": "application/json"}
    if settings.agent_llm_api_key is not None:
        headers["Authorization"] = f"Bearer {settings.agent_llm_api_key.get_secret_value()}"

    request_body = {
        "model": settings.agent_llm_model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are BYOB's simple RAG QA Agent. Answer in the user's language. "
                    "Use only the provided MCP source chunks. Return Markdown. Preserve useful "
                    "LaTeX formulas, Markdown tables, HTML snippets, and Markdown image syntax "
                    "from the sources when they help answer the question. Cite sources as [S1], "
                    "[S2]. "
                    "If the sources are insufficient, say so clearly."
                ),
            },
            {
                "role": "user",
                "content": build_llm_prompt(payload, sources, settings.agent_max_context_chars),
            },
        ],
    }
    async with httpx.AsyncClient(timeout=settings.agent_llm_timeout_seconds) as client:
        response = await client.post(
            chat_completions_url(str(settings.agent_llm_endpoint_url)),
            headers=headers,
            json=request_body,
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise AgentServiceError("LLM returned an empty answer")
    return content.strip()


def chat_completions_url(endpoint_url: str) -> str:
    """Normalize an OpenAI-compatible endpoint into /chat/completions."""

    normalized = endpoint_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def build_llm_prompt(payload: AgentAskRequest, sources: list[AgentSource], max_chars: int) -> str:
    """Build the user prompt containing the question and bounded source context."""

    context = build_source_context(sources, max_chars)
    return f"Question:\n{payload.question.strip()}\n\nMCP source chunks:\n{context}"


def build_source_context(sources: list[AgentSource], max_chars: int) -> str:
    """Serialize source chunks for the chat model within a character budget."""

    remaining_chars = max(1000, max_chars)
    blocks: list[str] = []
    for source in sources:
        heading = source_heading(source)
        content = source.content.strip()
        available_chars = remaining_chars - len(heading) - 16
        if available_chars <= 0:
            break
        if len(content) > available_chars:
            content = f"{content[:available_chars].rstrip()}\n...[truncated]"
        block = f"{heading}\n{content}"
        blocks.append(block)
        remaining_chars -= len(block)
    return "\n\n".join(blocks) if blocks else "No source chunks were retrieved."


def source_heading(source: AgentSource) -> str:
    """Return a compact source heading for prompts and extractive answers."""

    page = f", page {source.page_num}" if source.page_num is not None else ""
    return (
        f"[{source.source_id}] document={source.document.name}{page}, "
        f"chunk_id={source.chunk_id}, score={source.score:.4f}"
    )


def build_extract_answer(payload: AgentAskRequest, sources: list[AgentSource], reason: str) -> str:
    """Build a Markdown answer directly from MCP source chunks."""

    if not sources:
        return no_source_answer(payload.question)

    excerpts = []
    for source in sources[: min(3, len(sources))]:
        excerpts.append(
            f"### {source.source_id} - {source.document.name}\n\n"
            f"{source.content.strip()}"
        )
    source_lines = [
        f"- [{source.source_id}] `{source.document.name}` - "
        f"chunk `{source.chunk_id}` - score `{source.score:.4f}`"
        for source in sources
    ]
    return (
        "## Answer\n\n"
        f"{reason}\n\n"
        "These are the highest-scoring MCP source chunks for checking RAG recall.\n\n"
        f"{chr(10).join(excerpts)}\n\n"
        "## Sources\n\n"
        f"{chr(10).join(source_lines)}"
    )


def no_source_answer(question: str) -> str:
    """Return a Markdown answer for empty retrieval results."""

    return (
        "## Answer\n\n"
        "MCP retrieval returned no usable sources, so this question cannot be "
        "answered from the current knowledge bases.\n\n"
        "## Question\n\n"
        f"{question.strip()}"
    )


def elapsed_ms(started_at: float) -> int:
    """Return elapsed milliseconds since a perf counter timestamp."""

    return int((perf_counter() - started_at) * 1000)
