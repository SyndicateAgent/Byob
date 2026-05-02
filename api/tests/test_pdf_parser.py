import json
import subprocess
from pathlib import Path

import pytest

from workers.parsers import pdf_parser
from workers.parsers.base import ParsedDocument
from workers.parsers.pdf_parser import PdfParserConfig, clean_pdf_extracted_text, parse_pdf


def test_pdf_parser_uses_mineru_content_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """MinerU content-list output is preferred because it preserves layout blocks."""

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
            {"type": "text", "text": "Section title\nV i c t i m(s)", "page_idx": 0},
            {"type": "equation", "text": "$E=mc^2$", "page_idx": 0},
            {
                "type": "table",
                "caption": ["Table 1"],
                "html": (
                    "<table><tr><td>Num ber</td>"
                    "<td>hw1\\diary\\d iary 4.26.txt</td>"
                    "<td>eac7faf73f64dba 833466d3b21c2 ce3a</td></tr></table>"
                ),
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

    monkeypatch.setattr(pdf_parser.shutil, "which", lambda command: command)
    monkeypatch.setattr(pdf_parser.subprocess, "run", fake_run)

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
    assert "Section title" in parsed.text
    assert "Victim(s)" in parsed.text
    assert "$E=mc^2$" in parsed.text
    assert "<table>" in parsed.text
    assert "Num ber" not in parsed.text
    assert "<td>Number</td>" in parsed.text
    assert "d iary" not in parsed.text
    assert "diary 4.26.txt" in parsed.text
    assert "eac7faf73f64dba833466d3b21c2ce3a" in parsed.text
    assert "Figure caption" in parsed.text
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


def test_pdf_text_cleanup_repairs_spacing_without_breaking_html_tags() -> None:
    """PDF/OCR spacing cleanup should preserve tags while repairing text nodes."""

    cleaned = clean_pdf_extracted_text(
        "<table><tr><td>V i c t i m</td><td>Num ber</td>"
        "<td>normal words stay spaced</td></tr></table>"
    )

    assert cleaned == (
        "<table><tr><td>Victim</td><td>Number</td>"
        "<td>normal words stay spaced</td></tr></table>"
    )


def test_pdf_parser_falls_back_to_pypdf_when_mineru_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local development remains usable when MinerU has not been installed yet."""

    monkeypatch.setattr(pdf_parser.shutil, "which", lambda command: None)
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
