from io import BytesIO

from pypdf import PdfReader

from workers.parsers.base import ParsedDocument


def parse_pdf(content: bytes) -> ParsedDocument:
    """Extract text from a PDF document."""

    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return ParsedDocument(text="\n\n".join(pages), metadata={"page_count": len(reader.pages)})
