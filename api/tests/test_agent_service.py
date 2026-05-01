from uuid import uuid4

from mcp.types import CallToolResult, TextContent

from api.app.api.v1.agent import router as agent_router
from api.app.config import Settings
from api.app.main import create_app
from api.app.schemas.agent import AgentAskRequest, AgentSource
from api.app.schemas.retrieval import RetrievalAssetRef, RetrievalDocument
from api.app.services.agent_service import (
    AgentImageInput,
    append_source_asset_section,
    build_extract_answer,
    build_user_message_content,
    chat_completions_url,
    extract_tool_payload,
    select_image_assets_for_llm,
)


def test_agent_route_is_mounted() -> None:
    """The simple MCP-backed Agent route is part of the API surface."""

    app = create_app(Settings(app_env="test", dependency_health_checks_enabled=False))
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert agent_router.prefix == "/agent"
    assert "/api/v1/agent/ask" in paths


def test_chat_completions_url_normalizes_base_urls() -> None:
    """OpenAI-compatible base URLs are normalized consistently."""

    assert chat_completions_url("http://localhost:11434") == "http://localhost:11434/v1/chat/completions"
    assert chat_completions_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"
    assert chat_completions_url("http://localhost:11434/v1/chat/completions") == "http://localhost:11434/v1/chat/completions"


def test_extract_tool_payload_reads_structured_or_text_content() -> None:
    """MCP tool payload parsing supports structuredContent and JSON text fallback."""

    structured = CallToolResult(content=[], structuredContent={"results": []})
    text = CallToolResult(
        content=[TextContent(type="text", text='{"request_id":"req","results":[],"stats":{}}')]
    )

    assert extract_tool_payload(structured) == {"results": []}
    assert extract_tool_payload(text)["request_id"] == "req"


def test_extractive_answer_preserves_rich_markdown_sources() -> None:
    """Fallback answers keep formulas, images, and tables renderable as Markdown."""

    document = RetrievalDocument(id=uuid4(), name="paper.md", metadata={})
    source = AgentSource(
        source_id="S1",
        chunk_id=uuid4(),
        kb_id=uuid4(),
        document=document,
        content="| A | B |\n| - | - |\n| $x^2$ | ![plot](/api/v1/documents/a/assets/plot.png) |",
        score=0.9,
        rerank_score=None,
        chunk_type="text",
        page_num=2,
        metadata={},
    )

    answer = build_extract_answer(
        AgentAskRequest(question="What are the formula and chart?"),
        [source],
        "test fallback",
    )

    assert "$x^2$" in answer
    assert "![plot]" in answer
    assert "| A | B |" in answer


def test_agent_appends_retrieved_assets_when_answer_omits_them() -> None:
    """Agent answers expose retrieved images/files as renderable Markdown attachments."""

    document_id = uuid4()
    asset_id = uuid4()
    document = RetrievalDocument(id=document_id, name="paper.md", metadata={})
    asset = RetrievalAssetRef(
        id=asset_id,
        document_id=document_id,
        kb_id=uuid4(),
        asset_type="image",
        source_path="images/figure.png",
        url=f"/api/v1/documents/{document_id}/assets/{asset_id}",
        content_type="image/png",
        file_size=123,
        metadata={},
    )
    source = AgentSource(
        source_id="S1",
        chunk_id=uuid4(),
        kb_id=uuid4(),
        document=document,
        content="A chart is described here.",
        score=0.9,
        rerank_score=None,
        chunk_type="text",
        page_num=1,
        metadata={},
        assets=[asset],
    )

    answer = append_source_asset_section("## Answer\n\nChart summary. [S1]", [source])

    assert "## Source Assets" in answer
    assert f"![S1 asset 1]({asset.url})" in answer


def test_agent_multimodal_prompt_uses_image_url_content() -> None:
    """Configured image inputs are sent with OpenAI-compatible image_url blocks."""

    document_id = uuid4()
    asset_id = uuid4()
    document = RetrievalDocument(id=document_id, name="paper.md", metadata={})
    asset = RetrievalAssetRef(
        id=asset_id,
        document_id=document_id,
        kb_id=uuid4(),
        asset_type="image",
        source_path="images/figure.png",
        url=f"/api/v1/documents/{document_id}/assets/{asset_id}",
        content_type="image/png",
        file_size=123,
        metadata={},
    )
    source = AgentSource(
        source_id="S1",
        chunk_id=uuid4(),
        kb_id=uuid4(),
        document=document,
        content="A chart is shown below.",
        score=0.9,
        rerank_score=None,
        chunk_type="text",
        page_num=1,
        metadata={},
        assets=[asset],
    )

    selected = select_image_assets_for_llm([source], max_assets=3)
    content = build_user_message_content(
        AgentAskRequest(question="What does the chart show?"),
        [source],
        [
            AgentImageInput(
                source_id="S1",
                asset_id=str(asset_id),
                url=asset.url,
                content_type="image/png",
                data_uri="data:image/png;base64,AAAA",
            )
        ],
        max_chars=12000,
    )

    assert selected == [(source, asset)]
    assert isinstance(content, list)
    assert content[1]["type"] == "image_url"
