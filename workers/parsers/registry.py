from workers.parsers.base import ParsedDocument
from workers.parsers.docx_parser import parse_docx
from workers.parsers.image_parser import IMAGE_FILE_TYPES, parse_image
from workers.parsers.markup_parser import MARKUP_FILE_TYPES, parse_markup
from workers.parsers.mineru_parser import MINERU_DOCUMENT_FILE_TYPES, parse_mineru_document
from workers.parsers.pdf_parser import PdfParserConfig, mineru_config_from_pdf_config, parse_pdf
from workers.parsers.text_parser import parse_text
from workers.parsers.xlsx_parser import parse_xlsx


def parse_document_bytes(
    content: bytes,
    file_type: str | None,
    *,
    pdf_config: PdfParserConfig | None = None,
    source_name: str | None = None,
) -> ParsedDocument:
    """Dispatch document bytes to the parser for a supported file type."""

    normalized_type = (file_type or "txt").lower().lstrip(".")
    if normalized_type == "pdf":
        return parse_pdf(content, config=pdf_config)
    if normalized_type in MINERU_DOCUMENT_FILE_TYPES:
        try:
            parser_config = pdf_config or PdfParserConfig()
            return parse_mineru_document(
                content,
                file_type=normalized_type,
                config=mineru_config_from_pdf_config(parser_config),
                source_name=source_name,
            )
        except RuntimeError as exc:
            if "MinerU command not found" not in str(exc):
                raise
            if normalized_type == "docx":
                parsed = parse_docx(content)
            elif normalized_type == "xlsx":
                parsed = parse_xlsx(content, source_name=source_name)
            else:
                raise
            return ParsedDocument(
                text=parsed.text,
                metadata={
                    **parsed.metadata,
                    "mineru_fallback": True,
                    "mineru_error": str(exc),
                },
                assets=parsed.assets,
                chunks=parsed.chunks,
            )
    if normalized_type in IMAGE_FILE_TYPES:
        return parse_image(content, file_type=normalized_type, source_name=source_name)
    if normalized_type in MARKUP_FILE_TYPES:
        return parse_markup(content, file_type=normalized_type, source_name=source_name)
    if normalized_type == "txt":
        return parse_text(content, file_type=normalized_type)
    raise ValueError(f"Unsupported document type: {normalized_type}")
