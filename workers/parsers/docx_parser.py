from io import BytesIO

from docx import Document as DocxDocument

from workers.parsers.base import ParsedDocument


def parse_docx(content: bytes) -> ParsedDocument:
    """Extract paragraph text from a DOCX document."""

    document = DocxDocument(BytesIO(content))
    paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return ParsedDocument(
        text="\n\n".join(paragraphs),
        metadata={"paragraph_count": len(paragraphs)},
    )
