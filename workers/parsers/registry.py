from re import sub

from workers.parsers.base import ParsedDocument
from workers.parsers.docx_parser import parse_docx
from workers.parsers.pdf_parser import parse_pdf
from workers.parsers.text_parser import parse_text


def parse_document_bytes(content: bytes, file_type: str | None) -> ParsedDocument:
    """Dispatch document bytes to the parser for a supported file type."""

    normalized_type = (file_type or "txt").lower().lstrip(".")
    if normalized_type == "pdf":
        return parse_pdf(content)
    if normalized_type == "docx":
        return parse_docx(content)
    if normalized_type in {"txt", "md", "markdown", "html"}:
        parsed = parse_text(content, file_type=normalized_type)
        if normalized_type == "html":
            return ParsedDocument(text=strip_html(parsed.text), metadata=parsed.metadata)
        return parsed
    raise ValueError(f"Unsupported document type: {normalized_type}")


def strip_html(text: str) -> str:
    """Very small HTML-to-text fallback for URL ingestion."""

    without_scripts = sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
    without_tags = sub(r"(?s)<[^>]+>", " ", without_scripts)
    return sub(r"\s+", " ", without_tags).strip()
