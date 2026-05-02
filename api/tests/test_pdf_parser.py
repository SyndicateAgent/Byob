import json
import subprocess
from pathlib import Path

import pytest

from workers.parsers import mineru_parser, pdf_parser
from workers.parsers.base import ParsedDocument
from workers.parsers.mineru_parser import content_list_to_chunks
from workers.parsers.pdf_parser import PdfParserConfig, parse_pdf


def test_pdf_parser_uses_mineru_content_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """PDF parsing delegates to MinerU and preserves typed content-list chunks."""

    def fake_run(
        command: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert capture_output is True
        assert text is True
        assert timeout == 30
        output_dir = Path(command[command.index("-o") + 1])
        input_path = Path(command[command.index("-p") + 1])
        result_dir = output_dir / input_path.stem / "auto"
        result_dir.mkdir(parents=True)
        image_dir = result_dir / "images"
        image_dir.mkdir()
        (image_dir / "figure.png").write_bytes(b"fake png")
        content_list = [
            {"type": "text", "text": "# Section title", "level": 1, "page_idx": 0},
            {"type": "equation", "text": "$E=mc^2$", "page_idx": 0},
            {
                "type": "table",
                "caption": ["Table 1"],
                "html": "<table><tr><td>Number</td></tr></table>",
                "page_idx": 1,
            },
            {
                "type": "image",
                "caption": ["Figure caption"],
                "img_path": "images/figure.png",
                "page_idx": 1,
            },
        ]
        (result_dir / f"{input_path.stem}_content_list_v2.json").write_text(
            json.dumps(content_list),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(mineru_parser.shutil, "which", lambda command: command)
    monkeypatch.setattr(mineru_parser.subprocess, "run", fake_run)

    parsed = parse_pdf(
        b"%PDF-1.7",
        config=PdfParserConfig(
            parser="mineru",
            mineru_timeout_seconds=30,
            mineru_fallback_to_pypdf=False,
        ),
    )

    assert parsed.metadata["parser"] == "mineru"
    assert parsed.metadata["mineru_output"] == "content_list"
    assert parsed.metadata["page_count"] == 2
    assert parsed.metadata["mineru_block_types"] == {
        "text": 1,
        "equation": 1,
        "table": 1,
        "image": 1,
    }
    assert [chunk.chunk_type for chunk in parsed.chunks] == [
        "text",
        "equation",
        "table",
        "image",
    ]
    assert parsed.chunks[0].metadata["title_path"] == ["Section title"]
    assert parsed.chunks[1].metadata["latex"] == "$E=mc^2$"
    assert parsed.chunks[2].metadata["table_caption"] == "Table 1"
    assert parsed.chunks[3].metadata["image_caption"] == "Figure caption"
    assert parsed.chunks[3].metadata["image_path"] == "images/figure.png"
    assert "![Figure caption](images/figure.png)" in parsed.text
    assert len(parsed.assets) == 1
    assert parsed.assets[0].source_path == "images/figure.png"
    assert parsed.assets[0].content_type == "image/png"
    assert parsed.assets[0].metadata["aliases"] == [
        "images/figure.png",
        "./images/figure.png",
        "document/auto/images/figure.png",
        "./document/auto/images/figure.png",
    ]


def test_content_list_to_chunks_tracks_title_path_bbox_and_rich_types() -> None:
    """MinerU content-list blocks become RAG chunks with useful metadata."""

    text, metadata, chunks = content_list_to_chunks(
        [
            {"type": "text", "text": "# Incident Report", "level": 1, "page_idx": 0},
            {"type": "text", "text": "Timeline details", "page_idx": 0},
            {
                "type": "table",
                "table_caption": ["Evidence table"],
                "table_body": "<table><tr><td>Item</td></tr></table>",
                "page_idx": 1,
                "bbox": [10, 20, 200, 260],
            },
            {
                "type": "image",
                "img_caption": ["Scene image"],
                "img_path": "images/scene.png",
                "page_idx": 1,
            },
            {"type": "equation", "latex": "a^2+b^2=c^2", "page_idx": 2},
        ]
    )

    assert metadata["page_count"] == 3
    assert "Incident Report" in text
    assert [chunk.chunk_type for chunk in chunks] == [
        "text",
        "text",
        "table",
        "image",
        "equation",
    ]
    assert chunks[1].metadata["title_path"] == ["Incident Report"]
    assert chunks[2].page_num == 2
    assert chunks[2].bbox == {"points": [10, 20, 200, 260]}
    assert chunks[2].metadata["table_caption"] == "Evidence table"
    assert chunks[3].metadata["image_caption"] == "Scene image"
    assert chunks[3].metadata["image_path"] == "images/scene.png"
    assert "![Scene image](images/scene.png)" in chunks[3].content
    assert chunks[4].metadata["latex"] == "a^2+b^2=c^2"


def test_pdf_parser_falls_back_to_pypdf_when_mineru_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF fallback stays isolated from the MinerU parser implementation."""

    monkeypatch.setattr(mineru_parser.shutil, "which", lambda command: None)
    monkeypatch.setattr(
        pdf_parser,
        "parse_pdf_with_pypdf",
        lambda content: ParsedDocument(text="fallback text", metadata={"parser": "pypdf"}),
    )

    parsed = parse_pdf(
        b"not a real pdf",
        config=PdfParserConfig(parser="mineru", mineru_fallback_to_pypdf=True),
    )

    assert parsed.text == "fallback text"
    assert parsed.metadata["parser"] == "pypdf"
    assert parsed.metadata["mineru_fallback"] is True
    assert "MinerU command not found" in str(parsed.metadata["mineru_error"])