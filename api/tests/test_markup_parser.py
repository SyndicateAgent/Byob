import base64

from api.app.services.ingestion_service import build_ingestion_chunks
from workers.parsers.base import ParsedChunk
from workers.parsers.registry import parse_document_bytes


def image_data_uri(content: bytes, content_type: str = "image/png") -> str:
    """Return a compact base64 image data URI for parser tests."""

    return f"data:{content_type};base64,{base64.b64encode(content).decode('ascii')}"


def test_markdown_parser_emits_structure_and_extracts_data_uri_image() -> None:
    """Markdown files should produce structured chunks and extracted image assets."""

    image_uri = image_data_uri(b"markdown image bytes")
    parsed = parse_document_bytes(
        f"""# Incident Report

Intro paragraph with context.

![Revenue chart]({image_uri})

| Metric | Value |
| --- | --- |
| ARR | 42 |
""".encode(),
        "md",
        source_name="incident report.md",
    )

    assert parsed.metadata == {
        "parser": "markup",
        "file_type": "md",
        "markup_format": "markdown",
        "embedded_image_count": 1,
    }
    assert image_uri not in parsed.text
    assert "![Revenue chart](assets/incident_report-1.png)" in parsed.text
    assert [chunk.chunk_type for chunk in parsed.chunks] == [
        "text",
        "text",
        "image",
        "table",
    ]
    assert parsed.chunks[0].metadata["heading_level"] == 1
    assert parsed.chunks[1].metadata["title_path"] == ["Incident Report"]
    assert parsed.chunks[2] == ParsedChunk(
        content="![Revenue chart](assets/incident_report-1.png)",
        chunk_type="image",
        metadata={
            "markup_block_type": "image",
            "title_path": ["Incident Report"],
            "image_refs": [
                {
                    "image_path": "assets/incident_report-1.png",
                    "image_caption": "Revenue chart",
                }
            ],
            "image_path": "assets/incident_report-1.png",
            "image_caption": "Revenue chart",
        },
    )
    assert parsed.chunks[3].metadata["markup_block_type"] == "table"
    assert len(parsed.assets) == 1
    assert parsed.assets[0].source_path == "assets/incident_report-1.png"
    assert parsed.assets[0].content == b"markdown image bytes"
    assert parsed.assets[0].content_type == "image/png"
    assert parsed.assets[0].metadata["aliases"] == [
        "assets/incident_report-1.png",
        "./assets/incident_report-1.png",
    ]


def test_html_parser_emits_structure_and_extracts_data_uri_image() -> None:
    """HTML files should produce structural chunks and extracted image assets."""

    image_uri = image_data_uri(b"html image bytes")
    parsed = parse_document_bytes(
        f"""
<article>
  <h1>Incident Report</h1>
  <p>Intro paragraph with <strong>context</strong>.</p>
  <img alt="Revenue chart" src="{image_uri}">
  <table><tr><th>Metric</th><th>Value</th></tr><tr><td>ARR</td><td>42</td></tr></table>
</article>
""".encode(),
        "html",
        source_name="incident report.html",
    )

    assert parsed.metadata == {
        "parser": "markup",
        "file_type": "html",
        "markup_format": "html",
        "embedded_image_count": 1,
    }
    assert image_uri not in parsed.text
    assert '<img src="assets/incident_report-1.png" alt="Revenue chart">' in parsed.text
    assert [chunk.chunk_type for chunk in parsed.chunks] == [
        "text",
        "text",
        "image",
        "table",
    ]
    assert parsed.chunks[0].content == "Incident Report"
    assert parsed.chunks[0].metadata["heading_level"] == 1
    assert parsed.chunks[1].content == "Intro paragraph with context ."
    assert parsed.chunks[1].metadata["title_path"] == ["Incident Report"]
    assert parsed.chunks[2] == ParsedChunk(
        content=(
            '<figure><img src="assets/incident_report-1.png" alt="Revenue chart">'
            "<figcaption>Revenue chart</figcaption></figure>"
        ),
        chunk_type="image",
        metadata={
            "markup_block_type": "image",
            "image_path": "assets/incident_report-1.png",
            "image_caption": "Revenue chart",
            "title_path": ["Incident Report"],
        },
    )
    assert parsed.chunks[3].chunk_type == "table"
    assert len(parsed.assets) == 1
    assert parsed.assets[0].source_path == "assets/incident_report-1.png"
    assert parsed.assets[0].content == b"html image bytes"
    assert parsed.assets[0].content_type == "image/png"


def test_markup_image_asset_references_are_rewritten_for_ingestion() -> None:
    """Markup image chunks should use backend-controlled asset URLs after ingestion."""

    parsed = parse_document_bytes(
        f"![Chart]({image_data_uri(b'image bytes')})".encode(),
        "markdown",
        source_name="chart.md",
    )
    chunks = build_ingestion_chunks(
        parsed,
        parsed_text=parsed.text,
        asset_replacements={"assets/chart-1.png": "/api/v1/documents/doc/assets/asset"},
        file_type="md",
        chunk_size=80,
        chunk_overlap=0,
    )

    assert chunks == [
        ParsedChunk(
            content="![Chart](/api/v1/documents/doc/assets/asset)",
            chunk_type="image",
            metadata={
                "markup_block_type": "image",
                "image_refs": [
                    {
                        "image_path": "assets/chart-1.png",
                        "image_caption": "Chart",
                    }
                ],
                "image_path": "assets/chart-1.png",
                "image_caption": "Chart",
            },
        )
    ]