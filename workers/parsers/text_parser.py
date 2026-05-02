from workers.parsers.base import ParsedChunk, ParsedDocument


def parse_text(content: bytes, *, file_type: str | None = None) -> ParsedDocument:
    """Parse UTF-8 text-like document bytes."""

    text = content.decode("utf-8", errors="replace")
    return ParsedDocument(
        text=text,
        metadata={"parser": "text", "file_type": file_type or "txt"},
        chunks=[ParsedChunk(content=text)] if text.strip() else [],
    )
