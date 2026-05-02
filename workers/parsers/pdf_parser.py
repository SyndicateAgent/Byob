from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from pypdf import PdfReader

from workers.parsers.base import ParsedDocument
from workers.parsers.mineru_parser import MineruParserConfig, parse_mineru_document


@dataclass(frozen=True)
class PdfParserConfig:
    """Runtime configuration for PDF parsing."""

    parser: Literal["mineru", "pypdf"] = "mineru"
    mineru_command: str = "mineru"
    mineru_backend: str = "pipeline"
    mineru_parse_method: str = "auto"
    mineru_lang: str = "ch"
    mineru_timeout_seconds: int = 900
    mineru_api_url: str | None = None
    mineru_formula_enable: bool = True
    mineru_table_enable: bool = True
    mineru_fallback_to_pypdf: bool = True


def parse_pdf(content: bytes, config: PdfParserConfig | None = None) -> ParsedDocument:
    """Parse a PDF, preferring MinerU structured output with pypdf as fallback."""

    parser_config = config or PdfParserConfig()
    if parser_config.parser == "pypdf":
        return parse_pdf_with_pypdf(content)

    try:
        return parse_pdf_with_mineru(content, parser_config)
    except Exception as exc:
        if not parser_config.mineru_fallback_to_pypdf:
            raise
        parsed = parse_pdf_with_pypdf(content)
        return ParsedDocument(
            text=parsed.text,
            metadata={
                **parsed.metadata,
                "mineru_fallback": True,
                "mineru_error": str(exc)[:1000],
            },
            chunks=parsed.chunks,
        )


def parse_pdf_with_mineru(content: bytes, config: PdfParserConfig) -> ParsedDocument:
    """Parse PDF bytes through the shared MinerU parser."""

    return parse_mineru_document(
        content,
        file_type="pdf",
        config=mineru_config_from_pdf_config(config),
        source_name="document.pdf",
    )


def parse_pdf_with_pypdf(content: bytes) -> ParsedDocument:
    """Extract page text with pypdf for lightweight fallback mode."""

    reader = PdfReader(BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return ParsedDocument(
        text="\n\n".join(page.strip() for page in pages if page.strip()),
        metadata={"parser": "pypdf", "page_count": len(reader.pages)},
    )


def mineru_config_from_pdf_config(config: PdfParserConfig) -> MineruParserConfig:
    """Map PDF settings onto the shared MinerU parser config."""

    return MineruParserConfig(
        command=config.mineru_command,
        backend=config.mineru_backend,
        parse_method=config.mineru_parse_method,
        lang=config.mineru_lang,
        timeout_seconds=config.mineru_timeout_seconds,
        api_url=config.mineru_api_url,
        formula_enable=config.mineru_formula_enable,
        table_enable=config.mineru_table_enable,
    )